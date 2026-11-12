"use client";
import {useEffect,useState} from 'react';
import ReplenishmentWeeklyChart,{type WeekSale,type Occurrence} from './ReplenishmentWeeklyChart';

type History={daily_mean?:number;daily_reference?:number;consumption_basis?:string;daily_median:number|null;daily_median_frequency:number;daily_median_dates:string[];daily_modes:number[];daily_mode_occurrences:Occurrence[];daily_mode_frequency:number;positive_consumption_days:number;observed_days:number;weekly_sales:WeekSale[];calculation:{window_start:string;window_end:string}};
const fmt=(n:number)=>n.toLocaleString('es-ES',{maximumFractionDigits:3});
const percent=(count:number,total:number)=>(total?count/total*100:0).toLocaleString('es-ES',{maximumFractionDigits:1});
const day=(s:string)=>s.split('-').reverse().join('/');
export default function ReplenishmentHistory({endpoint,unit}:{endpoint:string;unit:string}){
 const [data,setData]=useState<History|null>(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 useEffect(()=>{const controller=new AbortController();setData(null);setError('');
  void(async()=>{try{const res=await fetch(endpoint,{credentials:'include',signal:controller.signal});
   if(res.status===401)window.dispatchEvent(new Event('session-expired'));
   const body=await res.json();if(!res.ok)throw Error(typeof body.detail==='string'?body.detail:'No se pudo cargar el histórico del material.');
   if(!Array.isArray(body.weekly_sales)||!Array.isArray(body.daily_modes)||typeof body.positive_consumption_days!=='number')throw Error('Este servidor todavía no ofrece las estadísticas del histórico.');
   // Older deployed APIs already return daily_sales; keep the new detail usable
   // while frontend/backend versions roll over, without reading current EXIT data.
   const daily:{day:string;demand:number}[]=body.daily_sales||[];
   const datesFor=(value:number)=>daily.filter(row=>row.demand>0&&row.demand===value).map(row=>row.day);
   const medianDates=body.daily_median==null?[]:body.daily_median_dates??datesFor(body.daily_median);
   const modes=body.daily_modes.map((value:number)=>body.daily_mode_occurrences?.find((mode:Occurrence)=>mode.value===value)??{value,dates:datesFor(value),count:datesFor(value).length});
   if(!controller.signal.aborted)setData({...body,daily_median_dates:medianDates,daily_median_frequency:body.daily_median==null?0:body.daily_median_frequency??medianDates.length,daily_mode_occurrences:modes});
  }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'No se pudo cargar el histórico.');}})();
  return()=>controller.abort();
 },[endpoint,attempt]);
 const weeks=data?.weekly_sales||[],peak=Math.max(0,...weeks.map(w=>w.sold));
 const occurrences=new Map<string,{value:number;median:boolean;mode:boolean}>();
 if(data){
  for(const date of data.daily_median_dates)occurrences.set(date,{value:data.daily_median!,median:true,mode:false});
  for(const mode of data.daily_mode_occurrences)for(const date of mode.dates){const old=occurrences.get(date);occurrences.set(date,{value:mode.value,median:old?.median||false,mode:true})}
 }
 return <section className="repl-history" aria-label="Histórico del material"><h3>Histórico del material</h3>
 {!data&&!error&&<p role="status">Cargando estadísticas y ventas semanales…</p>}
 {error&&<div role="alert"><p>{error}</p><button className="secondary" onClick={()=>setAttempt(n=>n+1)}>Reintentar</button></div>}
 {data&&<><p>Periodo analizado: <b>{day(data.calculation.window_start)} — {day(data.calculation.window_end)}</b> · {data.observed_days} días · Delegación de esta línea.</p>
 <dl className="repl-history-metrics"><div><dt>Media diaria de referencia</dt><dd>{data.daily_mean==null?'Sin datos':<>{fmt(data.daily_mean)} {unit}/día<small>Consumo mensual medio ÷ 30. Incluye los días sin consumo.</small></>}</dd></div><div><dt>Mediana del consumo diario</dt><dd>{data.daily_median==null?'Sin consumo positivo':<>{fmt(data.daily_median)} {unit}/día<small>Aparece exactamente en <b>{data.daily_median_frequency} de {data.positive_consumption_days} días con consumo positivo ({percent(data.daily_median_frequency,data.positive_consumption_days)} %)</b>.</small>{data.daily_median_frequency===0&&<small>Valor intermedio entre los dos consumos centrales: no se observó exactamente en ningún día.</small>}</>}</dd></div>
 <div><dt>Moda del consumo diario</dt><dd>{data.daily_mode_occurrences.length?data.daily_mode_occurrences.map(mode=><div className="repl-mode-frequency" key={mode.value}>{fmt(mode.value)} {unit}/día<small>Aparece en <b>{mode.count} de {data.positive_consumption_days} días con consumo positivo ({percent(mode.count,data.positive_consumption_days)} %)</b>.</small></div>):data.positive_consumption_days===0?'Sin consumo positivo':'Sin moda: ningún valor se repite.'}</dd></div></dl>
 <p className="small">La mediana es el valor central al ordenar los consumos diarios; la moda es el valor que más se repite. Se calculan solo con los días de consumo positivo: <b>{data.positive_consumption_days}</b> días incluidos y <b>{data.observed_days-data.positive_consumption_days}</b> días con consumo cero excluidos. Consumo diario = máximo entre 0 y (ventas − devoluciones). La reposición utiliza el criterio elegido: media, mediana o moda. La media mantiene el cálculo mensual normalizado; la desviación diaria sigue incluyendo los días sin consumo.</p>
 <div className="repl-history-reading"><b>Qué representan estos valores</b><p>Hubo consumo positivo en {data.positive_consumption_days} de {data.observed_days} días del periodo ({percent(data.positive_consumption_days,data.observed_days)} %).</p>
 {data.daily_mode_occurrences.length>0&&<p>{data.daily_mode_occurrences[0].count>data.positive_consumption_days/2?'La moda aparece en la mayoría de los días con consumo (más del 50 %).':'Ninguna cantidad aparece en más del 50 % de los días con consumo; no hay un valor mayoritario.'}</p>}
 <p>La mediana describe el centro de las cantidades consumidas, aunque se repita poco o no se haya observado exactamente. La frecuencia de un valor por sí sola no demuestra un patrón estacional.</p></div>
 <h4>Ventas semanales · {unit}</h4><p className="small">Semanas de lunes a domingo, limitadas al periodo analizado. Las barras muestran ventas brutas, sin restar devoluciones. Las semanas incompletas no se extrapolan. Las marcas inferiores señalan las fechas en que el consumo neto diario coincide con la mediana o la moda.</p>
 <div className="repl-history-legend"><span className="repl-sales-key">▮ Ventas semanales</span><span className="repl-peak-key">▮ Marrón: pico semanal · mayor venta del periodo</span><span className="repl-median-key">● Mediana: consumo diario</span><span className="repl-mode-key">◆ Moda: consumo diario</span><span>Fondos alternos: meses naturales</span></div>
 {weeks.length>0?<><p>{peak>0?<>Pico semanal: <b>{fmt(peak)} {unit}</b> · {weeks.filter(w=>w.sold===peak).map(w=>`${day(w.from)} — ${day(w.to)}`).join('; ')}. Las barras marrones destacan todas las semanas que alcanzan este máximo.</>:'Sin ventas en el periodo analizado.'}</p>
 <ReplenishmentWeeklyChart weeks={weeks} start={data.calculation.window_start} end={data.calculation.window_end} unit={unit} median={data.daily_median} medianDates={data.daily_median_dates} modes={data.daily_mode_occurrences}/>
 {data.daily_median!=null&&data.daily_median_frequency===0&&<p className="small">No hay marcas de mediana porque ese valor intermedio no ocurrió exactamente.</p>}
 <details><summary>Ver fechas de mediana y moda ({occurrences.size} días)</summary>{occurrences.size?<div className="repl-daily"><table><caption>Ocurrencias exactas del consumo diario en {unit}</caption><thead><tr><th>Fecha</th><th>Consumo diario</th><th>Coincidencia</th></tr></thead><tbody>{[...occurrences.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([date,row])=><tr key={date}><td>{day(date)}</td><td>{fmt(row.value)} {unit}</td><td>{row.median&&row.mode?'Mediana y moda':row.median?'Mediana':'Moda'}</td></tr>)}</tbody></table></div>:<p>No hay fechas que coincidan con estos indicadores.</p>}</details>
 <details><summary>Ver datos de las semanas</summary><div className="repl-daily"><table><caption>Ventas y devoluciones semanales en {unit}</caption><thead><tr><th>Periodo incluido</th><th>Días</th><th>Ventas</th><th>Devoluciones</th><th>Consumo neto diario acumulado</th></tr></thead><tbody>{weeks.map(w=><tr key={w.week_start}><td>{day(w.from)} — {day(w.to)}</td><td>{w.observed_days}{w.observed_days<7?' · incompleta':''}</td><td>{fmt(w.sold)}</td><td>{fmt(w.returned)}</td><td>{fmt(w.demand)}</td></tr>)}</tbody></table></div><p className="small">El consumo acumula el neto de cada día limitado a cero; puede diferir de restar las devoluciones al total semanal.</p></details></>:<p>Sin días de histórico en este periodo.</p>}</>}
 </section>
}
