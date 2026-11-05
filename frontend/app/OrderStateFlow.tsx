'use client';
import {type PickupSummary,pickupLabels} from './OrderPickup';
import './order-state-flow.css';
export type StateFlowDate={etapa:string;completed_at:string|null;date_only?:boolean};
type Event={estado_registro_exit:string;created_at:string;date_only?:boolean};
const stages=['PENDIENTE','EN_PROCESAMIENTO','PENDIENTE_RECOJO','ENTREGADO','FACTURADO'];
const labels=['Pendiente','En procesamiento','Pendiente de recogida','Entregado','Facturado'];
export function mainStage(state:string){
 if(state.startsWith('PENDIENTE_RECOGIDA')||['ATENDIDO','PENDIENTE_RECOJO'].includes(state))return 'PENDIENTE_RECOJO';
 if(state.startsWith('ENTREGADO'))return 'ENTREGADO';
 if(['REGISTRADO','BLOQUEADO','EN_PROCESO','EN_PREPARACION','EN_PROCESAMIENTO'].includes(state))return 'EN_PROCESAMIENTO';
 return state==='BORRADOR'?'PENDIENTE':state
}
function stamp(value?:string|null){const n=value?Date.parse(value):NaN;return Number.isFinite(n)?n:null}
export default function OrderStateFlow({state,workflow=[],history=[],summary,registeredAt,deliveredAt}:{state?:string|null;workflow?:StateFlowDate[];history?:Event[];summary?:PickupSummary|null;registeredAt?:string|null;deliveredAt?:string|null}){
 const current=state==='ELIMINADO_EN_EXIT'?state:summary?.state||state||'PENDIENTE',stage=mainStage(current);
 const dates=new Map<string,{value:string;dateOnly?:boolean}>();
 function record(key:string,value?:string|null,dateOnly=false){const time=stamp(value);if(time==null)return;const previous=dates.get(key);if(!previous||time>=stamp(previous.value)!)dates.set(key,{value:value!,dateOnly})}
 for(const item of workflow)record(mainStage(item.etapa),item.completed_at,item.date_only);
 for(const item of history)record(mainStage(item.estado_registro_exit),item.created_at,item.date_only);
 if(!dates.has('EN_PROCESAMIENTO'))record('EN_PROCESAMIENTO',registeredAt);
 // A served/invoiced line is not proof of physical collection. Prefer the ledger.
 if(summary){dates.delete('ENTREGADO');if(!summary.legacy_delivery)record('ENTREGADO',summary.completed_at||summary.last_pickup_at)}
 else record('ENTREGADO',deliveredAt);
 const substate=current.endsWith('_PARCIAL')?'Parcial':current.endsWith('_TOTAL')?'Total':null;
 const currentLabel=pickupLabels[current]||({'BORRADOR':'Borrador','ELIMINADO_EN_EXIT':'No se va a atender'} as Record<string,string>)[current]||labels[stages.indexOf(stage)]||'En gestión';
 const isPartialDelivery=!!summary&&!summary.legacy_delivery&&summary.delivered_materials>0&&!summary.completed_at;
 return <section className="order-state-flow" aria-label="Estado del pedido y fechas"><header><h3>Estado del pedido</h3><strong className={`state-flow-current ${current==='ENTREGADO_TOTAL'?'is-complete':''}`}>{currentLabel}</strong></header><ol aria-label="Flujo de estados del pedido">{stages.map((key,index)=>{const date=dates.get(key),active=stage===key;const detail=active&&substate?substate:key==='ENTREGADO'&&isPartialDelivery?'Parcial':null;return <li key={key} className={`${active?'is-current':''} ${date?'has-date':''}`} aria-current={active?'step':undefined}><span className="state-flow-dot" aria-hidden="true">{index+1}</span><span className="state-flow-copy"><b>{labels[index]}</b>{detail&&<small className="state-flow-substate">{detail}</small>}{date?<time dateTime={date.value}>{new Intl.DateTimeFormat('es-ES',{timeZone:'Europe/Madrid',dateStyle:'short',...(date.dateOnly?{}:{timeStyle:'short'})}).format(new Date(date.value))}</time>:<small>Sin fecha registrada</small>}</span></li>})}</ol>{isPartialDelivery&&<p>La fecha de entrega corresponde a la última recogida parcial. La facturación no confirma la entrega total.</p>}</section>
}
