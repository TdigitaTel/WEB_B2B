"""Compatibilidad de flujos antiguos sin imponer actividades a configuraciones nuevas."""
from copy import deepcopy


def requester(step):
    return step['scope']=='REQUESTER' or (step['kind']=='CONFIRM' and 'require_stock_verification' not in step)


def stock_verification(configuration,step):
    return step.get('require_stock_verification',configuration['kind']=='INVENTORY' and step['kind']=='EXECUTE')


def document_required(step):
    return step.get('require_document',False) or (step['kind']=='EXECUTE' and 'require_stock_verification' not in step)


def normalize(configuration):
    value=deepcopy(configuration)
    for step in value['steps']:
        if requester(step):step['scope']='REQUESTER'
        step['require_document']=document_required(step)
        step['require_stock_verification']=stock_verification(value,step)
    return value
