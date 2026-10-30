"use client";
import {useAutoRefresh} from "./AutoRefresh";
import {FormEvent,useEffect,useMemo,useState} from 'react';
import './sales-order-series.css';

type Series={company_code:number;series_code:string;document_type:string;description:string};
type Delegation={company_code:number;code:string;name:string};
type Options={series:Series[];delegations:Delegation[]};
type Assignment={id:number;company_code:number;delegation_code:string;delegation_name:string;document_type:string;series_code:string;series_description:string;active:boolean;version:number};
const base='/api/v1/store/sales-order-series';
const code=(value:string)=>value||'(Serie vacía)';
async function request<T>(path:string,method='GET',body?:unknown):Promise<T>{
 const res=await fetch(base+path,{method,credentials:'include',headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
 if(res.status===401)window.dispatchEvent(new Event('session-expired'));
 let data;try{data=await res.json()}catch{throw Error(`No se pudo completar la consulta (${res.status}).`)}
 if(!res.ok)throw Error(typeof data.detail==='string'?data.detail:'No se pudo guardar la configuración de series.');
 return data;
}
export default function SalesOrderSeries(){
 const [options,setOptions]=useState<Options|null>(null),[assignments,setAssignments]=useState<Assignment[]>([]);
 const [sourceLoading,setSourceLoading]=useState(true),[listLoading,setListLoading]=useState(true),[saving,setSaving]=useState(false);
 const [sourceError,setSourceError]=useState(''),[listError,setListError]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [company,setCompany]=useState(''),[query,setQuery]=useState(''),[state,setState]=useState('ALL'),[page,setPage]=useState(1);
 const [chosen,setChosen]=useState<Series|null>(null),[delegation,setDelegation]=useState(''),[active,setActive]=useState(true);
 async function loadSource(){setSourceLoading(true);setSourceError('');try{setOptions(await request<Options>('/options'))}catch(e){setSourceError((e as Error).message)}finally{setSourceLoading(false)}}
 async function loadAssignments(){setListLoading(true);setListError('');try{setAssignments(await request<Assignment[]>('/assignments'))}catch(e){setListError((e as Error).message)}finally{setListLoading(false)}}
 useEffect(()=>{void Promise.all([loadSource(),loadAssignments()])},[]);
 useAutoRefresh(async signal=>{const [source,rows]=await Promise.all([request<Options>("/options"),request<Assignment[]>("/assignments")]);if(!signal.aborted){setOptions(source);setAssignments(rows)}},!saving&&!sourceLoading&&!listLoading);
 const companies=useMemo(()=>Array.from(new Set([...(options?.series||[]).map(row=>row.company_code),...assignments.map(row=>row.company_code)])).sort((a,b)=>a-b),[options,assignments]);
 const matches=(values:(string|number)[])=>values.join(' ').toLocaleLowerCase('es').includes(query.trim().toLocaleLowerCase('es'));
 const series=(options?.series||[]).filter(row=>(!company||row.company_code===Number(company))&&matches([row.series_code,row.description,row.company_code]));
 const saved=assignments.filter(row=>(!company||row.company_code===Number(company))&&(state==='ALL'||row.active===(state==='ACTIVE'))&&matches([row.series_code,row.series_description,row.delegation_code,row.delegation_name,row.company_code]));
 const pages=Math.max(1,Math.ceil(series.length/25)),current=Math.min(page,pages);
 function choose(row:Series){setChosen(row);setDelegation('');setActive(true);setError('');setMessage('')}
 async function save(event:FormEvent){event.preventDefault();if(!chosen||!delegation)return;setSaving(true);setError('');setMessage('');try{
  await request<Assignment>('/assignments','PUT',{company_code:chosen.company_code,delegation_code:delegation,series_code:chosen.series_code,active});
  await loadAssignments();setMessage(`Serie ${code(chosen.series_code)} asociada a la delegación ${delegation} de la empresa ${chosen.company_code}${active?' y activada.':', como inactiva.'}`);setChosen(null);
 }catch(e){setError((e as Error).message)}finally{setSaving(false)}}
 async function toggle(row:Assignment){setSaving(true);setError('');setMessage('');try{
  await request<Assignment>(`/assignments/${row.id}`,'PATCH',{active:!row.active,expected_version:row.version});
  await loadAssignments();setMessage(`Serie ${code(row.series_code)} ${row.active?'desactivada':'activada'} para la delegación ${row.delegation_code} de la empresa ${row.company_code}.`);
 }catch(e){setError((e as Error).message);await loadAssignments()}finally{setSaving(false)}}
 return <section className="series-panel" aria-labelledby="series-title"><header className="series-heading"><div><h2 id="series-title">Series de pedidos de venta</h2><p>Series de EXIT de tipo <b>PedV</b>. Asócialas a una empresa y delegación para utilizar la serie activa.</p></div><button className="secondary" disabled={sourceLoading||listLoading||saving} onClick={()=>void Promise.all([loadSource(),loadAssignments()])}>Actualizar</button></header>
 <div className="series-filters"><label>Empresa<select value={company} onChange={e=>{setCompany(e.target.value);setPage(1);setChosen(null)}}><option value="">Todas las empresas permitidas</option>{companies.map(value=><option key={value} value={value}>{value}</option>)}</select></label><label className="series-search">Buscar<input type="search" value={query} onChange={e=>{setQuery(e.target.value);setPage(1)}} placeholder="Serie, descripción o delegación"/></label></div>
 {error&&<p className="error" role="alert">{error}</p>}{message&&<p className="series-success" role="status">{message}</p>}
 <div className="series-layout"><section><h3>Series disponibles en EXIT</h3>{sourceError&&<p className="error" role="alert">{sourceError}</p>}<div className="series-grid" aria-busy={sourceLoading}><table><thead><tr><th>Empresa</th><th>Serie</th><th>Tipo</th><th>Descripción</th><th/></tr></thead><tbody>{series.slice((current-1)*25,current*25).map((row,index)=><tr key={`${row.company_code}-${row.series_code}-${index}`}><td>{row.company_code}</td><td><b>{code(row.series_code)}</b></td><td>{row.document_type}</td><td>{row.description||'—'}</td><td><button className="secondary" disabled={saving||sourceLoading} onClick={()=>choose(row)}>Asociar</button></td></tr>)}{!series.length&&<tr><td colSpan={5}>{sourceLoading?'Consultando EXIT…':sourceError?'No se han podido cargar las series.':'No hay series para este filtro.'}</td></tr>}</tbody></table></div><div className="series-pagination"><span>{series.length} series · Página {current} de {pages}</span><button className="ghost" disabled={current<=1||sourceLoading} onClick={()=>setPage(current-1)}>Anterior</button><button className="ghost" disabled={current>=pages||sourceLoading} onClick={()=>setPage(current+1)}>Siguiente</button></div></section>
 <aside className="series-editor">{chosen?<><h3>Asociar serie {code(chosen.series_code)}</h3><p>Empresa <b>{chosen.company_code}</b> · {chosen.description||'Sin descripción'}</p><form onSubmit={save}><label>Delegación<select required disabled={saving} value={delegation} onChange={e=>setDelegation(e.target.value)}><option value="">Selecciona una delegación</option>{options?.delegations.filter(row=>row.company_code===chosen.company_code).map(row=><option key={`${row.company_code}:${row.code}`} value={row.code}>{row.name} · {row.code}</option>)}</select></label><label className="series-check"><input type="checkbox" checked={active} disabled={saving} onChange={e=>setActive(e.target.checked)}/>Usar esta serie como activa</label><p className="small">Solo puede haber una activa por empresa y delegación. Al activarla, la anterior queda inactiva.</p><button className="primary" disabled={saving||!delegation}>{saving?'Guardando…':'Guardar asociación'}</button><button type="button" className="ghost" disabled={saving} onClick={()=>setChosen(null)}>Cancelar</button></form></>:<><h3>Asignación por delegación</h3><p>Pulsa «Asociar» junto a una serie. Podrás conservar varias asociaciones y elegir cuál está activa.</p><p className="small">La empresa y el código de delegación se guardan por separado. Las series de EXIT se consultan, sin modificarlas.</p></>}</aside></div>
 <section className="series-saved"><div className="series-heading"><div><h3>Asociaciones guardadas</h3><p>La API devuelve únicamente la serie activa de la empresa y delegación solicitadas.</p></div><label>Estado<select value={state} onChange={e=>setState(e.target.value)}><option value="ALL">Todas</option><option value="ACTIVE">Activas</option><option value="INACTIVE">Inactivas</option></select></label></div>{listError&&<p className="error" role="alert">{listError}</p>}<div className="series-grid" aria-busy={listLoading}><table><thead><tr><th>Empresa</th><th>Delegación</th><th>Serie</th><th>Descripción</th><th>Estado</th><th/></tr></thead><tbody>{saved.map(row=><tr key={row.id}><td>{row.company_code}</td><td><b>{row.delegation_code}</b> · {row.delegation_name}</td><td>{code(row.series_code)}</td><td>{row.series_description||'—'}</td><td><span className={`brand-status ${row.active?'is-active':'is-inactive'}`}>{row.active?'Activa':'Inactiva'}</span></td><td><button className="secondary" disabled={saving||listLoading||(!row.active&&(sourceLoading||!options))} aria-label={`${row.active?'Desactivar':'Activar'} serie ${code(row.series_code)} de la delegación ${row.delegation_code}`} onClick={()=>void toggle(row)}>{row.active?'Desactivar':'Activar'}</button></td></tr>)}{!saved.length&&<tr><td colSpan={6}>{listLoading?'Cargando asociaciones…':listError?'No se han podido cargar las asociaciones.':'No hay asociaciones para este filtro.'}</td></tr>}</tbody></table></div><p className="small">La activación sustituye a la serie activa anterior de esa empresa y delegación. Las asociaciones guardadas y su consulta por API siguen disponibles aunque EXIT no responda.</p></section>
 </section>;
}
