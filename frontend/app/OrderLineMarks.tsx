'use client';
import {useEffect,useRef} from 'react';
import './order-line-origin.css';
type Origin={created_in_web?:boolean|null};
export function OrderLineMarkHeaders(_props:{customer?:boolean}){
 return <span className="order-line-marks-head">WEB/Tienda</span>
}
export function OrderLineMarks({line}:{line:Origin;customer?:boolean}){
 const ref=useRef<HTMLInputElement>(null),unknown=line.created_in_web==null;
 useEffect(()=>{if(ref.current)ref.current.indeterminate=unknown},[unknown]);
 const text=unknown?'Sin confirmar':line.created_in_web?'WEB':'Tienda';
 const title=unknown?'Origen del registro sin confirmar':line.created_in_web?'Creado desde el carrito WEB':'Creado en tienda';
 return <span className="order-line-marks" role="group" aria-label="Origen del artículo"><label title={title}><input ref={ref} type="checkbox" checked={line.created_in_web===true} disabled readOnly aria-label="Origen WEB" aria-checked={unknown?'mixed':line.created_in_web===true}/><span>{text}</span></label></span>
}
export function RemovedOrderLine({removed}:{removed?:boolean}){
 return removed?<small className="order-line-removed-label">Eliminado · No se va a atender</small>:null
}
