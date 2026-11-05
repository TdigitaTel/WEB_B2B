"use client";
import {useId} from 'react';
import './pickup-timing-choice.css';
export default function PickupTimingChoice({scheduled,onChange,label='Cuándo recoger',immediateAvailable=true}:{scheduled:boolean;onChange:(value:boolean)=>void;label?:string;immediateAvailable?:boolean}){
 const name=useId();
 return <fieldset className="pickup-timing-choice"><legend>{label}</legend><div><label><input type="radio" name={name} value="immediate" checked={!scheduled} disabled={!immediateAvailable} onChange={()=>onChange(false)}/><span>Inmediata</span></label><label><input type="radio" name={name} value="scheduled" checked={scheduled} onChange={()=>onChange(true)}/><span>Fecha programada</span></label></div>{!immediateAvailable&&<small>La recogida inmediata no está disponible en el horario actual. Selecciona una fecha programada.</small>}</fieldset>
}
