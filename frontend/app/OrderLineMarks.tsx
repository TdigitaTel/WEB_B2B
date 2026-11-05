'use client';
import './order-line-origin.css';
type Origin={created_in_web?:boolean|null};
export function OrderLineMarkHeaders(_props:{customer?:boolean}){
 return <span className="order-line-marks-head">WEB/Tienda</span>
}
export function OrderLineMarks({line}:{line:Origin;customer?:boolean}){
 const web=line.created_in_web===true;
 const text=web?'WEB':'Tienda';
 const title=web?'Creado desde el carrito WEB':'Creado en tienda';
 return <span className="order-line-marks" role="group" aria-label="Origen del artículo"><label className={web?"origin-web":"origin-store"} title={title}><input type="checkbox" checked={web} disabled readOnly aria-label="Origen WEB" aria-checked={web}/><span>{text}</span></label></span>
}
export function RemovedOrderLine({removed}:{removed?:boolean}){
 return removed?<small className="order-line-removed-label">Eliminado · No se va a atender</small>:null
}
