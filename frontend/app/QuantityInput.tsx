"use client";
import {useEffect,useRef,useState} from "react";

export default function QuantityInput({value,onChange,label,className}:{value:number;onChange:(value:number)=>void;label:string;className?:string}){
 const [draft,setDraft]=useState(String(value));
 const focused=useRef(false);
 const emitted=useRef(value);
 useEffect(()=>{if(!focused.current){setDraft(String(value));emitted.current=value}},[value]);
 function emit(next:number){if(next!==emitted.current){emitted.current=next;onChange(next)}}
 function finish(){
  focused.current=false;
  const parsed=Number(draft);
  const next=Number.isFinite(parsed)?Math.min(99999,Math.max(1,parsed)):1;
  setDraft(String(next));emit(next);
 }
 return <input aria-label={label} className={className} type="number" inputMode="decimal" min="1" max="99999" step="1" value={draft} onFocus={()=>{focused.current=true}} onChange={event=>{
  const text=event.target.value;setDraft(text);
  const next=Number(text);
  if(text!==""&&Number.isFinite(next)&&next>=1&&next<=99999)emit(next);
 }} onBlur={finish} onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();event.currentTarget.blur()}}}/>;
}
