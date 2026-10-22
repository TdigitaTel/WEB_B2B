"use client";
import {deliveryDelay,delayLabel,type DeliveryTiming} from "./deliveryDeadline";

export default function OrderDeliveryDeadline({order,now}:{order:DeliveryTiming;now:number|null}){
  const {seconds,closed}=deliveryDelay(order,now);
  const deadline=Date.parse(order.attention_deadline_at||"");
  if(!Number.isFinite(deadline))return <span className="delivery-deadline"><small>Atender antes de</small><b>—</b></span>;
  const late=seconds!=null&&seconds>0;
  const label=new Date(deadline).toLocaleString("es-ES",{timeZone:"Europe/Madrid",day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"});
  return <span className={`delivery-deadline ${late?"is-overdue":""}`}><small>Atender antes de</small><b>{label}</b>{late?<strong>{closed?"Atendido con retraso: ":"Retraso: "}{delayLabel(seconds)}</strong>:closed?<small>{seconds===0?"Atendido dentro del plazo":"Atendido · sin hora de atención registrada"}</small>:seconds===0?<small>En plazo</small>:null}</span>;
}
