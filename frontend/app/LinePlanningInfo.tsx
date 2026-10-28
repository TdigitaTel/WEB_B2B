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
export function LinePlanningInfo({sku,lineKey,served=false,part='note'}:{sku:string;lineKey?:string;served?:boolean;part?:'date'|'stock'|'note'}){
 const state=useContext(Context);
 const matches=state.lines.filter(line=>line.sku===sku);const line=matches.find(line=>line.line_key===lineKey)||(matches.length===1?matches[0]:undefined);
 if(state.loading)return <span className="line-plan-cell">Cargando…</span>;
 if(!line)return <span className="line-plan-cell" title={state.error}>{served?'—':state.error?'Consulta no disponible':part==='note'?'Pendiente de planificación':'—'}</span>;
 if(part==='date')return <span className="line-plan-cell">{line.expected_at?new Date(line.expected_at).toLocaleString('es-ES',{timeZone:'Europe/Madrid',dateStyle:'short',timeStyle:'short'}):'Sin fecha'}{line.manual&&<small>Manual</small>}</span>;
 if(part==='stock')return <span className="line-plan-cell">{line.local_available!=null?line.local_available.toLocaleString('es-ES'):'—'}<small>Stock consultado</small></span>;
 return <span className={`line-plan-cell plan-${line.status||'REVISAR'}`}><b>{labels[line.status||'REVISAR']}</b>{line.observation&&line.observation!==labels[line.status||'REVISAR']&&<small>{line.observation}</small>}</span>
}
