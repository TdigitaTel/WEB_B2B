'use client';
import {createContext,useContext,useEffect,useRef,useState,ReactNode} from 'react';
type Line={line_key:string;sku:string;pending:number;expected_at?:string|null;status?:string;observation?:string;local_available?:number|null;manual?:boolean};
type State={lines:Line[];loading:boolean;error:string};
const Context=createContext<State>({lines:[],loading:false,error:''});
const labels:Record<string,string>={EN_STOCK:'En stock',TRASLADO:'Movimiento entre delegaciones',PROVEEDOR:'En gestión proveedor',REVISAR:'Pendiente de revisión'};
export function LinePlanningProvider({orderId,customer=false,children}:{orderId:string;customer?:boolean;children:ReactNode}){
 const ref=useRef<HTMLSpanElement>(null);const [state,setState]=useState<State>({lines:[],loading:false,error:''});
 useEffect(()=>{const details=ref.current?.closest('details');const card=details||ref.current?.closest('article');if(!card)return;let visible=!!details?.open;let active=true,loaded=false;let controller:AbortController|undefined;
  async function load(force=false){if(!(details?details.open:visible)||loaded&&!force)return;loaded=true;controller?.abort();controller=new AbortController();setState(old=>({...old,loading:true,error:''}));try{
   const url=customer?`/api/v1/orders/${encodeURIComponent(orderId)}/line-planning`:`/api/v1/store/orders/line-planning/preview?order_id=${encodeURIComponent(orderId)}`;
   const res=await fetch(url,{credentials:'include',signal:controller.signal});if(res.status===401)window.dispatchEvent(new Event('session-expired'));
   const body=await res.json().catch(()=>({detail:'No se pudieron consultar las fechas'}));if(!res.ok)throw Error(typeof body.detail==='string'?body.detail:'No se pudieron consultar las fechas');
   if(active)setState({lines:body.lines,loading:false,error:body.warning||''});
  }catch(e){if(active&&!(e instanceof DOMException&&e.name==='AbortError'))setState({lines:[],loading:false,error:(e as Error).message})}}
  const toggle=()=>void load();const updated=(e:Event)=>{if((e as CustomEvent).detail===orderId){loaded=false;void load(true)}};details?.addEventListener('toggle',toggle);const observer=!details?new IntersectionObserver(entries=>{visible=entries.some(entry=>entry.isIntersecting);if(visible)void load()}):null;observer?.observe(card);window.addEventListener('line-planning-updated',updated);void load();
  return()=>{active=false;controller?.abort();details?.removeEventListener('toggle',toggle);observer?.disconnect();window.removeEventListener('line-planning-updated',updated)};
 },[orderId,customer]);
 return <Context.Provider value={state}><span ref={ref} hidden/>{children}</Context.Provider>
}
export function LinePlanningInfo({sku,lineKey,served=false}:{sku:string;lineKey?:string;served?:boolean}){
 const state=useContext(Context);if(served)return null;
 const matches=state.lines.filter(line=>line.sku===sku);const line=matches.find(line=>line.line_key===lineKey)||(matches.length===1?matches[0]:undefined);
 if(state.loading)return <small className="line-planning-inline">Consultando fecha y disponibilidad…</small>;
 if(!line)return <small className="line-planning-inline" title={state.error}>Fecha prevista: pendiente de revisión{matches.length>1?' · líneas repetidas: consultar con el operador':''}{state.error?' · no se pudieron consultar los datos':''}</small>;
 return <span className={`line-planning-inline plan-${line.status||'REVISAR'}`}><span><b>Fecha prevista:</b> {line.expected_at?new Date(line.expected_at).toLocaleString('es-ES',{timeZone:'Europe/Madrid',dateStyle:'short',timeStyle:'short'}):'Pendiente de revisión'}{line.manual?' · Manual':''}</span><span><b>{labels[line.status||'REVISAR']}</b>{line.local_available!=null?` · Stock disponible consultado: ${line.local_available.toLocaleString('es-ES')}`:''}</span>{line.observation&&line.observation!==labels[line.status||'REVISAR']&&<span>{line.observation}</span>}</span>
}
