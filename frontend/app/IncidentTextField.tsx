'use client';
import {useState} from 'react';
export default function IncidentTextField({label,value,onChange,required=false,maxLength=1000}:{label:string;value:string;onChange:(value:string)=>void;required?:boolean;maxLength?:number}){
 const [open,setOpen]=useState(false),[draft,setDraft]=useState('');
 return <><label className="incident-text-field">{label}{required?' *':''}<button type="button" className="secondary" aria-label={`Editar ${label}`} title={value||label} onClick={()=>{setDraft(value);setOpen(true)}}>{value?'Ver / editar':'Añadir texto'} ✎</button></label>{open&&<div className="incident-lookup" role="dialog" aria-modal="true" aria-label={label} onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();setOpen(false)}}}><div className="panel"><h3>{label}</h3><textarea autoFocus aria-label={label} maxLength={maxLength} value={draft} onChange={e=>setDraft(e.target.value)}/><div className="incident-actions"><button type="button" disabled={required&&!draft.trim()} onClick={()=>{onChange(draft);setOpen(false)}}>Aplicar descripción</button><button type="button" onClick={()=>setOpen(false)}>Cancelar descripción</button></div></div></div>}</>;
}
