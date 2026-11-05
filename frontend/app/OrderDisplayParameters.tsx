'use client';
import {useEffect,useState,type FormEvent} from 'react';
export default function OrderDisplayParameters({value,onSave}:{value:boolean;onSave:(value:boolean)=>Promise<void>}){
 const [images,setImages]=useState(value),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 useEffect(()=>setImages(value),[value]);
 async function save(event:FormEvent){event.preventDefault();if(busy)return;setBusy(true);setError('');setMessage('');try{await onSave(images);setMessage('Preferencia de pedidos guardada.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <form className="section order-display-parameters" onSubmit={save}><h2>Visualización de pedidos</h2><p>Configura cómo quieres ver las líneas de los pedidos. Esta preferencia se guarda para tu usuario.</p><label className="order-display-image-option"><input type="checkbox" checked={images} disabled={busy} onChange={event=>{setImages(event.target.checked);setMessage('')}}/> Mostrar microfotos en las líneas de pedidos</label><p className="small">Se aplica a pedidos. Las comandas de Kardex y SGA mantienen su vista de texto.</p>{error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status">{message}</p>}<button className="primary" disabled={busy}>{busy?'Guardando…':'Guardar visualización'}</button></form>
}
