"use client";
import {useEffect,useRef,useState} from 'react';
export type PickupSlot={start:string;end:string;ready_at:string};
export default function PickupTimeSlots({company,delegation,day,value,onChange,onReady}:{company:number;delegation:string;day:string;value:PickupSlot|null;onChange:(slot:PickupSlot|null)=>void;onReady?:(date:string|null)=>void}){
 const [slots,setSlots]=useState<PickupSlot[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const callbacks=useRef({onChange,onReady,value});callbacks.current={onChange,onReady,value};
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');setSlots([]);callbacks.current.onReady?.(null);
  if(!day){setLoading(false);callbacks.current.onChange(null);return;}
  fetch(`/api/v1/pickup-availability?${new URLSearchParams({company:String(company),delegation,scheduled_date:day})}`,{credentials:'include',signal:controller.signal}).then(async res=>{const data=await res.json();if(!res.ok)throw Error(data.detail||'No se pudieron consultar los horarios');return data}).then(data=>{
   if(controller.signal.aborted)return;const next:PickupSlot[]=data.pickup_slots||[];setSlots(next);const selected=next.find(slot=>slot.start===callbacks.current.value?.start&&slot.end===callbacks.current.value?.end)||next[0]||null;callbacks.current.onChange(selected);callbacks.current.onReady?.(selected?.ready_at||null);
  }).catch(e=>{if(!controller.signal.aborted){setError(e.message);callbacks.current.onChange(null)}}).finally(()=>{if(!controller.signal.aborted)setLoading(false)});
  return()=>controller.abort();
 },[company,delegation,day]);
 return <div className="pickup-time-slots"><label className="label">Franja horaria<select className="select" aria-label="Franja horaria" disabled={loading||!slots.length} value={value?`${value.start}-${value.end}`:''} onChange={e=>{const selected=slots.find(slot=>`${slot.start}-${slot.end}`===e.target.value)||null;onChange(selected);onReady?.(selected?.ready_at||null)}}>{loading?<option>Consultando horarios…</option>:!slots.length?<option>Sin franjas disponibles</option>:slots.map(slot=><option key={slot.start} value={`${slot.start}-${slot.end}`}>{slot.start} – {slot.end}</option>)}</select></label>{error&&<p className="error" role="alert">{error}</p>}{!loading&&!error&&!slots.length&&<p role="status">No hay franjas que permitan preparar el pedido en el horario de esta fecha.</p>}</div>
}
