from types import SimpleNamespace as Object
from datetime import datetime,timezone,timedelta
from app.incident_progress import progress

BASE=datetime(2026,11,16,9,tzinfo=timezone.utc)
def event(action,index=None,**detail):
    if index is not None:detail['stage_index']=index
    return Object(action=action,detail=detail,actor_id=3,created_at=BASE)
def row():return Object(workflow={'steps':[{'name':'Revisar','kind':'WORK','scope':'GENERAL'},{'name':'Revisar','kind':'EXECUTE','scope':'GENERAL'},{'name':'Finalizar','kind':'CONFIRM','scope':'REQUESTER'}]},status='OPEN',stage_index=1,creator_id=2,delegation_id='1:01',destination_id=None,assignee_id=4,entered_at=BASE+timedelta(hours=1),due_at=BASE+timedelta(hours=2))

def test_indices_disambiguate_identical_names_and_preserve_actual_actors():
    result=progress(row(),[event('ASSIGNED',0,stage='Revisar',assignee_name='Ana'),event('COMPLETED_STAGE',0,stage='Revisar'),event('ASSIGNED',1,stage='Revisar',assignee_name='Bea')],{3:'Supervisor',4:'Bea'})
    assert result[0]['state']=='COMPLETED' and result[0]['completed_at']==BASE
    assert result[0]['responsible_name']=='Ana' and result[0]['completed_by']=='Supervisor'
    assert result[1]['state']=='CURRENT' and result[1]['entered_at']==row().entered_at
    assert result[1]['completed_at'] is None and result[2]['entered_at'] is None
    # Ambiguous historical names have no invented date or responsible.
    legacy=progress(row(),[event('COMPLETED_STAGE',stage='Revisar')],{4:'Bea'})
    assert legacy[0]['completed_at'] is None and legacy[0]['responsible_name'] is None


def test_returns_keep_multiple_visits_and_closing_skips_remaining_steps():
    record=row();record.stage_index=0
    result=progress(record,[event('ASSIGNED',0,assignee_name='Ana'),event('COMPLETED_STAGE',0),event('ASSIGNED',1,assignee_name='Bea'),event('ASSIGNED',0,assignee_name='Ana')],{3:'Supervisor',4:'Ana'})
    assert len(result[0]['visits'])==2 and result[0]['visits'][0]['completed_at']==BASE
    assert result[0]['state']=='CURRENT' and result[0]['completed_at'] is None
    record.status='CLOSED';record.stage_index=0
    result=progress(record,[event('COMPLETED_STAGE',0)],{3:'Supervisor'})
    assert result[0]['state']=='COMPLETED' and all(step['state']=='NOT_EXECUTED' for step in result[1:])
