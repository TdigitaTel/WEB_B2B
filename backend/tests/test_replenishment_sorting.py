import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from app.models import ReplenishmentResult as Result
from app.replenishment import ordered_results,ResultFilters

NUMERIC=['stock','incoming','outgoing','inventory_position','monthly_mean','minimum_stock','replenishment_point','maximum_stock','quantity_without_multiple','quantity_with_exit_multiple','exit_multiple','central_available','central_physical_available','quantity','coverage']

@pytest.fixture
def rows():
    engine=create_engine('sqlite://')
    Result.__table__.create(engine)
    with engine.begin() as connection:
        for index,(sku,value,label,delegation,level) in enumerate([('A',30,'Zulu','02','HIGH'),('B',10,'Alpha','01','LOW'),('C',None,None,'04','NOT_ANALYZED'),('D',20,'Beta','00','MEDIUM')],1):
            data={key:value for key in NUMERIC}
            data.update(description=label,final_quantity=value,coverage_days=value,exceptionality={'level':level},recommendations=[{}]*({'A':3,'B':1,'C':0,'D':2}[sku]))
            variant={**data,**{key:40-value if value is not None else None for key in NUMERIC},'consumption_basis':'MEDIAN','final_quantity':40-value if value is not None else None,'coverage_days':40-value if value is not None else None}
            data['consumption_variants']={'MEDIAN':variant}
            # Existing saved calculations have a compact projection lacking new sort fields.
            compact={'description':label,'recommendations':data['recommendations']}
            connection.execute(Result.__table__.insert().values(id=index,scenario_id=1,sku=sku,delegation=delegation,payload=data,filter_data=compact))
    with Session(engine) as session:yield session

@pytest.mark.parametrize('key',NUMERIC)
@pytest.mark.parametrize('descending',[False,True])
def test_numeric_sorting_supports_legacy_projections_and_keeps_missing_values_last(rows,key,descending):
    ResultFilters(sort=key)
    query=ordered_results(select(Result),key,descending)
    assert [row.sku for row in rows.scalars(query)]==(['A','D','B','C'] if descending else ['B','D','A','C'])
    assert [row.sku for row in rows.scalars(query.offset(1).limit(1))]==['D']

@pytest.mark.parametrize('key',NUMERIC)
def test_ordering_uses_selected_consumption_basis(rows,key):
    query=ordered_results(select(Result),key,False,'MEDIAN')
    assert [row.sku for row in rows.scalars(query)]==['A','D','B','C']

@pytest.mark.parametrize('key,expected',[
    ('sku',['A','B','C','D']),('description',['B','D','A','C']),
    ('delegation',['D','B','A','C']),('exceptionality',['B','D','A','C']),('alerts',['C','B','D','A'])])
def test_text_flags_and_notice_count_are_sortable(rows,key,expected):
    ResultFilters(sort=key)
    assert [row.sku for row in rows.scalars(ordered_results(select(Result),key,False))]==expected
