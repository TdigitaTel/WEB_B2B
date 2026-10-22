import math
import pytest
from app.erp_db import _insert_article_filter_codes, _prepare_eligible_articles

class Cursor:
    def __init__(self):self.calls=[]
    def execute(self,sql,params=()):self.calls.append((sql,params))
    def executemany(self,*args,**kwargs):raise AssertionError('No enviar códigos individualmente')

@pytest.mark.parametrize('size',[0,1,999,1000,1001,25001])
@pytest.mark.parametrize('table',['#EligibleArticles','#HiddenArticles'])
def test_filters_are_loaded_in_bounded_multirow_statements(size,table):
    cursor=Cursor()
    codes=[f'{i:06d}' for i in range(size)]
    _insert_article_filter_codes(cursor,table,codes)
    assert len(cursor.calls)==math.ceil(size/1000)
    assert [value for sql,values in cursor.calls for value in values]==codes
    for sql,params in cursor.calls:
        assert 1<=len(params)<=1000
        assert sql.count('(%s)')==len(params)
        assert sql.startswith(f'INSERT INTO {table} (article_code) VALUES ')

def test_filter_preserves_leading_zeroes_and_parameterizes_values():
    cursor=Cursor()
    _insert_article_filter_codes(cursor,'#EligibleArticles',['00004','00004',' 00123 ',"x'); DROP TABLE a;--",''])
    sql,params=cursor.calls[0]
    assert params==('00004','00123',"x'); DROP TABLE a;--")
    assert 'DROP TABLE' not in sql
    with pytest.raises(ValueError):_insert_article_filter_codes(cursor,'not_allowed',['A'])

def test_none_is_no_filter_and_empty_is_explicit_empty_filter():
    cursor=Cursor()
    assert _prepare_eligible_articles(cursor,None)==''
    assert cursor.calls==[]
    assert _prepare_eligible_articles(cursor,[])=='INNER JOIN #EligibleArticles e ON e.article_code = '
    assert len(cursor.calls)==1 and cursor.calls[0][0].startswith('CREATE TABLE #EligibleArticles')
