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
