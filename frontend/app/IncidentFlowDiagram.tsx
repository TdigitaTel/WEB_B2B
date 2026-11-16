'use client';
import {activityLabels,type Flow,type Options,type Step} from './incidentTypes';
export function configuredResponsible(step:Step,options:Options){
 const person=(id:number)=>options.users.find(row=>row.id===id)?.name||'Responsable configurado';
 if(step.scope==='REQUESTER')return 'Solicitante de la incidencia';
 if(step.scope==='GENERAL')return step.general?person(step.general.user_id):'Falta asignar responsable';
 const assigned=Object.entries(step.delegations).map(([id,target])=>`${options.destinations.find(row=>row.id===id)?.name||id}: ${person(target.user_id)}`);
 return assigned.join(' · ')||(step.substitute?'Sustituto: '+person(step.substitute.user_id):'Falta asignar por delegación');
}
export default function IncidentFlowDiagram({flow,options,navigate=false}:{flow:Flow;options:Options;navigate?:boolean}){
 const close=flow.steps.findIndex(step=>step.kind==='CONFIRM');
 return <section className="incident-diagram" aria-label="Diagrama del flujo"><div className="incident-visual-title"><h3>Recorrido del flujo</h3><small>Orden de atención · Cada círculo es una etapa</small></div><ol className="incident-stepper incident-definition">{flow.steps.map((step,index)=>{const skipped=close>=0&&index>close;return <li className={skipped?'is-skipped':'is-defined'} key={index}><div className="incident-step-circle">{navigate?<button type="button" aria-label={`Ir a etapa ${index+1}: ${step.name}`} onClick={()=>document.getElementById('flow-stage-'+index)?.scrollIntoView({behavior:'smooth',block:'start'})}>{index+1}</button>:index+1}</div><div className="incident-step-content"><b>{step.name||'Etapa sin nombre'}</b><span className="incident-activity-badge">{activityLabels[step.kind]}</span><small>{configuredResponsible(step,options)}</small><small>{step.hours} h para atender</small>{skipped&&<span className="incident-step-state">No se ejecuta: hay un cierre anterior</span>}</div></li>})}</ol><p className="small">{navigate?'Pulsa un círculo para editar su etapa. ':''}Cerrar termina la incidencia; las etapas posteriores quedan fuera del recorrido.</p></section>;
}
