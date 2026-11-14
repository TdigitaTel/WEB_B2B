"""Alcance de delegaciones compartido por consultas, tareas y avisos."""
from .operator_permissions import can_operate_delegation


def allows(user,db,reference):
    if not reference:return False
    company,code=reference.split(':',1)
    return can_operate_delegation(user,db,int(company),code)


def includes(user,db,row):
    return allows(user,db,row.delegation_id) or bool(row.destination_id and allows(user,db,row.destination_id))


def task_reference(row,step):
    return row.destination_id if step['scope']=='DESTINATION' else row.delegation_id


def allows_task(user,db,row,step):
    return allows(user,db,task_reference(row,step))
