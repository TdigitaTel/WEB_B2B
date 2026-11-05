"use client";
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {useAutoRefresh} from './AutoRefresh';
import './order-calendar.css';
type CalendarOrder={id:string;number?:string;web_number?:string|null;exit_order_number?:string|null;nro_pedido_exit?:string|null;customer?:string;store?:string;calendar_date?:string|null;calendar_slot_start?:string|null;calendar_slot_end?:string|null;calendar_time_source?:string;pickup_date?:string|null;pickup_slot_start?:string|null;pickup_slot_end?:string|null;attention_deadline_at?:string|null;estado_registro_exit?:string|null;pickup_summary?:{prepared_complete:boolean;state?:string}|null};
export function calendarGroups<T extends CalendarOrder>(orders:T[]){
 const groups=new Map<string,{label:string;sort:string;orders:T[]}>();
 for(const order of orders){let key='UNASSIGNED',label='Programados sin franja',sort='99:99';
  const slot=appointmentWindow(order);
  if(slot){key=`S-${slot.start}-${slot.end}`;label=`${slot.start} – ${slot.end} · Franja reservada`;sort=slot.start;}
  else if(order.attention_deadline_at){const date=new Date(order.attention_deadline_at);if(Number.isFinite(date.getTime())){const hour=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Madrid',hour:'2-digit',hourCycle:'h23'}).format(date);key=`I-${hour}`;label=`${hour}:00 – ${String(Number(hour)+1).padStart(2,'0')}:00 · ${order.pickup_date?'Hora prevista':'Inmediatos'}`;sort=`${hour}:00`;}}
  if(!groups.has(key))groups.set(key,{label,sort,orders:[]});groups.get(key)!.orders.push(order);
 }
 const priority=(order:T)=>order.pickup_summary?.state==='ENTREGADO_TOTAL'||(!order.pickup_summary&&['ENTREGADO','FACTURADO'].includes(order.estado_registro_exit||''))?2:order.pickup_summary?.prepared_complete||order.estado_registro_exit==='ATENDIDO'?1:0;
 for(const group of groups.values())group.orders.sort((a,b)=>priority(a)-priority(b)||(a.attention_deadline_at||'').localeCompare(b.attention_deadline_at||''));
 return [...groups.values()].sort((a,b)=>a.sort.localeCompare(b.sort)||a.label.localeCompare(b.label));
}
export const calendarDate=(now:Date)=>new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Madrid'}).format(now);
export function shiftCalendarDate(day:string,offset:number){const date=new Date(`${day}T12:00:00Z`);date.setUTCDate(date.getUTCDate()+offset);return date.toISOString().slice(0,10)}
export function calendarWeek(now=new Date()){const today=calendarDate(now),weekday=new Date(`${today}T12:00:00Z`).getUTCDay();const from=shiftCalendarDate(today,-((weekday+6)%7));return {from,to:shiftCalendarDate(from,6)}}
export function calendarDays(from:string,to:string){const days:string[]=[];if(!from||!to||to<from||to>shiftCalendarDate(from,6))return days;for(let day=from;day<=to;day=shiftCalendarDate(day,1))days.push(day);return days}
export const orderDay=(order:CalendarOrder)=>order.calendar_date||(order.attention_deadline_at&&Number.isFinite(Date.parse(order.attention_deadline_at))?calendarDate(new Date(order.attention_deadline_at)):order.pickup_date||'');
function appointmentWindow(order:CalendarOrder){
 if(order.calendar_time_source)return order.calendar_slot_start&&order.calendar_slot_end?{start:order.calendar_slot_start,end:order.calendar_slot_end}:null;
 const time=order.attention_deadline_at&&Number.isFinite(Date.parse(order.attention_deadline_at))?new Date(order.attention_deadline_at).toLocaleTimeString('en-GB',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}):null;
 return order.pickup_date===orderDay(order)&&order.pickup_slot_start&&order.pickup_slot_end&&(!time||(order.pickup_slot_start<=time&&time<=order.pickup_slot_end))?{start:order.pickup_slot_start,end:order.pickup_slot_end}:null;
}
export function calendarError(detail:unknown,status:number){
 if(typeof detail==='string')return detail;
 if(Array.isArray(detail)){const fields=detail.map(item=>item&&typeof item==='object'&&Array.isArray(item.loc)?item.loc.at(-1):'').filter(Boolean);return `No se pudo consultar el calendario: revisa las fechas y la delegación${fields.length?` (${fields.join(', ')})`:''}. Código ${status}.`;}
 if(detail&&typeof detail==='object'&&'message' in detail&&typeof detail.message==='string')return detail.message;
 return `No se pudo consultar el calendario (código ${status}). Reintenta o revisa la versión del servidor.`;
}
const needsDailyApi=(detail:unknown,status:number)=>status===422&&Array.isArray(detail)&&detail.some(item=>item&&Array.isArray(item.loc)&&item.loc.join('.')==='query.day'&&['missing','value_error.missing'].includes(item.type));
const orderNumber=(order:CalendarOrder)=>order.exit_order_number||order.nro_pedido_exit||order.web_number||order.number||order.id;
function appointmentLabel(order:CalendarOrder){const slot=appointmentWindow(order);if(slot)return `Franja reservada: ${slot.start} – ${slot.end}`;return order.attention_deadline_at?`Hora prevista: ${new Date(order.attention_deadline_at).toLocaleTimeString('es-ES',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit'})}`:'Sin hora confirmada';}
export function calendarStartHour(order:CalendarOrder){
 const slot=appointmentWindow(order);if(slot)return Number(slot.start.slice(0,2));
 if(order.attention_deadline_at&&Number.isFinite(Date.parse(order.attention_deadline_at)))return Number(new Date(order.attention_deadline_at).toLocaleTimeString('en-GB',{timeZone:'Europe/Madrid',hour:'2-digit',hourCycle:'h23'}));
 return null;
}
export function calendarTimeRows(orders:CalendarOrder[]){
 const hours=orders.map(calendarStartHour).filter((hour):hour is number=>hour!==null);
 const from=Math.min(7,...hours),to=Math.max(20,...hours.map(hour=>hour+1));
 const rows=Array.from({length:to-from},(_,index)=>({key:String(from+index),label:`${String(from+index).padStart(2,'0')}:00`}));
 return orders.some(order=>calendarStartHour(order)===null)?[{key:'none',label:'Sin hora'},...rows]:rows;
}
function eventState(order:CalendarOrder){const state=order.pickup_summary?.state||order.estado_registro_exit||'PENDIENTE';if(state==='ENTREGADO_PARCIAL')return 'Entregado parcial';if(state.startsWith('ENTREGADO'))return 'Entregado';if(state==='FACTURADO')return 'Facturado';if(order.pickup_summary?.prepared_complete||state==='ATENDIDO')return 'Preparado';if(state==='PENDIENTE_RECOGIDA_PARCIAL')return 'Preparación parcial';if(state==='PENDIENTE')return 'Pendiente';return 'En preparación';}
const dayTitle=(day:string)=>new Intl.DateTimeFormat('es-ES',{timeZone:'UTC',weekday:'long',day:'2-digit',month:'2-digit'}).format(new Date(`${day}T12:00:00Z`));
export default function OrderDailyCalendar<T extends CalendarOrder>({delegation,renderOrders,onOpenOrder}:{delegation:string;renderOrders?:(orders:T[],refresh:()=>Promise<void>)=>ReactNode;onOpenOrder?:(order:T)=>void}){
 const [range,setRange]=useState(()=>calendarWeek()),[selected,setSelected]=useState(()=>calendarDate(new Date())),[preview,setPreview]=useState<T|null>(null);
 const [orders,setOrders]=useState<T[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true),[compatibility,setCompatibility]=useState(false);
 const version=useRef(0),days=calendarDays(range.from,range.to);
 async function load(signal?:AbortSignal){
  const request=++version.current;if(!days.length){setError('Selecciona un rango de uno a siete días.');setLoading(false);return;}
  async function fetchCalendar(query:URLSearchParams){const res=await fetch(`/api/v1/store/order-calendar?${query}`,{credentials:'include',signal});if(res.status===401)window.dispatchEvent(new Event('session-expired'));let body;try{body=await res.json()}catch{throw Error(`El servidor no devolvió una respuesta válida (${res.status}).`)}return {res,body};}
  try{let {res,body}=await fetchCalendar(new URLSearchParams({date_from:range.from,date_to:range.to,delegation}));let compatible=false;
   if(needsDailyApi(body.detail,res.status)){
    const collected:T[]=[];for(const day of days){const daily=await fetchCalendar(new URLSearchParams({day,delegation}));if(!daily.res.ok)throw Error(calendarError(daily.body.detail,daily.res.status));if(!Array.isArray(daily.body.orders))throw Error('La respuesta del calendario no contiene una lista de pedidos.');collected.push(...daily.body.orders);}
    body={orders:[...new Map(collected.map(order=>[order.id,order])).values()]};compatible=true;
   }else if(!res.ok)throw Error(calendarError(body.detail,res.status));
   if(!Array.isArray(body.orders))throw Error('La respuesta del calendario no contiene una lista de pedidos.');
   if(!signal?.aborted&&request===version.current){setOrders(body.orders);setCompatibility(compatible);setError('')}
  }catch(e){if(!signal?.aborted&&request===version.current)setError(e instanceof Error?e.message:'No se pudo consultar el calendario.')}finally{if(!signal?.aborted&&request===version.current)setLoading(false)}
 }
 useEffect(()=>{const controller=new AbortController();setLoading(true);setOrders([]);void load(controller.signal);return()=>controller.abort()},[range.from,range.to,delegation]);
 useAutoRefresh(signal=>load(signal),true,`${range.from}-${range.to}-${delegation}`);
 const activeDay=days.includes(selected)?selected:range.from;
 const visibleOrders=orders.filter(order=>days.includes(orderDay(order))),timeRows=calendarTimeRows(visibleOrders);
 const cells=new Map<string,T[]>();
 for(const order of visibleOrders){const key=`${orderDay(order)}|${calendarStartHour(order)??'none'}`;if(!cells.has(key))cells.set(key,[]);cells.get(key)!.push(order)}
 for(const [key,rows] of cells)cells.set(key,calendarGroups(rows).flatMap(group=>group.orders));
 const today=calendarDate(new Date());
 function openOrder(order:T){if(onOpenOrder)onOpenOrder(order);else setPreview(order)}
 return <section className="order-daily-calendar" aria-label="Calendario semanal de pedidos"><header><div><h2>Calendario de pedidos</h2><p>Pedidos por día y hora prevista de recogida o entrega. Pulsa un pedido para abrir su detalle.</p></div><label>Desde<input type="date" aria-label="Desde del calendario" value={range.from} onChange={e=>{if(e.target.value){setRange({from:e.target.value,to:shiftCalendarDate(e.target.value,6)});setSelected(e.target.value)}}}/></label><label>Hasta<input type="date" aria-label="Hasta del calendario" min={range.from} max={shiftCalendarDate(range.from,6)} value={range.to} onChange={e=>{if(e.target.value)setRange(old=>({...old,to:e.target.value}))}}/></label><button className="secondary" onClick={()=>{setRange(calendarWeek());setSelected(calendarDate(new Date()))}}>Semana actual</button><button className="secondary" disabled={!days.length} onClick={()=>void load()}>Actualizar agenda</button></header>{error&&<p className="error" role="alert">{error}</p>}{compatibility&&!error&&<p role="status">Consulta compatible con la versión diaria anterior. Completa la actualización de la API para incluir todas las previsiones modificadas.</p>}<div className="calendar-legend"><span><i className="reserved"/>Franja reservada</span><span><i className="estimated"/>Hora estimada</span><small>Europe/Madrid</small></div><div className="calendar-week-grid calendar-timetable-scroll" role="region" aria-label="Calendario por días y horas" tabIndex={0}><table className="calendar-timetable" style={{minWidth:60+days.length*150}}><thead><tr><th className="calendar-corner" scope="col">Hora</th>{days.map(day=><th className="calendar-day" data-selected={day===activeDay} data-today={day===today} scope="col" key={day}><button className="calendar-day-select" type="button" aria-pressed={day===activeDay} onClick={()=>setSelected(day)}><time dateTime={day}>{dayTitle(day)}</time><small>{loading?'…':error&&!orders.length?'Sin datos':`${visibleOrders.filter(order=>orderDay(order)===day).length} pedidos`}</small></button></th>)}</tr></thead><tbody>{timeRows.map(row=><tr key={row.key}><th className="calendar-hour" scope="row">{row.label}</th>{days.map(day=><td data-day={day} data-hour={row.key} data-selected={day===activeDay} data-today={day===today} key={day}>{(cells.get(`${day}|${row.key}`)||[]).map(order=><button className={`calendar-order-shortcut calendar-event ${appointmentWindow(order)?'is-reserved':'is-estimated'}`} type="button" key={order.id} aria-label={`Abrir pedido ${orderNumber(order)}. ${order.customer||''}. ${appointmentLabel(order)}`} title={`${order.customer||''} · ${order.store||''} · ${appointmentLabel(order)}`} onClick={()=>openOrder(order)}><small className="calendar-event-time">{appointmentLabel(order).replace('Franja reservada: ','').replace('Hora prevista: ','')}</small><b>{orderNumber(order)}</b><span className="calendar-event-customer">{order.customer||order.store}</span><small className={`calendar-event-state ${eventState(order)==='Preparado'?'is-ready':eventState(order).startsWith('Entregado')||eventState(order)==='Facturado'?'is-done':''}`}>{eventState(order)}</small></button>)}</td>)}</tr>)}</tbody></table></div><span className="calendar-selected-day calendar-sr-only" aria-live="polite">{days.length?dayTitle(activeDay):''}</span>{loading&&<p role="status">Consultando pedidos…</p>}{!loading&&!error&&!visibleOrders.length&&<p>No hay pedidos previstos para este rango y delegación.</p>}{preview&&renderOrders&&<section className="calendar-clicked-detail"><button className="secondary" onClick={()=>setPreview(null)}>Cerrar detalle</button>{renderOrders([preview],()=>load())}</section>}</section>
}
