import json
from sqlalchemy import create_engine, text
from app.replenishment_read_model import migrate


def test_legacy_table_upgrade_is_bounded_idempotent_and_preserves_saved_results():
    engine=create_engine('sqlite://')
    payload={'description':'Material anterior','final_quantity':12,'monthly_consumption':[{'month':'2026-01','consumption':99}],
             'consumption_variants':{'MEDIAN':{'consumption_basis':'MEDIAN','final_quantity':42,'recommendations':[{'reason':'Conservar aviso'}]}}}
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE replenishment_results (id INTEGER PRIMARY KEY, scenario_id INTEGER, sku TEXT, delegation TEXT, payload JSON)'))
        connection.execute(text('INSERT INTO replenishment_results (id,scenario_id,sku,delegation,payload) VALUES (:id,1,:sku,\'02\',:payload)'),
                           [{'id':i,'sku':str(i),'payload':json.dumps(payload)} for i in range(1,126)])
    migrate(engine);migrate(engine)
    with engine.connect() as connection:
        rows=connection.execute(text('SELECT payload,filter_data FROM replenishment_results')).all()
        assert len(rows)==125
        for original,projection in rows:
            assert json.loads(original)==payload
            compact=json.loads(projection)
            assert 'monthly_consumption' not in compact
            assert compact['final_quantity']==12
            assert compact['consumption_variants']['MEDIAN']['final_quantity']==42
            assert len(compact['consumption_variants']['MEDIAN']['recommendations'])==1
        indexes=connection.execute(text("PRAGMA index_list('replenishment_results')")).all()
        assert any(row[1]=='ix_replenishment_results_scenario_delegation_sku' for row in indexes)
