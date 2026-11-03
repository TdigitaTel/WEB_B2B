'use client';
import {useEffect,useRef} from 'react';
type Marks={created_in_web?:boolean|null;entered_in_exit?:boolean;exit_removed_at?:string|null};
function Mark({label,checked,unknown=false}:{label:string;checked:boolean;unknown?:boolean}){
 const ref=useRef<HTMLInputElement>(null);
 useEffect(()=>{if(ref.current)ref.current.indeterminate=unknown},[unknown]);
 return <label title={unknown?'Origen histórico no registrado':label}><input ref={ref} type="checkbox" checked={checked} disabled readOnly aria-label={label} aria-checked={unknown?'mixed':checked}/>{label}{unknown&&' (sin registro)'}</label>
}
export function OrderLineMarks({line}:{line:Marks}){
 return <span className="order-line-marks" role="group" aria-label="Seguimiento del artículo">
  <Mark label="Generado en WEB" checked={line.created_in_web===true} unknown={line.created_in_web==null}/>
  <Mark label="Ingresado en EXIT" checked={!!line.entered_in_exit}/>
  <Mark label="Eliminado en EXIT" checked={!!line.exit_removed_at}/>
 </span>
}
