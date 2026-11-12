"use client";
export type SpotSummary={status:string;flagged_share_percent?:number};
export default function SpotIndicator({analysis,onReview}:{analysis?:SpotSummary;onReview?:()=>void}){
 const status=analysis?.status||'NOT_ANALYZED';
 const labels:Record<string,{label:string;description:string;tone:string}>={
  POSSIBLE_SPOT:{label:'⚠ Posible spot · revisar',description:`Los días atípicos concentran ${(analysis?.flagged_share_percent??0).toLocaleString('es-ES',{maximumFractionDigits:1})} % del consumo neto. No se ha excluido ninguna venta.`,tone:'warning'},
  NO_OUTLIERS:{label:'Sin picos atípicos detectados',description:'No se superó el umbral de revisión. Esto no confirma que todas las ventas sean recurrentes.',tone:'neutral'},
  INSUFFICIENT:{label:'Histórico insuficiente para detectar spot',description:'Se necesitan al menos 8 días con consumo positivo para aplicar la regla.',tone:'pending'},
  NO_CONSUMPTION:{label:'Sin consumo para analizar spot',description:'No hay consumo neto positivo en el periodo.',tone:'neutral'},
  NOT_ANALYZED:{label:'Spot sin analizar',description:'Este cálculo no incluye el análisis spot. Genera un cálculo nuevo para verlo en el listado.',tone:'pending'}
 };
 const state=labels[status]||labels.NOT_ANALYZED;
 const content=<><b>{state.label}</b><small>{state.description}</small>{onReview&&<small className="repl-spot-review">Ver datos del material →</small>}</>;
 const props={className:`repl-spot-indicator ${state.tone}`,'data-spot-status':status};
 return onReview?<button type="button" {...props} onClick={onReview}>{content}</button>:<span {...props}>{content}</span>;
}
