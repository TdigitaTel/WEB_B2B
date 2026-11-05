"use client";
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {useAutoRefresh} from './AutoRefresh';
import './order-calendar.css';
type CalendarOrder={id:string;pickup_date?:string|null;pickup_slot_start?:string|null;pickup_slot_end?:string|null;attention_deadline_at?:string|null;estado_registro_exit?:string|null;pickup_summary?:{prepared_complete:boolean;state?:string}|null};
export function calendarGroups<T extends CalendarOrder>(orders:T[]){
 const groups=new Map<string,{label:string;sort:string;orders:T[]}>();
 for(const order of orders){let key='UNASSIGNED',label='Programados sin franja',sort='99:99';
  if(order.pickup_slot_start&&order.pickup_slot_end){key=`S-${order.pickup_slot_start}-${order.pickup_slot_end}`;label=`${order.pickup_slot_start} – ${order.pickup_slot_end}`;sort=order.pickup_slot_start;}
  else if(!order.pickup_date&&order.attention_deadline_at){const date=new Date(order.attention_deadline_at);if(Number.isFinite(date.getTime())){const hour=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Madrid',hour:'2-digit',hourCycle:'h23'}).format(date);key=`I-${hour}`;label=`${hour}:00 – ${String(Number(hour)+1).padStart(2,'0')}:00 · Inmediatos`;sort=`${hour}:00`;}}
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
const orderDay=(order:CalendarOrder)=>order.pickup_date||(order.attention_deadline_at&&Number.isFinite(Date.parse(order.attention_deadline_at))?calendarDate(new Date(order.attention_deadline_at)):'');
const dayTitle=(day:string)=>new Intl.DateTimeFormat('es-ES',{timeZone:'UTC',weekday:'long',day:'2-digit',month:'2-digit'}).format(new Date(`${day}T12:00:00Z`));
export default function OrderDailyCalendar<T extends CalendarOrder>({delegation,renderOrders}:{delegation:string;renderOrders:(orders:T[],refresh:()=>Promise<void>)=>ReactNode}){
 const [range,setRange]=useState(()=>calendarWeek()),[selected,setSelected]=useState(()=>calendarDate(new Date()));
 const [orders,setOrders]=useState<T[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const version=useRef(0),days=calendarDays(range.from,range.to);
 async function load(signal?:AbortSignal){const request=++version.current;if(!days.length){setError('Selecciona un rango de uno a siete días.');setLoading(false);return;}try{const res=await fetch(`/api/v1/store/order-calendar?${new URLSearchParams({date_from:range.from,date_to:range.to,delegation})}`,{credentials:'include',signal});const body=await res.json();if(!res.ok)throw Error(body.detail||'No se pudo consultar la agenda');if(!signal?.aborted&&request===version.current){setOrders(body.orders);setError('')}}catch(e){if(!signal?.aborted&&request===version.current)setError((e as Error).message)}finally{if(!signal?.aborted&&request===version.current)setLoading(false)}}
 useEffect(()=>{const controller=new AbortController();setLoading(true);setOrders([]);void load(controller.signal);return()=>controller.abort()},[range.from,range.to,delegation]);
 useAutoRefresh(signal=>load(signal),true,`${range.from}-${range.to}-${delegation}`);
 const activeDay=days.includes(selected)?selected:range.from;
 const groups=calendarGroups(orders.filter(order=>orderDay(order)===activeDay));
 return <section className="order-daily-calendar" aria-label="Calendario semanal de pedidos"><header><div><h2>Calendario de preparación</h2><p>Hasta siete días. Selecciona un día para gestionar sus pedidos por franja horaria, con los pendientes de preparar primero.</p></div><label>Desde<input type="date" aria-label="Desde del calendario" value={range.from} onChange={e=>{if(e.target.value){setRange({from:e.target.value,to:shiftCalendarDate(e.target.value,6)});setSelected(e.target.value)}}}/></label><label>Hasta<input type="date" aria-label="Hasta del calendario" min={range.from} max={shiftCalendarDate(range.from,6)} value={range.to} onChange={e=>{if(e.target.value)setRange(old=>({...old,to:e.target.value}))}}/></label><button className="secondary" onClick={()=>{setRange(calendarWeek());setSelected(calendarDate(new Date()))}}>Semana actual</button><button className="secondary" disabled={!days.length} onClick={()=>void load()}>Actualizar agenda</button></header>{error&&<p className="error" role="alert">{error}</p>}<div className="calendar-week-grid" role="group" aria-label="Días del calendario">{days.map(day=>{const rows=orders.filter(order=>orderDay(order)===day),slots=calendarGroups(rows);return <button type="button" className="calendar-day" key={day} aria-pressed={day===activeDay} onClick={()=>setSelected(day)}><time dateTime={day}>{dayTitle(day)}</time><strong>{loading?'…':`${rows.length} pedidos`}</strong>{!loading&&!slots.length&&<small>Sin pedidos</small>}{slots.map(slot=><span className="calendar-slot-count" key={slot.label}>{slot.label} · {slot.orders.length}</span>)}</button>})}</div>{loading&&<p role="status">Consultando pedidos…</p>}{days.length>0&&<h3 className="calendar-selected-day">{dayTitle(activeDay)}</h3>}{!loading&&!error&&!groups.length&&<p>No hay pedidos previstos para este día y delegación.</p>}{groups.map(group=><section className="calendar-time-group" key={group.label}><h3>{group.label}<span>{group.orders.length} pedidos</span></h3>{renderOrders(group.orders,()=>load())}</section>)}</section>
}
