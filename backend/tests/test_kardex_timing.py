from app.kardex_timing import aggregate

def test_order_waits_for_all_kardex_tasks():
    inputs = [{'ORDEN': task, 'FECHA_CREACION': '07/10/2026 10:00:00'} for task in ('A', 'B')]
    outputs = [{'ORDEN': 'A', 'FECHA_MOVIMIENTO': '07/10/2026 10:05:00', 'ORDEN_COMPLETA': 1}]
    assert aggregate(inputs, outputs)['kardex_closed_at'] is None
    outputs.append({'ORDEN': 'B', 'FECHA_MOVIMIENTO': '07/10/2026 10:12:00', 'ORDEN_COMPLETA': 1})
    result = aggregate(inputs, outputs)
    assert (result['kardex_closed_at'] - result['kardex_started_at']).total_seconds() == 720

def test_invalid_dates_do_not_close_order():
    assert aggregate([{'ORDEN': 'A', 'FECHA_CREACION': 'invalid'}], []) == {}
    result = aggregate([{'ORDEN': 'A', 'FECHA_CREACION': '2026-10-07T10:00:00'}],
                       [{'ORDEN': 'A', 'FECHA_MOVIMIENTO': '2026-10-07T09:00:00', 'ORDEN_COMPLETA': 1}])
    assert result['kardex_date_error']
    assert result['kardex_closed_at'] is None


def test_real_exit_reference_and_kardex_dates():
    from app.kardex_timing import sales_order_number
    assert sales_order_number('2026/AL/6006762') == '6006762'
    result = aggregate([{'ORDEN': '2026-AL-6006762', 'FECHA_CREACION': '2026-10-07 11:39:28'}],
                       [{'ORDEN': '2026-AL-6006762', 'FECHA_MOVIMIENTO': '07/10/2026 11:40:47', 'ORDEN_COMPLETA': 1}])
    assert (result['kardex_closed_at'] - result['kardex_started_at']).total_seconds() == 79


def test_operations_preserves_registered_and_preparation_dates():
    from types import SimpleNamespace
    from datetime import datetime
    from app.order_timeline import dispatch_timing
    record = SimpleNamespace(recorded_at=datetime(2026,10,7,12,2), prepared_at=datetime(2026,10,7), delivered_at=None, invoiced_at=None, source_updated_at=None)
    steps = dispatch_timing(record)['operational_workflow']
    assert [step['stage'] for step in steps] == ['REGISTRADO', 'EN_PREPARACION', 'ATENDIDO', 'ENTREGADO']
    assert steps[0]['occurred_at'].hour == 12
    assert steps[1]['occurred_at'].second == 10
    assert steps[2]['occurred_at'] is None


def test_preparation_uses_first_kardex_material_before_fallback():
    from types import SimpleNamespace
    from datetime import datetime
    from app.order_timeline import dispatch_timing
    record = SimpleNamespace(recorded_at=datetime(2026,10,7,11,39), prepared_at=datetime(2026,10,7), delivered_at=None, invoiced_at=None, source_updated_at=None)
    timings = aggregate([{'ORDEN': 'A', 'FECHA_CREACION': stamp} for stamp in ('2026-10-07 11:39:35', '2026-10-07 11:39:28')], [])
    step = dispatch_timing(record, kardex_started_at=timings['kardex_started_at'])['operational_workflow'][1]
    assert step['occurred_at'].strftime('%H:%M:%S') == '11:39:28'
    fallback = dispatch_timing(record)['operational_workflow'][1]
    assert fallback['occurred_at'].strftime('%H:%M:%S') == '11:39:10'
    record.prepared_at = None
    assert dispatch_timing(record, kardex_started_at=timings['kardex_started_at'])['operational_workflow'][1]['occurred_at'] is not None
