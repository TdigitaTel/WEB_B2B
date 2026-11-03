'use client';
import {useEffect,useRef} from 'react';
type Marks={created_in_web?:boolean|null;entered_in_exit?:boolean;exit_removed_at?:string|null};
function Mark({label,title,checked,unknown=false}:{label:string;title:string;checked:boolean;unknown?:boolean}){
 const ref=useRef<HTMLInputElement>(null);
 useEffect(()=>{if(ref.current)ref.current.indeterminate=unknown},[unknown]);
 return <label title={unknown?'Origen WEB sin confirmar':title}><input ref={ref} type="checkbox" checked={checked} disabled readOnly aria-label={label} aria-checked={unknown?'mixed':checked}/></label>
}
export function OrderLineMarkHeaders({customer=false}:{customer?:boolean}){
 return <span className="order-line-marks-head"><span>WEB</span><span>{customer?'Tienda':'EXIT'}</span><span>Eliminado</span></span>
}
export function OrderLineMarks({line,customer=false}:{line:Marks;customer?:boolean}){
 return <span className="order-line-marks" role="group" aria-label="Seguimiento del artículo">
  <Mark label="WEB" title="Creado desde el carrito WEB" checked={line.created_in_web===true} unknown={line.created_in_web==null}/>
  <Mark label={customer?'Tienda':'EXIT'} title={customer?'Registrado en tienda':'Ingresado en EXIT'} checked={!!line.entered_in_exit}/>
  <Mark label="Eliminado" title={customer?'Eliminado: no se va a atender':'Eliminado en EXIT: no se va a atender'} checked={!!line.exit_removed_at}/>
 </span>
}
