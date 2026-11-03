"use client";
import {useEffect,useRef,useState} from 'react';
import './order-tracking.css';
type Status={active:boolean;expires_at?:string|null;lifetime_days:number};
const date=(value:string)=>new Date(value).toLocaleString('es-ES',{timeZone:'Europe/Madrid',dateStyle:'short',timeStyle:'short'});
export default function ShareOrderTracking({orderId,number}:{orderId:string;number:string}){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[status,setStatus]=useState<Status|null>(null),[url,setUrl]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('');
 const dialog=useRef<HTMLDialogElement>(null);
 const linkField=useRef<HTMLInputElement>(null),messageField=useRef<HTMLTextAreaElement>(null);
 const whatsappMessage=`Puedes consultar el estado de tu pedido ${number} aquí:\n\n${url}`;
 function selectField(asMessage=false){const field=asMessage?messageField.current:linkField.current;field?.focus();field?.select();field?.setSelectionRange(0,field.value.length);return field}
 const endpoint=`/api/v1/store/orders/${encodeURIComponent(orderId)}/tracking-link`;
 async function request(method:string,signal?:AbortSignal){const response=await fetch(endpoint,{method,credentials:'include',cache:'no-store',signal});if(response.status===401)window.dispatchEvent(new Event('session-expired'));const data=await response.json().catch(()=>({}));if(!response.ok)throw Error(data.detail||'No se pudo preparar el enlace');return data}
 useEffect(()=>{if(!open)return;dialog.current?.showModal();const controller=new AbortController();setBusy(true);setError('');setMessage('');setUrl('');setStatus(null);request('GET',controller.signal).then(setStatus).catch(e=>{if(!controller.signal.aborted)setError(e.message)}).finally(()=>{if(!controller.signal.aborted)setBusy(false)});return()=>controller.abort()},[open,endpoint]);
 async function create(){setBusy(true);setError('');setMessage('');try{const data=await request('POST');setUrl(window.location.origin+data.path);setStatus({active:true,expires_at:data.expires_at,lifetime_days:data.lifetime_days})}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function revoke(){setBusy(true);setError('');try{await request('DELETE');setStatus({active:false,lifetime_days:status?.lifetime_days||30});setUrl('');setMessage('Enlace desactivado. Ya no permite consultar el pedido.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function copy(asMessage=false){
  const field=selectField(asMessage);if(!field)return;
  let copied=false;
  // Copy while the click is active, including HTTP kiosks without Clipboard API.
  try{copied=typeof document.execCommand==='function'&&document.execCommand('copy')}catch{}
  if(!copied){try{if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(field.value);copied=true}}catch{}}
  if(copied)setMessage(asMessage?'Mensaje copiado. Puedes pegarlo en WhatsApp.':'Enlace copiado.');
  else{selectField(asMessage);setMessage('El navegador no permite copiar automáticamente. El texto está seleccionado: usa Copiar o Ctrl+C. En móvil, mantén pulsado para copiar.')}
 }
 return <><button className="secondary" type="button" onClick={()=>setOpen(true)}>Compartir seguimiento</button>{open&&<dialog className="tracking-share-dialog" ref={dialog} onCancel={e=>{e.preventDefault();if(!busy)setOpen(false)}}><h2>Compartir seguimiento del pedido {number}</h2><p>Quien tenga el enlace podrá consultar el estado de este pedido sin iniciar sesión. No muestra precios ni datos personales.</p>{status?.active&&<p>Enlace activo hasta {status.expires_at?date(status.expires_at):'—'}.{!url&&' Crear otro enlace desactivará el anterior.'}</p>}{url&&<><label>Enlace de seguimiento<input ref={linkField} aria-label="Enlace de seguimiento" readOnly value={url} onFocus={e=>e.currentTarget.select()} onClick={()=>selectField()}/></label><a className="tracking-open-link" href={url} target="_blank" rel="noopener noreferrer">Abrir enlace de seguimiento ↗</a><label>Mensaje para WhatsApp<textarea ref={messageField} aria-label="Mensaje para WhatsApp" readOnly rows={4} value={whatsappMessage} onFocus={e=>e.currentTarget.select()} onClick={()=>selectField(true)}/></label></>}<div className="tracking-actions">{url?<><button className="primary" type="button" onClick={()=>void copy()}>Copiar enlace</button><button className="secondary" type="button" onClick={()=>void copy(true)}>Copiar mensaje para WhatsApp</button><a className="secondary" href={`https://wa.me/?text=${encodeURIComponent(whatsappMessage)}`} target="_blank" rel="noopener noreferrer">Abrir WhatsApp</a></>:<button className="primary" type="button" disabled={busy} onClick={()=>void create()}>{busy?'Preparando…':status?.active?'Crear nuevo enlace':'Crear enlace privado'}</button>}{status?.active&&<button className="ghost" type="button" disabled={busy} onClick={()=>void revoke()}>Desactivar enlace</button>}<button className="ghost" type="button" disabled={busy} onClick={()=>setOpen(false)}>Cerrar</button></div><p className="small">Vigencia: {status?.lifetime_days||30} días. El enlace solo permite consultar el seguimiento.</p>{message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}</dialog>}</>;
}
