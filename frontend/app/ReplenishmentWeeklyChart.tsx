"use client";
export type WeekSale={week_start:string;from:string;to:string;observed_days:number;sold:number;returned:number;demand:number};
export type Occurrence={value:number;count:number;dates:string[]};
const DAY=86400000;
const stamp=(value:string)=>Date.parse(value+'T00:00:00Z');
const fmt=(value:number)=>value.toLocaleString('es-ES',{maximumFractionDigits:3});
const dateLabel=(value:string)=>value.split('-').reverse().join('/');
export function monthBands(start:string,end:string){
 const result:{key:string;from:string;to:string;label:string;shortLabel:string}[]=[];
 const limit=stamp(end)+DAY;let cursor=stamp(start);
 while(cursor<limit){
  const date=new Date(cursor),next=Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,1),until=Math.min(next,limit);
  result.push({key:date.toISOString().slice(0,7),from:date.toISOString().slice(0,10),to:new Date(until).toISOString().slice(0,10),
   label:date.toLocaleDateString('es-ES',{month:'short',year:'numeric',timeZone:'UTC'}),shortLabel:date.toLocaleDateString('es-ES',{month:'short',timeZone:'UTC'})});
  cursor=until;
 }
 return result;
}
export default function ReplenishmentWeeklyChart({weeks,start,end,unit,median,medianDates,modes,outliers=[]}:{weeks:WeekSale[];start:string;end:string;unit:string;median:number|null;medianDates:string[];modes:Occurrence[];outliers?:{day:string;demand:number;times_normal:number}[]}){
 const width=Math.max(700,weeks.length*42+90),height=362,left=74,right=18,top=42,plotHeight=170,bottom=top+plotHeight;
 const rangeStart=stamp(start),days=Math.max(1,(stamp(end)-rangeStart)/DAY+1),scale=(width-left-right)/days;
 const x=(date:string)=>left+(stamp(date)-rangeStart)/DAY*scale;
 const peak=Math.max(0,...weeks.map(week=>week.sold)),bands=monthBands(start,end);
 const modeDays=modes.flatMap(mode=>mode.dates.map(date=>({date,value:mode.value})));
 return <div className="repl-weekly-scroll" tabIndex={0} role="region" aria-label="Gráfico semanal y fechas de mediana y moda"><svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="repl-weekly-title repl-weekly-desc">
  <title id="repl-weekly-title">Ventas semanales y ocurrencias diarias de mediana y moda</title><desc id="repl-weekly-desc">Triángulos rojos: consumos diarios atípicos que requieren revisión, sin excluir ventas. Barras de ventas brutas en {unit}; En marrón se destacan todas las semanas con la mayor venta del periodo; las demás barras son azules. Meses separados por bandas de fondo. Círculos verdes: días del valor de mediana. Rombos violetas: días de cada moda. Las marcas usan consumo neto diario positivo. Las fechas exactas se pueden consultar en las tablas.</desc>
  <g className="repl-month-bands">{bands.map((band,i)=>{const from=x(band.from),to=x(band.to),span=to-from;return <g key={band.key} data-month={band.key}>
   <rect x={from} y={27} width={span} height={317} fill={i%2?'#fff6e7':'#edf4fa'}/>
   <line x1={from} y1={27} x2={from} y2={344} stroke="#cad8e1" strokeDasharray="3 3"/>
   <text className="repl-month-label" x={(from+to)/2} y={20} textAnchor="middle" style={{fontSize:span<60?9:12}}>{span<60?band.shortLabel:band.label}</text>
   {span>=90&&<text className="repl-month-watermark" x={(from+to)/2} y={75} textAnchor="middle" style={{fontSize:20,fill:'#7790a3',opacity:.24,fontWeight:700}}>{band.label}</text>}
   <title>{`${band.label}: ${dateLabel(band.from)} — ${dateLabel(new Date(stamp(band.to)-DAY).toISOString().slice(0,10))}`}</title>
  </g>})}</g>
  {[0,.5,1].map(ratio=><g key={ratio}><line x1={left} y1={top+plotHeight*(1-ratio)} x2={width-right} y2={top+plotHeight*(1-ratio)} stroke="#c5d6e1"/><text x={left-9} y={top+4+plotHeight*(1-ratio)} textAnchor="end">{fmt(peak*ratio)}</text></g>)}
  {weeks.map(week=>{const from=x(week.from),span=week.observed_days*scale,gap=Math.min(4,span*.15),h=peak?week.sold/peak*plotHeight:0,center=from+span/2;return <g key={week.week_start}>
   <rect className="repl-week-bar" x={from+gap} y={bottom-h} width={Math.max(1,span-gap*2)} height={h} fill={peak>0&&week.sold===peak?'#b56a13':'#226b98'}><title>{`${peak>0&&week.sold===peak?"Pico semanal · mayor venta del periodo. ":""}${dateLabel(week.from)} — ${dateLabel(week.to)}: ${fmt(week.sold)} ${unit} vendidos; devoluciones: ${fmt(week.returned)}; ${week.observed_days} días${week.observed_days<7?" (semana incompleta)":""}.`}</title></rect>
   <text x={center} y={232} textAnchor="end" transform={`rotate(-40 ${center} 232)`}>{week.from.slice(8)}/{week.from.slice(5,7)}</text>
  </g>})}
  {outliers.map(row=>{const week=weeks.find(w=>w.from<=row.day&&row.day<=w.to);if(!week)return null;const cx=x(row.day)+scale/2,cy=bottom-(peak?week.sold/peak*plotHeight:0)-9;return <path className="repl-spot-mark" key={row.day} data-date={row.day} d={`M ${cx} ${cy-5} L ${cx+5} ${cy+4} L ${cx-5} ${cy+4} Z`} fill="#a93226" stroke="white"><title>{`Posible spot a revisar · ${dateLabel(row.day)} · Consumo neto: ${fmt(row.demand)} ${unit}; ${fmt(row.times_normal)} veces la mediana. No se ha excluido.`}</title></path>})}
  <text x={8} y={298}>Mediana</text><line x1={left} x2={width-right} y1={294} y2={294} stroke="#c4d6cf"/>
  <text x={8} y={332}>Moda</text><line x1={left} x2={width-right} y1={328} y2={328} stroke="#d5cce6"/>
  {median!=null&&medianDates.map(date=><circle className="repl-median-mark" key={date} data-date={date} cx={x(date)+scale/2} cy={294} r={4.5} fill="#18734f" stroke="white" strokeWidth={1}><title>{`Mediana · ${dateLabel(date)} · Consumo: ${fmt(median)} ${unit}/día.`}</title></circle>)}
  {modeDays.map(({date,value})=>{const cx=x(date)+scale/2,cy=328;return <path className="repl-mode-mark" key={`${value}:${date}`} data-date={date} d={`M ${cx} ${cy-5} L ${cx+5} ${cy} L ${cx} ${cy+5} L ${cx-5} ${cy} Z`} fill="#7650a5" stroke="white" strokeWidth={1}><title>{`Moda · ${dateLabel(date)} · Consumo: ${fmt(value)} ${unit}/día.`}</title></path>})}
 </svg></div>
}
