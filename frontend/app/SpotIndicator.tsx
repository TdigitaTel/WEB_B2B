"use client";
export type ConsumptionExceptionality={level:string;reasons:string[];observed_days:number;positive_days:number;consumption_day_percent:number;top3_share_percent:number;top_days:{day:string;quantity:number}[];largest_quantity:number|null;largest_date:string|null;outlier_days:number};
export type SpotSummary={status:string;flagged_share_percent?:number;positive_days?:number;single_consumption?:{day:string;quantity:number}|null};
export default function SpotIndicator({analysis,exceptionality,onReview}:{analysis?:SpotSummary;exceptionality?:ConsumptionExceptionality;onReview?:()=>void}){
 if(exceptionality){
  const labels:Record<string,string>={HIGH:'Alta excepcionalidad · revisar',MEDIUM:'Consumo poco frecuente · revisar',LOW:'Sin señales de excepcionalidad',LIMITED_HISTORY:'Periodo corto · interpretación limitada',NO_CONSUMPTION:'Sin consumo positivo'};
  const flags:Record<string,string>={CONCENTRATION:'Concentrado en pocos días',LOW_FREQUENCY:'Baja frecuencia',OUTLIERS:'Picos atípicos',FEW_ACTIVE_DAYS:'Pocos días con consumo',SHORT_PERIOD:'Menos de 30 días observados'};
  const fmt=(n:number)=>n.toLocaleString('es-ES',{maximumFractionDigits:1});
  const content=<><b>{labels[exceptionality.level]||'Excepcionalidad sin analizar'}</b><small>{exceptionality.positive_days} de {exceptionality.observed_days} días con consumo ({fmt(exceptionality.consumption_day_percent)} %).</small><small>Los {exceptionality.top_days.length} mayores días concentran {fmt(exceptionality.top3_share_percent)} % del consumo.</small>{exceptionality.reasons.length>0&&<small>{exceptionality.reasons.map(key=>flags[key]||key).join(' · ')}</small>}{onReview&&<small className="repl-spot-review">Ver análisis →</small>}</>;
  const props={className:`repl-spot-indicator ${exceptionality.level==='HIGH'?'warning':exceptionality.level==='MEDIUM'||exceptionality.level==='LIMITED_HISTORY'?'pending':'neutral'}`,'data-exceptionality-level':exceptionality.level};
  return onReview?<button type="button" {...props} onClick={onReview}>{content}</button>:<span {...props}>{content}</span>;
 }
 const status=analysis?.positive_days===1?'SINGLE_CONSUMPTION':analysis?.status||'NOT_ANALYZED';
 const labels:Record<string,{label:string;description:string;tone:string}>={
  SINGLE_CONSUMPTION:{label:'Consumo único · revisar',description:analysis?.single_consumption?`${analysis.single_consumption.quantity.toLocaleString('es-ES')} unidades en un solo día (${analysis.single_consumption.day.split('-').reverse().join('/')}). No demuestra recurrencia; revisar antes de reponer.`:'Solo un día con consumo positivo. No demuestra recurrencia; revisar antes de reponer.',tone:'warning'},
  POSSIBLE_SPOT:{label:'⚠ Posible spot · revisar',description:`Los días atípicos concentran ${(analysis?.flagged_share_percent??0).toLocaleString('es-ES',{maximumFractionDigits:1})} % del consumo neto. No se ha excluido ninguna venta.`,tone:'warning'},
  NO_OUTLIERS:{label:'Sin picos atípicos detectados',description:'No se superó el umbral de revisión. Esto no confirma que todas las ventas sean recurrentes.',tone:'neutral'},
  INSUFFICIENT:{label:'Histórico insuficiente para detectar spot',description:'Se necesitan al menos 8 días con consumo positivo para aplicar la regla.',tone:'pending'},
  NO_CONSUMPTION:{label:'Sin consumo para analizar spot',description:'No hay consumo neto positivo en el periodo.',tone:'neutral'},
  NOT_ANALYZED:{label:'Excepcionalidad sin analizar',description:'Este cálculo no incluye el análisis spot. Genera un cálculo nuevo para verlo en el listado.',tone:'pending'}
 };
 const state=labels[status]||labels.NOT_ANALYZED;
 const content=<><b>{state.label}</b><small>{state.description}</small>{onReview&&<small className="repl-spot-review">Ver datos del material →</small>}</>;
 const props={className:`repl-spot-indicator ${state.tone}`,'data-spot-status':status};
 return onReview?<button type="button" {...props} onClick={onReview}>{content}</button>:<span {...props}>{content}</span>;
}
