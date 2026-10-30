"use client";
import {createContext,useContext,useEffect,useRef,useState,ReactNode} from "react";
import {startPolling} from "./screenPolling";

type Settings={interval_seconds:number};
const Interval=createContext(5);
const Scope=createContext(true);
export const useRefreshSeconds=()=>useContext(Interval);
export function RefreshScope({active,children}:{active:boolean;children:ReactNode}){
  const parent=useContext(Scope);
  return <Scope.Provider value={parent&&active}>{children}</Scope.Provider>;
}
export function AutoRefreshProvider({children}:{children:ReactNode}){
  const [seconds,setSeconds]=useState(5);
  useEffect(()=>{
    const load=async(signal:AbortSignal)=>{
      const response=await fetch('/api/v1/screen-refresh-settings',{credentials:'include',cache:'no-store',signal});
      if(!response.ok)return;
      const data:Settings=await response.json();
      if(!signal.aborted&&Number.isInteger(data.interval_seconds)&&data.interval_seconds>=5&&data.interval_seconds<=300)setSeconds(data.interval_seconds);
    };
    const controller=new AbortController();void load(controller.signal).catch(()=>{});
    const stop=startPolling(load,5,{pauseEditing:false});
    const saved=()=>{void load(controller.signal).catch(()=>{})};
    window.addEventListener('screen-refresh-settings-updated',saved);
    return()=>{controller.abort();stop();window.removeEventListener('screen-refresh-settings-updated',saved)};
  },[]);
  return <Interval.Provider value={seconds}>{children}</Interval.Provider>;
}
/** Poll only a mounted, visible read view. The callback must never submit a mutation. */
export function useAutoRefresh(task:(signal:AbortSignal)=>void|Promise<unknown>,enabled=true,key:unknown=""){
  const seconds=useRefreshSeconds(),scope=useContext(Scope);
  const latest=useRef(task);latest.current=task;
  useEffect(()=>{
    if(!enabled||!scope)return;
    return startPolling(signal=>latest.current(signal),seconds);
  },[seconds,enabled,scope,key]);
}
export function ScreenRefreshParameters(){
  const seconds=useRefreshSeconds();const [value,setValue]=useState(String(seconds));
  const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  useEffect(()=>{if(!dirty)setValue(String(seconds))},[seconds,dirty]);
  const valid=Number.isInteger(Number(value))&&Number(value)>=5&&Number(value)<=300;
  async function save(event:React.FormEvent){event.preventDefault();if(!valid||busy)return;setBusy(true);setMessage('');try{
    const response=await fetch('/api/v1/store/screen-refresh-settings',{method:'PATCH',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({interval_seconds:Number(value)})});
    if(response.status===401)window.dispatchEvent(new Event('session-expired'));
    const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'No se pudo guardar el intervalo');
    setValue(String(data.interval_seconds));setDirty(false);setMessage('Intervalo guardado para todas las pantallas.');window.dispatchEvent(new Event('screen-refresh-settings-updated'));
  }catch(error){setMessage((error as Error).message)}finally{setBusy(false)}}
  return <section className="section"><h2>Actualización de pantallas</h2><p>Intervalo común para las pantallas de consulta de operadores y clientes. Los datos se actualizan sin recargar la página y conservando filtros y edición.</p><form onSubmit={save}><label>Actualizar cada (segundos)<input className="input" type="number" min={5} max={300} step={1} value={value} onChange={event=>{setValue(event.target.value);setDirty(true)}} required/></label><p className="small">Predeterminado: 5 segundos. Admite entre 5 y 300 segundos. Se pausa en pestañas ocultas, sin conexión o mientras se escribe. Las consultas lentas terminan antes de repetirlas.</p><p className="small">No guarda formularios, importa archivos ni ejecuta cálculos de reposición. Los cambios sin guardar se conservan.</p><button className="primary" disabled={busy||!valid}>{busy?'Guardando…':'Guardar intervalo'}</button></form>{message&&<p role="status">{message}</p>}</section>;
}
