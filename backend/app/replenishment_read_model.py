"""Small saved projection for filtering/aggregating, without histories or variants."""
from sqlalchemy import bindparam, event, inspect, select, text, update

FIELDS = ('consumption_basis', 'description', 'final_quantity', 'central_can_supply',
          'overstock', 'total_demand', 'monthly_mean', 'daily_mean', 'daily_reference',
          'coverage_days', 'target_stock', 'irregular')


def filter_projection(payload):
    def compact(row):
        # Keep the existing SQL/legacy null semantics, including alert counts.
        return {**{key: row[key] for key in FIELDS if key in row},
                'recommendations': [0] * len(row.get('recommendations', []))}
    return {**compact(payload), 'consumption_variants': {
        basis: compact(row) for basis, row in payload.get('consumption_variants', {}).items()}}


def update_projection(mapper, connection, target):
    target.filter_data = filter_projection(target.payload)


def install_events(model):
    event.listen(model, 'before_insert', update_projection)
    event.listen(model, 'before_update', update_projection)


def migrate(engine):
    """Idempotent, bounded adoption of already computed results; never read EXIT.

    Row locks prevent overwriting a concurrent manual adjustment with stale data.
    Each batch commits independently so a restart resumes only missing projections.
    """
    from .models import ReplenishmentResult as Result
    columns = {c['name'] for c in inspect(engine).get_columns(Result.__tablename__)}
    if 'filter_data' not in columns:
        with engine.begin() as connection:
            suffix = ' IF NOT EXISTS' if engine.dialect.name == 'postgresql' else ''
            connection.execute(text(f'ALTER TABLE replenishment_results ADD COLUMN{suffix} filter_data JSON'))
    with engine.begin() as connection:
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_replenishment_results_scenario_delegation_sku '
                                'ON replenishment_results (scenario_id, delegation, sku)'))
    while True:
        with engine.begin() as connection:
            query = select(Result.id, Result.payload).where(Result.filter_data.is_(None)).order_by(Result.id).limit(100)
            if engine.dialect.name == 'postgresql': query = query.with_for_update()
            rows = connection.execute(query).all()
            if not rows: return
            connection.execute(update(Result).where(Result.id == bindparam('row_id'))
                .values(filter_data=bindparam('projection')),
                [{'row_id':row.id,'projection':filter_projection(row.payload)} for row in rows])
