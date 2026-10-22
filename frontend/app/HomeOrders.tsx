"use client";

import {useEffect, useState} from "react";

type SummaryOrder = {id:string;number:string;store:string;job_name?:string|null;estado_registro_exit?:string};
const labels:Record<string,string>={BORRADOR:"Borrador",PENDIENTE:"Pendiente",BLOQUEADO:"En procesamiento",REGISTRADO:"En procesamiento",EN_PROCESO:"En procesamiento",EN_PREPARACION:"En procesamiento",ATENDIDO:"Pendiente de recogida",ENTREGADO:"Entregado"};

export default function HomeOrders({load,onNavigate}:{load:(signal:AbortSignal)=>Promise<SummaryOrder[]>;onNavigate:()=>void}) {
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
    const timer=window.setInterval(refresh,30000);
    window.addEventListener("focus",refresh);
    document.addEventListener("visibilitychange",refresh);
    return ()=>{controller.abort();window.clearInterval(timer);window.removeEventListener("focus",refresh);document.removeEventListener("visibilitychange",refresh);};
  },[load,retry]);
  const active=orders?.filter(order=>order.estado_registro_exit!=="FACTURADO")??[];
  return <>
    <div className="section-heading"><h2>Mis pedidos</h2><span className="count">{orders===null?"…":active.length}</span></div>
    <p className="small">El estado de tus últimas compras.</p>
    {orders===null&&!error&&<p className="small" role="status">Consultando pedidos…</p>}
    {active.slice(0,3).map(order=><div className="compact-order" key={order.id}><b>{order.number}</b><span className="small">{order.store} · {order.job_name||"Sin obra"}</span><span className="status">{labels[order.estado_registro_exit||"PENDIENTE"]||order.estado_registro_exit}</span></div>)}
    {error&&<p className="small" role="alert">No se pudieron actualizar los pedidos. <button className="text-button" onClick={()=>setRetry(value=>value+1)}>Reintentar</button></p>}
    {orders!==null&&!error&&!active.length&&<p className="small">No tienes pedidos activos.</p>}
    <button className="secondary block home-orders-button" onClick={onNavigate}>Ver todos mis pedidos →</button>
  </>;
}
