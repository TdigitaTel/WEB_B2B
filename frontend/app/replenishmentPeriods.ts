export function salesPeriodDates(period:string,end:string){
 const day=new Date(`${end}T12:00:00Z`);
 if(period==='ALL')return {date_from:'2026-01-01',date_to:end};
 if(period==='YEAR'){
  const month=day.getUTCMonth();
  day.setUTCFullYear(day.getUTCFullYear()-1);
  if(day.getUTCMonth()!==month)day.setUTCDate(0);
 }else day.setUTCDate(day.getUTCDate()-Number(period)+1);
 return {date_from:day.toISOString().slice(0,10),date_to:end};
}
