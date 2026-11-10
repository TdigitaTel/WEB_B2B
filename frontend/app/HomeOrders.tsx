"use client";

import {useEffect, useState} from "react";
import {PickupSummaryView,type PickupSummary} from './OrderPickup';
import {useRefreshSeconds} from "./AutoRefresh";

type SummaryOrder = {pickup_summary?:PickupSummary|null;id:string;number:string;web_number?:string|null;origen_pedido?:string;store:string;job_name?:string|null;estado_registro_exit?:string|null};
const labels:Record<string,string>={BORRADOR:"Borrador",PENDIENTE:"Pendiente",BLOQUEADO:"En procesamiento",REGISTRADO:"En procesamiento",EN_PROCESO:"En procesamiento",EN_PREPARACION:"En procesamiento",ATENDIDO:"Pendiente de recogida",ENTREGADO:"Entregado",FACTURADO:"Facturado",ELIMINADO_EN_EXIT:"No se va a atender"};

export default function HomeOrders({load,onNavigate}:{load:(signal:AbortSignal)=>Promise<SummaryOrder[]>;onNavigate:()=>void}) {
  const refreshSeconds=useRefreshSeconds();
  const [orders,setOrders]=useState<SummaryOrder[]|null>(null);
  const [error,setError]=useState(false);
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    let busy=false;
    const refresh=async()=>{
      if(busy || document.visibilityState==="hidden")return;
      busy=true;
      try {
        const rows=await load(controller.signal);
        if(!controller.signal.aborted){setOrders(rows);setError(false);}
      } catch {
        if(!controller.signal.aborted)setError(true);
      } finally {busy=false;}
    };
    void refresh();
    const timer=window.setInterval(refresh,refreshSeconds*1000);
    window.addEventListener("focus",refresh);
    document.addEventListener("visibilitychange",refresh);
    return ()=>{controller.abort();window.clearInterval(timer);window.removeEventListener("focus",refresh);document.removeEventListener("visibilitychange",refresh);};
  },[load,retry,refreshSeconds]);
  const recent=(orders??[]).filter(order=>order.origen_pedido==="B2B"&&order.estado_registro_exit!=="ELIMINADO_EN_EXIT").sort((a,b)=>(b.web_number||b.number).localeCompare(a.web_number||a.number,"es",{numeric:true})).slice(0,5);
  return <>
    <div className="section-heading"><h2>Mis pedidos</h2><span className="count">{orders===null?"…":recent.length}</span></div>
    <p className="small">Tus últimos cinco pedidos WEB.</p>
    {orders===null&&!error&&<p className="small" role="status">Consultando pedidos…</p>}
    {recent.map(order=><div className="compact-order" key={order.id}><b>{order.web_number||order.number}</b><span className="small">{order.store} · {order.job_name||"Sin obra"}</span>{order.pickup_summary&&order.estado_registro_exit!=="ELIMINADO_EN_EXIT"?<PickupSummaryView summary={order.pickup_summary}/>:<span className="status">{labels[order.estado_registro_exit||"PENDIENTE"]||order.estado_registro_exit}</span>}</div>)}
    {error&&<p className="small" role="alert">No se pudieron actualizar los pedidos. <button className="text-button" onClick={()=>setRetry(value=>value+1)}>Reintentar</button></p>}
    {orders!==null&&!error&&!recent.length&&<p className="small">Todavía no tienes pedidos WEB.</p>}
    <button className="secondary block home-orders-button" onClick={onNavigate}>Ver todos mis pedidos →</button>
  </>;
}
