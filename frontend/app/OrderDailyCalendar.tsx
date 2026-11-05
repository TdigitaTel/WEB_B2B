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
export default function OrderDailyCalendar<T extends CalendarOrder>({delegation,renderOrders}:{delegation:string;renderOrders:(orders:T[],refresh:()=>Promise<void>)=>ReactNode}){
 const [day,setDay]=useState(()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Madrid'}).format(new Date()));
 const [orders,setOrders]=useState<T[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const version=useRef(0);
 async function load(signal?:AbortSignal){const request=++version.current;try{const res=await fetch(`/api/v1/store/order-calendar?${new URLSearchParams({day,delegation})}`,{credentials:'include',signal});const body=await res.json();if(!res.ok)throw Error(body.detail||'No se pudo consultar la agenda');if(!signal?.aborted&&request===version.current){setOrders(body.orders);setError('')}}catch(e){if(!signal?.aborted&&request===version.current)setError((e as Error).message)}finally{if(!signal?.aborted&&request===version.current)setLoading(false)}}
 useEffect(()=>{const controller=new AbortController();setLoading(true);setOrders([]);void load(controller.signal);return()=>controller.abort()},[day,delegation]);
 useAutoRefresh(signal=>load(signal),true,`${day}-${delegation}`);
 const groups=calendarGroups(orders);
 return <section className="order-daily-calendar" aria-label="Calendario diario de pedidos"><header><div><h2>Preparación del día</h2><p>Ordenados por franja de recogida. Los inmediatos se agrupan por su hora prevista. Dentro de cada franja aparecen primero los pendientes de preparar. Las fechas de creación del listado no limitan esta agenda.</p></div><label>Día<input type="date" aria-label="Día del calendario" value={day} onChange={e=>{if(e.target.value)setDay(e.target.value)}}/></label><button className="secondary" onClick={()=>void load()}>Actualizar agenda</button></header>{error&&<p className="error" role="alert">{error}</p>}{loading&&<p role="status">Consultando pedidos…</p>}{!loading&&!error&&!groups.length&&<p>No hay pedidos previstos para este día y delegación.</p>}{groups.map(group=><section className="calendar-time-group" key={group.label}><h3>{group.label}<span>{group.orders.length} pedidos</span></h3>{renderOrders(group.orders,()=>load())}</section>)}</section>
}
