"""Progress from persisted events, without inventing historical dates or actors."""
from datetime import timezone
from .incident_flow import requester


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def planned_user_id(row,step):
    if requester(step):return row.creator_id
    target=step.get('general') if step.get('scope')=='GENERAL' else step.get('delegations',{}).get(row.destination_id if step.get('scope')=='DESTINATION' else row.delegation_id)
    target=target or step.get('substitute')
    return target.get('user_id') if target else None


def planned_ids(row):
    return {user_id for step in row.workflow['steps'] if (user_id:=planned_user_id(row,step))}


def progress(row,events,names):
    definitions=row.workflow['steps']
    result=[]
    for index,step in enumerate(definitions):
        state='CURRENT' if row.status=='OPEN' and index==row.stage_index else 'REJECTED' if row.status=='REJECTED' and index==row.stage_index else 'COMPLETED' if index<row.stage_index or row.status=='CLOSED' and index==row.stage_index else 'NOT_EXECUTED' if row.status in {'CLOSED','REJECTED'} else 'PENDING'
        result.append({'name':step['name'],'kind':step['kind'],'state':state,'entered_at':None,'completed_at':None,'responsible_name':None,'planned_responsible_name':names.get(planned_user_id(row,step)),'completed_by':None,'visits':[]})
    cursor=None
    for entry in events:
        data=entry.detail or {};index=data.get('stage_index')
        if not isinstance(index,int) or not 0<=index<len(result):
            matches=[i for i,step in enumerate(definitions) if step['name']==data.get('stage')]
            index=matches[0] if len(matches)==1 else cursor if entry.action=='REASSIGNED' else None
        if index is None:continue  # Old duplicate names cannot be attributed reliably.
        item=result[index]
        if entry.action=='ASSIGNED':
            cursor=index
            item['visits'].append({'entered_at':utc(entry.created_at),'completed_at':None,'responsible_name':data.get('assignee_name') or names.get(data.get('assignee_id')),'completed_by':None})
        elif entry.action=='REASSIGNED':
            if item['visits']:item['visits'][-1]['responsible_name']=data.get('assignee_name') or names.get(data.get('assignee_id'))
        elif entry.action=='COMPLETED_STAGE':
            if not item['visits']:item['visits'].append({'entered_at':None,'responsible_name':None})
            item['visits'][-1].update(completed_at=utc(entry.created_at),completed_by=names.get(entry.actor_id))
    for index,item in enumerate(result):
        if item['visits']:item.update({key:item['visits'][-1].get(key) for key in ('entered_at','completed_at','responsible_name','completed_by')})
        if index==row.stage_index:
            if row.status=='OPEN':
                item['responsible_name']=names.get(row.assignee_id) or item['responsible_name']
                item['entered_at']=utc(row.entered_at) or item['entered_at']
                item['completed_at']=None;item['completed_by']=None
            item['due_at']=utc(row.due_at)
    return result
