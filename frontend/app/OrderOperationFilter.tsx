"use client";
export type OperationFilter='POR_ATENDER'|'ATENDIDO';
type OperationOrder={estado_registro_exit?:string|null;pickup_summary?:{prepared_complete?:boolean;state?:string}|null};
export function operationGroup(order:OperationOrder):OperationFilter{
 const raw=(order.estado_registro_exit||'').toUpperCase(),summary=order.pickup_summary;
 // Invoiced and delivered orders belong to the attended group, including their substates.
 if(raw==='FACTURADO'||raw.startsWith('ENTREGADO')||summary?.state?.startsWith('ENTREGADO'))return 'ATENDIDO';
 if(summary)return summary.prepared_complete||summary.state==='PENDIENTE_RECOGIDA_TOTAL'?'ATENDIDO':'POR_ATENDER';
 return ['ATENDIDO','PREPARADO','PENDIENTE_RECOGIDA','PENDIENTE_RECOJO','PENDIENTE_RECOGIDA_TOTAL'].includes(raw)?'ATENDIDO':'POR_ATENDER';
}
export default function OrderOperationFilter({value,onChange}:{value:OperationFilter;onChange:(value:OperationFilter)=>void}){
 return <label>Operación<select aria-label="Estado de la operación" value={value} onChange={event=>onChange(event.target.value as OperationFilter)}><option value="POR_ATENDER">Por atender</option><option value="ATENDIDO">Atendido</option></select></label>
}
