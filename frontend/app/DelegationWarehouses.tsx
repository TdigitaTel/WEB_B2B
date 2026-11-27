'use client';
import {useEffect,useState} from 'react';
import './sales-order-series.css';
type Seat={company_code:number;code:string;name:string;primary_warehouse_code:string};
type Warehouse={company_code:number;code:string;name:string};
type Link={company_code:number;delegation_code:string;warehouse_code:string;delegation_name:string;warehouse_name:string;is_primary:boolean;active:boolean;use_for_stock:boolean;version:number};
type Options={can_edit:boolean;delegations:Seat[];warehouses:Warehouse[]};
const base='/api/v1/store/delegation-warehouses';
async function request<T>(path:string,method='GET',body?:unknown):Promise<T>{
 const response=await fetch(base+path,{method,credentials:'include',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});
 if(response.status===401)window.dispatchEvent(new Event('session-expired'));
 let data;try{data=JSON.parse(await response.text())}catch{throw Error('No se pudo completar la consulta. Inténtalo de nuevo.')}
 if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'No se pudo guardar la relación.');return data;
}
export default function DelegationWarehouses(){
 const [options,setOptions]=useState<Options|null>(null),[links,setLinks]=useState<Link[]>([]),[selected,setSelected]=useState(''),[warehouse,setWarehouse]=useState('');
 const [busy,setBusy]=useState(true),[error,setError]=useState(''),[message,setMessage]=useState('');
 async function refresh(){setBusy(true);setError('');try{
  const source=await request<Options>('/options');setOptions(source);
  if(source.can_edit)await request('/sync','POST');
 }catch(e){setError((e as Error).message)}
 try{setLinks(await request<Link[]>('/assignments'))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 useEffect(()=>{void refresh()},[]);
 const seats=new Map<string,Seat>();for(const row of links)seats.set(`${row.company_code}:${row.delegation_code}`,{company_code:row.company_code,code:row.delegation_code,name:row.delegation_name,primary_warehouse_code:''});
 for(const row of options?.delegations||[])seats.set(`${row.company_code}:${row.code}`,row);
 const key=selected||seats.keys().next().value||'',seat=seats.get(key);
 const rows=links.filter(row=>`${row.company_code}:${row.delegation_code}`===key);
 const available=(options?.warehouses||[]).filter(row=>row.company_code===seat?.company_code&&!rows.some(link=>link.warehouse_code===row.code));
 async function save(row:Link|undefined,code:string,active:boolean,useForStock:boolean){if(!seat)return;setBusy(true);setError('');setMessage('');try{
  await request('/assignments','PUT',{company_code:seat.company_code,delegation_code:seat.code,warehouse_code:code,active,use_for_stock:useForStock,...row?{expected_version:row.version}:{}});
  setLinks(await request<Link[]>('/assignments'));setWarehouse('');setMessage('Relación guardada.');
 }catch(e){setError((e as Error).message);try{setLinks(await request<Link[]>('/assignments'))}catch{}}finally{setBusy(false)}}
 return <section className="series-panel" aria-labelledby="delegation-warehouses-title"><header className="series-heading"><div><h2 id="delegation-warehouses-title">Delegaciones y almacenes</h2><p>El almacén principal procede de EXIT. Añade otros almacenes de la misma empresa y decide cuáles se utilizan para stock.</p></div><button className="secondary" disabled={busy} onClick={()=>void refresh()}>Actualizar desde EXIT</button></header>
 {error&&<p className="error" role="alert">{error}</p>}{message&&<p className="series-success" role="status">{message}</p>}
 <div className="series-filters"><label>Empresa · Delegación<select aria-label="Empresa y delegación" value={key} disabled={busy} onChange={e=>{setSelected(e.target.value);setWarehouse('');setMessage('')}}>{[...seats].map(([id,row])=><option key={id} value={id}>{row.company_code} · {row.code} · {row.name}</option>)}</select></label></div>
 <div className="series-grid" aria-busy={busy}><table><thead><tr><th>Orden</th><th>Almacén</th><th>Descripción</th><th>Activo</th><th>Usar para stock</th></tr></thead><tbody>{rows.map(row=><tr key={row.warehouse_code}><td>{row.is_primary?<b>Principal · EXIT</b>:'Adicional'}</td><td>{row.warehouse_code}</td><td>{row.warehouse_name||'—'}</td><td><input type="checkbox" aria-label={`Activo ${row.warehouse_code}`} checked={row.active} disabled={busy||!options?.can_edit} onChange={e=>void save(row,row.warehouse_code,e.target.checked,row.use_for_stock)}/></td><td><input type="checkbox" aria-label={`Usar para stock ${row.warehouse_code}`} checked={row.use_for_stock} disabled={busy||!options?.can_edit} onChange={e=>void save(row,row.warehouse_code,row.active,e.target.checked)}/></td></tr>)}{!rows.length&&<tr><td colSpan={5}>{busy?'Consultando…':'No hay almacenes vinculados a esta delegación.'}</td></tr>}</tbody></table></div>
 {seat&&!seat.primary_warehouse_code&&options&&<p className="small">Esta delegación no tiene almacén principal configurado en EXIT.</p>}
 {options&&!options.can_edit&&<p className="small" role="status">Solo consulta: no tienes permiso para configurar las relaciones.</p>}
 {options?.can_edit&&<form className="series-filters" onSubmit={e=>{e.preventDefault();if(warehouse)void save(undefined,warehouse,true,true)}}><label>Almacén adicional<select aria-label="Almacén adicional" required disabled={busy||!seat} value={warehouse} onChange={e=>setWarehouse(e.target.value)}><option value="">Selecciona un almacén de EXIT</option>{available.map(row=><option value={row.code} key={row.code}>{row.code} · {row.name}</option>)}</select></label><button className="primary" type="submit" disabled={busy||!warehouse}>Añadir almacén</button></form>}
 <p className="small">Para utilizar un almacén en stock deben estar marcados «Activo» y «Usar para stock». Actualizar desde EXIT conserva tus indicadores y sitúa primero el principal actual. Si cambia el principal, el anterior se conserva como adicional.</p>
 </section>;
}
