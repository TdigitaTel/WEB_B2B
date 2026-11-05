/** Cálculos puros para el plazo de entrega; las fechas incluyen zona horaria. */
export type DeliveryTiming = {
  pickup_slot_start?:string|null;
  pickup_slot_end?:string|null;
  pickup_summary?:{prepared_complete:boolean}|null;
  attention_deadline_at?: string|null;
  delivered_at?: string|null;
  attended_at?: string|null;
  estado_registro_exit?: string|null;
};

export function deliveryDelay(order:DeliveryTiming, now:number|null){
  const deadline=Date.parse(order.attention_deadline_at||"");
  const closed=order.pickup_summary?order.pickup_summary.prepared_complete:!!order.attended_at||["ATENDIDO","ENTREGADO","FACTURADO"].includes(order.estado_registro_exit||"");
  const end=closed?(order.pickup_summary?NaN:Date.parse(order.attended_at||"")):now;
  if(!Number.isFinite(deadline)||end==null||!Number.isFinite(end))return {seconds:null,closed};
  return {seconds:Math.max(0,Math.ceil((end-deadline)/1000)),closed};
}

export function delayLabel(seconds:number){
  const days=Math.floor(seconds/86400);
  const hours=Math.floor(seconds%86400/3600);
  const minutes=Math.floor(seconds%3600/60);
  const remaining=Math.floor(seconds%60);
  return `${days?`${days} d `:""}${hours.toString().padStart(2,"0")} h ${minutes.toString().padStart(2,"0")} min ${remaining.toString().padStart(2,"0")} s`;
}
