"use client";
import {useEffect,useState} from 'react';

type Week={week_start:string;from:string;to:string;observed_days:number;sold:number;returned:number;demand:number};
type History={daily_median:number|null;daily_modes:number[];daily_mode_frequency:number;observed_days:number;weekly_sales:Week[];calculation:{window_start:string;window_end:string}};
const fmt=(n:number)=>n.toLocaleString('es-ES',{maximumFractionDigits:3});
const day=(s:string)=>s.split('-').reverse().join('/');
export default function ReplenishmentHistory({endpoint,unit}:{endpoint:string;unit:string}){
 const [data,setData]=useState<History|null>(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 useEffect(()=>{const controller=new AbortController();setData(null);setError('');
  void(async()=>{try{const res=await fetch(endpoint,{credentials:'include',signal:controller.signal});
   if(res.status===401)window.dispatchEvent(new Event('session-expired'));
   const body=await res.json();if(!res.ok)throw Error(typeof body.detail==='string'?body.detail:'No se pudo cargar el histórico del material.');
   if(!Array.isArray(body.weekly_sales)||!Array.isArray(body.daily_modes))throw Error('Este servidor todavía no ofrece las estadísticas del histórico.');
   if(!controller.signal.aborted)setData(body);
  }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'No se pudo cargar el histórico.');}})();
  return()=>controller.abort();
 },[endpoint,attempt]);
 const weeks=data?.weekly_sales||[],peak=Math.max(0,...weeks.map(w=>w.sold)),chartWidth=Math.max(640,weeks.length*40+80),plotHeight=180,barWidth=(chartWidth-80)/Math.max(1,weeks.length);
 return <section className="repl-history" aria-label="Histórico del material"><h3>Histórico del material</h3>
 {!data&&!error&&<p role="status">Cargando estadísticas y ventas semanales…</p>}
 {error&&<div role="alert"><p>{error}</p><button className="secondary" onClick={()=>setAttempt(n=>n+1)}>Reintentar</button></div>}
 {data&&<><p>Periodo analizado: <b>{day(data.calculation.window_start)} — {day(data.calculation.window_end)}</b> · {data.observed_days} días · Delegación de esta línea.</p>
 <dl className="repl-history-metrics"><div><dt>Mediana del consumo diario</dt><dd>{data.daily_median==null?'Sin datos':`${fmt(data.daily_median)} ${unit}/día`}</dd></div><div><dt>Moda del consumo diario</dt><dd>{data.daily_modes.length?<>{data.daily_modes.map(fmt).join(' · ')} {unit}/día <small>Cada valor aparece en {data.daily_mode_frequency} de {data.observed_days} días.</small></>:'Sin moda: ningún valor se repite.'}</dd></div></dl>
 <p className="small">La mediana es el valor central al ordenar los consumos diarios; la moda es el valor que más se repite. Se incluyen los días sin ventas. Consumo diario = máximo entre 0 y (ventas − devoluciones). Son datos informativos: no modifican la reposición calculada.</p>
 <h4>Ventas semanales · {unit}</h4><p className="small">Semanas de lunes a domingo, limitadas al periodo analizado. Las barras muestran ventas brutas, sin restar devoluciones. Las semanas incompletas no se extrapolan.</p>
 {weeks.length>0?<><p>{peak>0?<>Pico semanal: <b>{fmt(peak)} {unit}</b> · {weeks.filter(w=>w.sold===peak).map(w=>`${day(w.from)} — ${day(w.to)}`).join('; ')}.</>:'Sin ventas en el periodo analizado.'}</p>
 <div className="repl-weekly-scroll" tabIndex={0} role="region" aria-label="Gráfico semanal desplazable"><svg width={chartWidth} height={265} viewBox={`0 0 ${chartWidth} 265`} role="img" aria-labelledby="repl-weekly-title repl-weekly-desc"><title id="repl-weekly-title">Ventas semanales del material</title><desc id="repl-weekly-desc">Cantidades en {unit}. Los picos se destacan en naranja. El detalle exacto está en la tabla de semanas.</desc>
 {[0,0.5,1].map(ratio=><g key={ratio}><line x1={60} y1={30+plotHeight*(1-ratio)} x2={chartWidth-20} y2={30+plotHeight*(1-ratio)} stroke="#d4e1e9"/><text x={53} y={34+plotHeight*(1-ratio)} textAnchor="end">{fmt(peak*ratio)}</text></g>)}
 {weeks.map((week,i)=>{const x=60+i*barWidth,h=peak?week.sold/peak*plotHeight:0;return <g key={week.week_start}><rect x={x+4} y={30+plotHeight-h} width={Math.max(2,barWidth-8)} height={h} fill={peak>0&&week.sold===peak?'#b56a13':'#226b98'}><title>{day(week.from)} — {day(week.to)}: {fmt(week.sold)} {unit} vendidos; devoluciones: {fmt(week.returned)}; {week.observed_days} días{week.observed_days<7?' (semana incompleta)':''}.</title></rect><text x={x+barWidth/2} y={230} textAnchor="middle" transform={`rotate(-35 ${x+barWidth/2} 230)`}>{week.from.slice(8)}/{week.from.slice(5,7)}</text></g>})}</svg></div>
 <details><summary>Ver datos de las semanas</summary><div className="repl-daily"><table><caption>Ventas y devoluciones semanales en {unit}</caption><thead><tr><th>Periodo incluido</th><th>Días</th><th>Ventas</th><th>Devoluciones</th><th>Consumo neto diario acumulado</th></tr></thead><tbody>{weeks.map(w=><tr key={w.week_start}><td>{day(w.from)} — {day(w.to)}</td><td>{w.observed_days}{w.observed_days<7?' · incompleta':''}</td><td>{fmt(w.sold)}</td><td>{fmt(w.returned)}</td><td>{fmt(w.demand)}</td></tr>)}</tbody></table></div><p className="small">El consumo acumula el neto de cada día limitado a cero; puede diferir de restar las devoluciones al total semanal.</p></details></>:<p>Sin días de histórico en este periodo.</p>}</>}
 </section>
}
