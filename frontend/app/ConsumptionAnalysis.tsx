"use client";
import {useState} from 'react';
import type {Spot} from './ReplenishmentHistory';
import type {ConsumptionExceptionality} from './SpotIndicator';
export type ConsumptionDay={day:string;demand:number};
const number=(n:number)=>n.toLocaleString('es-ES',{maximumFractionDigits:2});
const pct=(n:number)=>n.toLocaleString('es-ES',{maximumFractionDigits:1});
const bounded=(n:number)=>Math.max(0,Math.min(100,n));
const dateLabel=(date:string)=>date.split('-').reverse().join('/');
const BLUE='#236f98',ORANGE='#b96812',GREEN='#24805c',GREY='#dce7ee',RED='#b83d47';
const W=800,H=240,L=62,R=22,T=25,B=40,PW=W-L-R,PH=H-T-B;
export function orderedConsumption(days:ConsumptionDay[]){
 const positive=days.filter(d=>Number.isFinite(d.demand)&&d.demand>0).sort((a,b)=>a.demand-b.demand||a.day.localeCompare(b.day));
 const descending=[...positive].reverse(),total=positive.reduce((sum,d)=>sum+d.demand,0);
 let cumulative=0;
 const pareto=descending.map((d,index)=>{cumulative+=d.demand;return {...d,count:index+1,share:total?cumulative/total*100:0}});
 return {positive,pareto,total};
}
function Step({index,title,idea,children}:{index:number;title:string;idea:string;children:React.ReactNode}){
 return <section className="repl-stat-step"><header><span className="repl-stat-number" aria-hidden="true">{index}</span><h5>{title}</h5></header><p className="repl-stat-idea">{idea}</p>{children}</section>;
}
function Grid({min=0,max,unit}:{min?:number;max:number;unit:string}){
 return <>{[min,(max+min)/2,max].map((value,index)=>{const y=T+(max-value)/(max-min||1)*PH;return <g key={index}><line x1={L} x2={W-R} y1={y} y2={y} stroke="#d9e5ec"/><text x={L-8} y={y+4} textAnchor="end" fontSize="12" fill="#526b7b">{number(value)}</text></g>})}<text x={L} y={15} fontSize="12" fill="#526b7b">{unit}</text></>;
}
function Timeline({days,outliers,unit}:{days:ConsumptionDay[];outliers:Set<string>;unit:string}){
 const [hover,setHover]=useState<string|null>(null);
 const min=Math.min(0,...days.map(d=>d.demand)),max=Math.max(1,...days.map(d=>d.demand));
 const y=(v:number)=>T+(max-v)/(max-min)*PH,zero=y(0),step=PW/days.length;
 const ticks=[...new Set([0,Math.floor((days.length-1)/2),days.length-1])];
 return <figure className="repl-stat-figure"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Consumo neto por fecha: azul habitual, naranja días señalados y rojo devoluciones netas"><Grid min={min} max={max} unit={unit}/><line x1={L} x2={W-R} y1={zero} y2={zero} stroke="#8ca4b3"/>{days.map((d,i)=>{const color=d.demand<0?RED:outliers.has(d.day)?ORANGE:BLUE;const label=`${dateLabel(d.day)}: ${number(d.demand)} ${unit}${outliers.has(d.day)?' · día señalado':''}`;return <rect key={d.day} className="repl-stat-day" x={L+i*step} y={Math.min(zero,y(d.demand))} width={Math.max(.4,step*.8)} height={Math.max(d.demand===0?1:2,Math.abs(zero-y(d.demand)))} fill={d.demand===0?GREY:color} onMouseEnter={()=>setHover(label)} onMouseLeave={()=>setHover(null)}><title>{label}</title></rect>})}{ticks.map(i=><text key={i} x={L+i*step} y={H-12} textAnchor={i===0?'start':i===days.length-1?'end':'middle'} fontSize="12" fill="#526b7b">{dateLabel(days[i].day)}</text>)}</svg><figcaption><span>{hover||'Cada barra es un día. Las devoluciones netas se muestran por debajo de cero.'}</span><span className="repl-stat-legend"><i style={{background:BLUE}}/>Neto positivo <i style={{background:ORANGE}}/>Día señalado <i style={{background:RED}}/>Neto negativo</span></figcaption></figure>;
}
function Ranked({rows,median,unit}:{rows:ConsumptionDay[];median:number;unit:string}){
 const max=Math.max(1,...rows.map(d=>d.demand)),x=(i:number)=>L+(rows.length===1?PW/2:i/(rows.length-1)*PW),y=(v:number)=>T+(1-v/max)*PH;
 const middle=L+PW/2;
 return <figure className="repl-stat-figure"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Días positivos ordenados de menor a mayor. La mediana divide los días en dos mitades y vale ${number(median)} ${unit}`}><Grid max={max} unit={unit}/><rect x={L} y={T} width={PW/2} height={PH} fill="#e9f4ef" opacity=".65"/><line x1={middle} x2={middle} y1={T} y2={T+PH} stroke={GREEN} strokeDasharray="5 4"/><line x1={L} x2={middle} y1={y(median)} y2={y(median)} stroke={GREEN} strokeDasharray="5 4"/><polyline fill="none" stroke={BLUE} strokeWidth="2" points={rows.map((d,i)=>`${x(i)},${y(d.demand)}`).join(' ')}/>{rows.map((d,i)=><circle className="repl-stat-ranked-day" key={d.day} cx={x(i)} cy={y(d.demand)} r={rows.length>400?1.5:2.8} fill={BLUE}><title>{`${dateLabel(d.day)} · posición ${i+1} de ${rows.length}: ${number(d.demand)} ${unit}`}</title></circle>)}<circle cx={middle} cy={y(median)} r="6" fill={GREEN} stroke="white" strokeWidth="2"/><text x={middle-10} y={Math.max(T+15,y(median)-12)} textAnchor="end" fill={GREEN} fontSize="15" fontWeight="700">Mediana: {number(median)} {unit}</text><text x={L} y={H-12} fill="#526b7b" fontSize="12">Menor cantidad</text><text x={middle} y={H-12} textAnchor="middle" fill={GREEN} fontSize="12">Mitad de los días</text><text x={W-R} y={H-12} textAnchor="end" fill="#526b7b" fontSize="12">Mayor cantidad</text></svg><figcaption>No es el orden de las fechas: se ordena por cantidad. Cada punto representa un día con neto positivo.</figcaption></figure>;
}
function Pareto({rows,highlight,unit}:{rows:ReturnType<typeof orderedConsumption>['pareto'];highlight:number;unit:string}){
 const x=(count:number)=>L+count/rows.length*PW,y=(share:number)=>T+(1-share/100)*PH;
 const points=[`${L},${T+PH}`,...rows.map(d=>`${x(d.count)},${y(d.share)}`)].join(' ');
 const selected=rows[highlight-1],mark=selected?`${pct(selected.share)} % en ${highlight} días`:null;
 const labelRight=selected&&x(highlight)<W/2;
 return <figure className="repl-stat-figure"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Curva de concentración: porcentaje acumulado de unidades al sumar los días de mayor a menor consumo"><Grid max={100} unit="% de unidades positivas"/><polygon points={`${L},${T+PH} ${points} ${W-R},${T+PH}`} fill="#edf4f8"/><polyline points={points} fill="none" stroke={BLUE} strokeWidth="3"/>{selected&&<><polyline points={[`${L},${T+PH}`,...rows.slice(0,highlight).map(d=>`${x(d.count)},${y(d.share)}`)].join(' ')} fill="none" stroke={ORANGE} strokeWidth="4"/><line x1={x(highlight)} x2={x(highlight)} y1={y(selected.share)} y2={T+PH} stroke={ORANGE} strokeDasharray="5 4"/><line x1={L} x2={x(highlight)} y1={y(selected.share)} y2={y(selected.share)} stroke={ORANGE} strokeDasharray="5 4"/><circle cx={x(highlight)} cy={y(selected.share)} r="5" fill={ORANGE}/><rect x={x(highlight)+(labelRight?8:-228)} y={Math.max(T,y(selected.share)-36)} width="220" height="26" rx="5" fill="white" opacity=".96"/><text x={x(highlight)+(labelRight?12:-12)} y={Math.max(T+16,y(selected.share)-17)} textAnchor={labelRight?'start':'end'} fill={ORANGE} fontSize="15" fontWeight="700">{mark}</text></>}{[...new Set([0,Math.ceil(rows.length/2),rows.length])].map((count,i)=><text key={i} x={x(count)} y={H-12} textAnchor={count===0?'start':count===rows.length?'end':'middle'} fill="#526b7b" fontSize="12">{count} días</text>)}</svg><figcaption>Empieza por el día con más consumo y suma los siguientes. Al final están el 100 % de las unidades positivas. Las devoluciones siguen descontadas en el balance total.</figcaption></figure>;
}
export default function ConsumptionAnalysis({analysis:a,exceptionality:e,positiveDays,observedDays,unit,days=[]}:{analysis?:Spot;exceptionality?:ConsumptionExceptionality;positiveDays:number;observedDays:number;unit:string;days?:ConsumptionDay[]}){
 const {positive,pareto}=orderedConsumption(days);
 const complete=days.length===observedDays&&positive.length===positiveDays&&days.every(d=>Number.isFinite(d.demand));
 const peaksAnalyzed=!!a&&['POSSIBLE_SPOT','NO_OUTLIERS'].includes(a.status),peaks=a?.status==='POSSIBLE_SPOT'?a.outliers.length:0;
 const share=peaks?a!.flagged_share_percent:0,concentration=!!e?.reasons.includes('CONCENTRATION');
 const highImpact=peaks>0&&share>=(e?.high_impact_threshold_percent??25),single=positiveDays===1,limited=observedDays<30||positiveDays<8;
 const tone=single||concentration||highImpact?'review':limited?'limited':'normal';
 const title=positiveDays===0?'Sin consumo positivo':single?'Un solo día con consumo':concentration?'Consumo concentrado en pocos días':highImpact?'Los picos pesan en el promedio':limited?'Pocos datos para evaluar':'Consumo sin picos de alto impacto';
 const current=a?.daily_mean,without=a?.daily_mean_without_peaks,comparison=peaks>0&&current!=null&&without!=null;
 const maxMean=Math.max(current??0,without??0,.001),canDrawMean=comparison&&current!>=0&&without!>=0;
 const halfCount=pareto.find(d=>d.share>=50)?.count??0;
 const mark=peaks|| (concentration?Math.min(3,positive.length):halfCount);
 const median=a?.normal_daily_median??(positive.length?positive.length%2?positive[(positive.length-1)/2].demand:(positive[positive.length/2-1].demand+positive[positive.length/2].demand)/2:null);
 const outlierDates=new Set(a?.outliers.map(d=>d.day)||[]);
 return <section className={`repl-consumption-analysis repl-stat-story ${tone}`} aria-label="Resumen visual del consumo"><header><div><span className="repl-analysis-eyebrow">EL CONSUMO, PASO A PASO</span><h4>{title}</h4></div><span className="repl-analysis-status">{tone==='review'?'⚑ Revisar':tone==='limited'?'◌ Datos limitados':'● Informativo'}</span></header>
 <Step index={1} title="¿Cuándo se consume?" idea={`${positiveDays} de ${observedDays} días tuvieron consumo positivo (${pct(observedDays?positiveDays/observedDays*100:0)} %).${peaks?` En ${peaks} días se superaron ${number(a!.upper_threshold!)} ${unit}.`:''}`}>
 {complete&&days.length>0?<Timeline days={days} outliers={outlierDates} unit={unit}/>:<><div className="repl-analysis-stack" role="img" aria-label={`${positiveDays} de ${observedDays} días con consumo positivo`}><i style={{width:`${bounded(observedDays?positiveDays/observedDays*100:0)}%`}}/></div><p className="repl-stat-note">No hay una serie diaria completa para dibujar las fechas. Se muestran los recuentos guardados.</p></>}
 <p className="repl-stat-takeaway"><b>Idea clave:</b> {single?'Un solo día no demuestra que la demanda vaya a repetirse.':positiveDays===0?'No hay días con neto positivo en este periodo.':`${observedDays-positiveDays} días tuvieron neto cero o negativo. La frecuencia y la cantidad son medidas distintas.`}</p></Step>
 {median!=null&&<Step index={2} title="¿Qué cantidad queda en el centro?" idea={`La mediana es ${number(median)} ${unit}: al menos la mitad de los días positivos consumió esa cantidad o menos.`}>
 {complete&&positive.length>0?<Ranked rows={positive} median={median} unit={unit}/>:<p className="repl-stat-value">Mediana guardada: <strong>{number(median)} {unit}</strong></p>}
 <p className="repl-stat-takeaway"><b>Idea clave:</b> {number(median)} es una cantidad de unidades; no es un número de días ni una venta diaria garantizada.</p></Step>}
 {positiveDays>0&&<Step index={3} title="¿Pocos días concentran muchas unidades?" idea={peaks?`${peaks} de los ${positiveDays} días positivos reúnen ${number(a!.flagged_quantity)} ${unit}: el ${pct(share)} % de las unidades positivas.`:complete?`${halfCount} de los ${positiveDays} días positivos reúnen al menos la mitad de las unidades.`:concentration?`Los ${e!.top_days.length} mayores días reúnen el ${pct(e!.top3_share_percent)} % de las unidades positivas.`:'No hay datos completos para dibujar la concentración por día.'}>
 {complete&&pareto.length>0?<Pareto rows={pareto} highlight={mark} unit={unit}/>:peaks>0&&<div className="repl-analysis-stack impact" role="img" aria-label={`Picos: ${pct(share)} por ciento del consumo positivo`}><i style={{width:`${bounded(share)}%`}}/></div>}
 <p className="repl-stat-takeaway"><b>Idea clave:</b> {peaks?`${peaks} es un número de días, no una cantidad de ${unit}. Revisa el motivo de esas ventas grandes; el gráfico no confirma compras spot.`:'Una curva que sube muy rápido al principio indica concentración en pocos días.'}</p></Step>}
 {comparison&&<Step index={4} title="¿Cuánto cambian el promedio esos días?" idea={`Con todas las ventas y devoluciones: ${number(current!)} ${unit}/día. Si se retiran solo las cantidades de los días señalados: ${number(without!)} ${unit}/día.`}>
 <div className="repl-stat-comparison">{[['Con todas las cantidades',current!,ORANGE,'current'],['Comparación sin cantidades señaladas',without!,BLUE,'baseline']].map(([label,value,color,kind])=><div key={String(kind)}><div className="repl-stat-bar-label"><span>{label}</span><strong>{number(Number(value))} {unit}/día</strong></div>{canDrawMean&&<div className="repl-stat-bar-track"><div className={`repl-analysis-bar ${kind}`} style={{width:`${bounded(Number(value)/maxMean*100)}%`,background:String(color)}}/></div>}</div>)}</div>
 <p className="repl-analysis-impact">{a!.mean_uplift_percent==null?'No hay base positiva para calcular el aumento porcentual.':`Los días señalados elevan la media un ${pct(a!.mean_uplift_percent)} %.`}</p><p className="repl-stat-takeaway"><b>Idea clave:</b> Es una comparación con los mismos {observedDays} días. No se ha eliminado ninguna venta del cálculo real.</p></Step>}
 {!peaksAnalyzed&&positiveDays>0&&<p className="repl-stat-note">{a?.status==='SINGLE_CONSUMPTION'?'Consumo único: no hay base para clasificar picos.':a?.status==='INSUFFICIENT'?'Hay pocos días positivos para clasificar picos; se requieren al menos 8.':'El análisis de picos no está disponible en este cálculo.'}</p>}
 <footer><b>Para decidir la reposición:</b> confirma si las cantidades grandes volverán a necesitarse. Este análisis no cambia la propuesta ni excluye ventas automáticamente.</footer></section>;
}
