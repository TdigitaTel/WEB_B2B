"use client";
import {useAutoRefresh} from "./AutoRefresh";
import {useEffect,useRef,useState} from "react";
import {createPortal} from "react-dom";
type Item={line:number;sku:string;description:string;quantity:number;unit:string;unit_price:number|null;discount_pct:number|null;net_amount:number|null;total:number|null};
type Note={number:string;created_at?:string;status?:string;items?:Item[]};
const money=(value:number|null|undefined)=>value==null?"—":value.toLocaleString("es-ES",{style:"currency",currency:"EUR"});
export default function OperatorDeliveryNote({orderId,number,onClose}:{orderId:string;number:string;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 const [note,setNote]=useState<Note|null>(null),[error,setError]=useState(""),[retry,setRetry]=useState(0);
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close()},[]);
 useEffect(()=>{
  const controller=new AbortController();setNote(null);setError("");
  fetch(`/api/v1/store/orders/${encodeURIComponent(orderId)}/delivery-note?${new URLSearchParams({number})}`,{credentials:"include",signal:controller.signal,cache:"no-store"}).then(async response=>{
   if(response.status===401)window.dispatchEvent(new Event("session-expired"));
   const data=await response.json();if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"No se pudo consultar el albarán");return data as Note;
  }).then(data=>{if(!controller.signal.aborted)setNote(data)}).catch(e=>{if(!controller.signal.aborted)setError(e.message)});
  return()=>controller.abort();
 },[orderId,number,retry]);
 useAutoRefresh(async signal=>{const response=await fetch(`/api/v1/store/orders/${encodeURIComponent(orderId)}/delivery-note?${new URLSearchParams({number})}`,{credentials:"include",cache:"no-store",signal});if(response.status===401)window.dispatchEvent(new Event('session-expired'));if(!response.ok)throw Error('No se pudo actualizar el albarán');const data=await response.json();if(!signal.aborted)setNote(data)},!!note,orderId+number);
 return createPortal(<dialog ref={dialog} className="delivery-notes-dialog operator-delivery-document" aria-labelledby="operator-note-title" onCancel={event=>{event.preventDefault();onClose()}}><header><h2 id="operator-note-title">Albarán {number}</h2><button className="ghost" autoFocus aria-label="Cerrar albarán" onClick={onClose}>×</button></header>{error?<p role="alert">{error} <button className="text-button" onClick={()=>setRetry(value=>value+1)}>Reintentar</button></p>:!note?<p role="status">Consultando albarán…</p>:<><p>{note.created_at?new Date(note.created_at).toLocaleString("es-ES",{timeZone:"Europe/Madrid"}):"Sin fecha registrada"} · {({ENTREGADO:"EMITIDO",IMPRESO:"EMITIDO",PENDIENTE_DE_ENTREGA:"PENDIENTE DE EMISIÓN",PENDIENTE_EMISION:"PENDIENTE DE EMISIÓN"}[note.status||""]||note.status||"Registrado")}</p><div className="delivery-notes-table"><table><thead><tr><th>Artículo</th><th>Cantidad</th><th>Precio</th><th>% descuento</th><th>Importe neto</th><th>Total</th></tr></thead><tbody>{(note.items||[]).map(item=><tr key={item.line}><td><b>{item.description}</b><br/><small>{item.sku}</small></td><td>{item.quantity} {item.unit||"UD"}</td><td>{money(item.unit_price)}</td><td>{item.discount_pct==null?"—":`${item.discount_pct} %`}</td><td>{money(item.net_amount)}</td><td>{money(item.total)}</td></tr>)}</tbody></table></div>{!note.items?.length&&<p>El albarán no contiene líneas de material.</p>}</>}<footer><button className="primary" onClick={onClose}>Cerrar</button></footer></dialog>,document.body);
}
