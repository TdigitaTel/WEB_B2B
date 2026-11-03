"use client";
import {FormEvent,useState} from "react";
import {localDate,madridStamp} from "./madridDateTime";
import "./order-planning-editor.css";
type Order={pickup_summary?:{legacy_delivery:boolean;prepared_complete:boolean;total_materials:number}|null;id:string;attention_deadline_at?:string|null;notes?:string|null;delivered_at?:string|null;attended_at?:string|null;estado_registro_exit?:string|null};
export default function OrderPlanningEditor({order,onSaved}:{order:Order;onSaved:()=>Promise<void>}){
 const [editing,setEditing]=useState(false),[date,setDate]=useState(''),[observations,setObservations]=useState('');
 const [original,setOriginal]=useState<{date:string|null;notes:string|null}>({date:null,notes:null}),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const partiallyPending=order.pickup_summary&&!order.pickup_summary.legacy_delivery&&!order.pickup_summary.prepared_complete&&order.pickup_summary.total_materials>0;
 const closed=!partiallyPending&&(!!order.delivered_at||!!order.attended_at||['ATENDIDO','ENTREGADO','FACTURADO'].includes(order.estado_registro_exit||''));
 async function save(event:FormEvent){event.preventDefault();if(busy)return;setBusy(true);setError('');try{
  const response=await fetch(`/api/v1/store/orders/${encodeURIComponent(order.id)}/planning`,{method:'PATCH',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_at:madridStamp(date),observations,previous_expected_at:original.date,previous_observations:original.notes})});
  if(response.status===401)window.dispatchEvent(new Event('session-expired'));
  const result=await response.json().catch(()=>null);
  if(!response.ok)throw Error(typeof result?.detail==='string'?result.detail:'No se pudo guardar la previsión');
  setEditing(false);await onSaved();
 }catch(error){setError((error as Error).message)}finally{setBusy(false)}}
 return <div className="order-planning-editor">{!closed&&(editing?<form onSubmit={save}><h3>Previsión y observaciones del pedido</h3><label>Fecha y hora previstas<input aria-label="Fecha y hora previstas del pedido" type="datetime-local" required value={date} disabled={busy} onChange={event=>setDate(event.target.value)}/></label><label>Observaciones del pedido<textarea aria-label="Observaciones del pedido" rows={3} maxLength={1000} value={observations} disabled={busy} onChange={event=>setObservations(event.target.value)}/></label><p className="small">Hora de España peninsular. Las entregas de cada artículo se editan en «Editar entregas previstas».</p><div><button className="primary" type="submit" disabled={busy}>{busy?'Guardando…':'Guardar cabecera'}</button><button className="ghost" type="button" disabled={busy} onClick={()=>{setEditing(false);setError('')}}>Cancelar</button></div></form>:<button className="secondary" type="button" onClick={()=>{setOriginal({date:order.attention_deadline_at||null,notes:order.notes??null});setDate(localDate(order.attention_deadline_at));setObservations(order.notes||'');setError('');setEditing(true)}}>Editar fecha prevista y observaciones</button>)}{!editing&&order.notes&&<p className="order-header-observation"><b>Observaciones del pedido:</b> {order.notes}</p>}{error&&<p className="error" role="alert">{error}</p>}</div>;
}
