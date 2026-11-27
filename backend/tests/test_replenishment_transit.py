from contextlib import contextmanager
from copy import deepcopy
import sqlite3
import pytest
from sqlalchemy import delete
from app import replenishment_transit as module
from app.models import DelegationWarehouse as Link
from app.db import SessionLocal
from app.replenishment_engine import prepare_context,calculate_article,annotate_central
from test_replenishment import source_for


def test_transit_query_uses_full_header_key_state_type_material_and_direction():
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute("ATTACH DATABASE ':memory:' AS dbo")
    db.execute('CREATE TABLE dbo.MovimientoAlmacenCabecera (CodigoEmpresa INT, Ejercicio INT, Numero INT, Serie TEXT)')
    db.execute('CREATE TABLE dbo.MovimientoAlmacenLineas (CodigoEmpresa INT, Ejercicio INT, Numero INT, Serie TEXT, CodigoArticulo TEXT, CodigoAlmacen TEXT, AlmacenContrapartida TEXT, Unidades REAL, EX_EstadoMovA TEXT, TipoMovimientoAlmacen TEXT)')
    db.executemany('INSERT INTO dbo.MovimientoAlmacenCabecera VALUES (?,?,?,?)',[(1,2026,1,'A'),(1,2026,1,'B'),(2,2026,1,'A'),(1,2025,1,'A')])
    def line(company=1,year=2026,series='A',sku='24024',origin='99',destination='02',units=4,state='Transito',kind='T',number=1):
        return (company,year,number,series,sku,origin,destination,units,state,kind)
    db.executemany('INSERT INTO dbo.MovimientoAlmacenLineas VALUES (?,?,?,?,?,?,?,?,?,?)',[
        line(),line(series='B',origin='00',units=6),line(origin='02',destination='00',units=3),
        line(company=2,units=100),line(number=999,units=100),line(state='Registrado',units=100),
        line(kind='E',units=100),line(sku='OTHER',units=100)])
    calls=[]
    class Cursor:
        def execute(self,sql,params=()):self.sql=sql;self.params=params;calls.append((sql,params))
        def fetchall(self):
            if 'INFORMATION_SCHEMA' in self.sql:return [{'TABLE_NAME':table,'COLUMN_NAME':'Serie'} for table in ('MovimientoAlmacenCabecera','MovimientoAlmacenLineas')]
            return [dict(row) for row in db.execute(self.sql.replace('%s','?'),self.params)]
    transits=module.fetch_transits(Cursor(),['24024'])
    assert sum(r['units'] for r in transits)==13
    assert 'mac.[Serie]=mal.[Serie]' in calls[-1][0]
    assert calls[-1][1]==(1,'Transito','T','24024')
    stocks=[dict(sku='24024',delegation='00',stock=20,incoming=10,outgoing=2),dict(sku='24024',delegation='02',stock=5,incoming=7,outgoing=1)]
    module.add_transits(stocks,transits,{'99':'00','00':'00','02':'02'})
    assert (stocks[0]['incoming'],stocks[0]['outgoing'])==(13,12)
    assert (stocks[1]['incoming'],stocks[1]['outgoing'])==(17,4)
    assert stocks[0]['stock']==20 and stocks[0]['incoming_exit']==10 and stocks[0]['outgoing_transit']==10
    db.close()


def test_mapping_uses_company_active_and_stock_flags_and_rejects_double_counting():
    with SessionLocal() as db:
        db.execute(delete(Link));db.add_all([
            Link(company_code=c,delegation_code=d,warehouse_code=w,delegation_name=d,warehouse_name=w,active=a,use_for_stock=s,is_primary=False)
            for c,d,w,a,s in [(1,'00','99',True,True),(1,'00','00',True,True),(1,'02','02',True,True),
                              (1,'00','INACTIVE',False,True),(1,'00','NO-STOCK',True,False),(2,'04','99',True,True)]])
        db.commit()
    try:
        assert module.stock_warehouse_map()=={'99':'00','00':'00','02':'02'}
        with SessionLocal() as db:
            db.add(Link(company_code=1,delegation_code='04',warehouse_code='99',delegation_name='',warehouse_name='',active=True,use_for_stock=True));db.commit()
        with pytest.raises(ValueError,match='más de una delegación'):module.stock_warehouse_map()
    finally:
        with SessionLocal() as db:db.execute(delete(Link));db.commit()
    with pytest.raises(ValueError,match='Configura'):module.stock_warehouse_map()


def test_transit_updates_positions_and_central_dispatch_without_changing_history():
    source=source_for();sku=source['articles'][0]['sku']
    before=deepcopy(source['sales'])
    source['stocks']=[dict(sku=sku,delegation='00',stock=20,incoming=2,outgoing=1),dict(sku=sku,delegation='02',stock=0,incoming=0,outgoing=0)]
    module.add_transits(source['stocks'],[{'sku':sku,'origin':'99','destination':'02','units':4}],{'99':'00','02':'02'})
    context=prepare_context(source,['02'],[],{})
    result=calculate_article(source['articles'][0],'02',context)
    annotate_central([result],source)
    assert result['incoming']==4 and result['incoming_transit']==4 and result['incoming_exit']==0
    assert result['inventory_position']==4 and result['central_outgoing']==5
    assert result['central_physical_available']==15 and source['sales']==before


def test_unconfigured_warehouses_are_excluded_and_missing_stock_is_not_invented():
    stocks=[dict(sku='24024',delegation='00',stock=1,incoming=0,outgoing=0)]
    module.add_transits(stocks,[dict(sku='24024',origin='IGNORED',destination='IGNORED',units=10)],{})
    assert stocks[0]['incoming']==stocks[0]['outgoing']==0
    with pytest.raises(ValueError,match='sin fila de stock'):
        module.add_transits(stocks,[dict(sku='24024',origin='99',destination='02',units=10)],{'99':'00','02':'02'})


def test_sql_server_decimal_transits_can_be_fingerprinted_and_saved():
    from decimal import Decimal
    import json
    from app.replenishment_worker import digest
    class Cursor:
        def execute(self,sql,params=()):self.sql=sql
        def fetchall(self):
            if 'INFORMATION_SCHEMA' in self.sql:return []
            return [{'sku':'24024','origin':'99','destination':'02','units':Decimal('12.500000')}]
    transits=module.fetch_transits(Cursor(),['24024'])
    snapshot={'transits':transits}
    assert digest(snapshot)
    assert json.loads(json.dumps(snapshot))['transits'][0]['units']==12.5
