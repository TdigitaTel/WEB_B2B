"use client";
import type {Spot} from './ReplenishmentHistory';
import type {ConsumptionExceptionality} from './SpotIndicator';
const number=(n:number)=>n.toLocaleString('es-ES',{maximumFractionDigits:2});
const pct=(n:number)=>n.toLocaleString('es-ES',{maximumFractionDigits:1});
const bounded=(n:number)=>Math.max(0,Math.min(100,n));
export default function ConsumptionAnalysis({analysis:a,exceptionality:e,positiveDays,observedDays,unit}:{analysis?:Spot;exceptionality?:ConsumptionExceptionality;positiveDays:number;observedDays:number;unit:string}){
 const peaksAnalyzed=!!a&&['POSSIBLE_SPOT','NO_OUTLIERS'].includes(a.status);
 const peaks=a?.status==='POSSIBLE_SPOT'?a.outliers.length:0;
 const share=peaks?a!.flagged_share_percent:0;
 const concentration=!!e?.reasons.includes('CONCENTRATION');
 const highImpact=peaks>0&&share>=(e?.high_impact_threshold_percent??25);
 const lowFrequency=observedDays>0&&positiveDays/observedDays<=0.1;
 const single=positiveDays===1;
 const limited=observedDays<30||positiveDays<8;
 const tone=single||concentration||highImpact?'review':limited||lowFrequency?'limited':'normal';
 const title=positiveDays===0?'Sin consumo':single?'Un solo día con consumo':concentration?'Consumo concentrado en pocos días':highImpact?'Los picos pesan en el promedio':limited?'Pocos datos para evaluar':lowFrequency?'Consumo poco frecuente':peaks?'Picos de bajo impacto':'Sin picos relevantes detectados';
 const reason=positiveDays===0?'No hay demanda positiva en este periodo.':single?'No hay recurrencia demostrada. Confirma si volverá a necesitarse.':concentration?`Los ${e!.top_days.length} mayores días reúnen el ${pct(e!.top3_share_percent)} % del consumo.`:highImpact?`${peaks} días concentran el ${pct(share)} % del consumo. Revisa si corresponden a necesidades puntuales.`:limited?'Amplía el histórico antes de concluir si el consumo es habitual o puntual.':lowFrequency?'Hay consumo en el 10 % de los días o menos. Confirma la frecuencia esperada antes de reponer.':peaks?`Los picos representan el ${pct(share)} % del consumo; por sí solos no indican una compra puntual.`:'Esta regla no encuentra picos; revisa también la frecuencia de consumo.';
 const recurrence=observedDays?positiveDays/observedDays*100:0;
 const current=a?.daily_mean,without=a?.daily_mean_without_peaks;
 const comparison=peaks>0&&current!=null&&without!=null;
 const maximum=Math.max(current??0,without??0,0.001);
 return <section className={`repl-consumption-analysis ${tone}`} aria-label="Resumen visual del consumo">
  <header><div><span className="repl-analysis-eyebrow">ANÁLISIS DEL CONSUMO</span><h4>{title}</h4></div><span className="repl-analysis-status">{tone==='review'?'⚑ Revisar':tone==='limited'?(limited?'◌ Datos limitados':'⚑ Revisar frecuencia'):'● Informativo'}</span></header>
  <p className="repl-analysis-verdict">{reason}</p>
  <div className="repl-analysis-cards">
   <div><span>Habitual · mediana</span><strong>{a?.normal_daily_median==null?'—':number(a.normal_daily_median)} <small>{unit}/día con consumo</small></strong><small>Solo días con consumo positivo</small></div>
   <div><span>Días con consumo</span><strong>{positiveDays} <small>de {observedDays}</small></strong><small>{pct(recurrence)} % de los días del periodo</small></div>
   <div><span>Días con picos</span><strong>{peaksAnalyzed?peaks:'—'} <small>{peaks?`de ${positiveDays} con consumo`:limited?'Sin base suficiente':'detectados'}</small></strong><small>{peaks?`Superan ${number(a!.upper_threshold!)} ${unit}/día`:a?.status==='SINGLE_CONSUMPTION'?'Consumo único; sin clasificar picos':'Según el umbral de revisión'}</small></div>
  </div>
  <div className="repl-analysis-visuals">
   <div className="repl-analysis-panel"><b>Frecuencia de consumo</b><div className="repl-analysis-stack" role="img" aria-label={`${positiveDays} días con consumo de ${observedDays}`}><i style={{width:`${bounded(recurrence)}%`}}/></div><div className="repl-analysis-keys"><span>● Con consumo: {positiveDays} días</span><span>○ Sin consumo: {Math.max(0,observedDays-positiveDays)} días</span></div>
   {peaks>0&&<><b>Cuánto pesan los picos</b><div className="repl-analysis-stack impact" role="img" aria-label={`Picos: ${pct(share)} por ciento del consumo`}><i style={{width:`${bounded(share)}%`}}/></div><div className="repl-analysis-keys"><span>▲ Picos: {pct(share)} % · {number(a!.flagged_quantity)} {unit}</span><span>Resto: {pct(100-share)} %</span></div></>}
   {concentration&&!peaks&&<p><strong>{pct(e!.top3_share_percent)} %</strong> del consumo en los {e!.top_days.length} mayores días.</p>}
   </div>
   {comparison&&<div className="repl-analysis-panel"><b>Impacto sobre la media diaria</b><div className="repl-mean-comparison"><span>Con todas las ventas</span><strong>{number(current!)} {unit}/día</strong><div className="repl-analysis-bar current" style={{width:`${bounded(current!/maximum*100)}%`}}/><span>Sin cantidades de los picos</span><strong>{number(without!)} {unit}/día</strong><div className="repl-analysis-bar baseline" style={{width:`${bounded(without!/maximum*100)}%`}}/></div><p className="repl-analysis-impact">{a!.mean_uplift_percent==null?'Sin base para comparar el aumento':`Los picos elevan la media un ${pct(a!.mean_uplift_percent)} %`}</p><small>Comparación orientativa; conserva los mismos días.</small></div>}
  </div>
  <footer><b>Para decidir la reposición:</b> {tone==='review'?'confirma si esas cantidades se repetirán.':'combina consumo, stock y plazo de suministro.'} No se excluyen ventas ni se cambia la propuesta automáticamente.</footer>
 </section>
}
