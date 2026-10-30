"use client";
import {useAutoRefresh} from "./AutoRefresh";
import {FormEvent, useEffect, useState} from "react";

type Config = {enabled:boolean; accessory_terms:string[]; piece_names:string[]; materials:string[]};
const fields = [
  ["accessory_terms", "Palabras que significan accesorios", "Por ejemplo: accesorios, piezas, componentes, conexiones."],
  ["materials", "Materiales reconocidos", "Por ejemplo: latón, cobre, inox, inoxidable, PVC."],
] as const;

export default function SearchParameters(){
  const [dirty,setDirty]=useState(false);
  const [config,setConfig]=useState<Config|null>(null);
  const [words,setWords]=useState({accessory_terms:"",piece_names:"",materials:""});
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  async function request(method="GET",body?:Config){
    const response=await fetch("/api/v1/store/search-settings",{method,credentials:"include",headers:{"Content-Type":"application/json"},...(body?{body:JSON.stringify(body)}:{})});
    const data=await response.json();
    if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"Revisa las listas: máximo 80 palabras individuales por campo, sin signos ni comodines.");
    return data as Config;
  }
  function load(data:Config){setDirty(false);setConfig(data);setWords({accessory_terms:data.accessory_terms.join(", "),piece_names:data.piece_names.join(", "),materials:data.materials.join(", ")})}
  useEffect(()=>{request().then(load).catch(e=>setError(e.message))},[]);
  useAutoRefresh(async signal=>{const data=await request();if(!signal.aborted)load(data)},!!config&&!dirty&&!busy);
  async function save(event:FormEvent){
    event.preventDefault();if(!config)return;setBusy(true);setError("");setMessage("");
    const split=(value:string)=>value.split(/[,;\n]+/).map(word=>word.trim()).filter(Boolean);
    try{load(await request("PATCH",{enabled:config.enabled,accessory_terms:split(words.accessory_terms),piece_names:split(words.piece_names),materials:split(words.materials)}));setMessage("Parámetros del buscador guardados. Se aplican en las próximas búsquedas.")}catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  return <section className="panel" style={{marginTop:24}}><h2>Buscador</h2><p>Permite encontrar accesorios aunque el cliente escriba «piezas de latón» o «componentes de cobre». El material y las medidas siguen siendo obligatorios.</p>{error&&<p className="error" role="alert">{error}</p>}{config?<form onSubmit={save}><label><input type="checkbox" checked={config.enabled} disabled={busy} onChange={e=>{setDirty(true);setConfig({...config,enabled:e.target.checked})}}/> Simplificar búsquedas por material</label>{fields.map(([key,label,hint])=><label key={key} style={{display:"block",marginTop:16}}>{label}<textarea className="input" rows={4} required disabled={busy} value={words[key]} onChange={e=>{setDirty(true);setWords({...words,[key]:e.target.value})}}/><small>{hint} Separa las palabras con comas o saltos de línea.</small></label>)}<p>Cuando hay un material reconocido, se omiten palabras generales como accesorios, piezas o componentes. «Componentes de latón» busca igual que «latón»; las medidas y otros términos se conservan. Los resultados pueden incluir cualquier artículo de ese material.</p><button className="primary" disabled={busy}>{busy?"Guardando…":"Guardar buscador"}</button>{message&&<p role="status">{message}</p>}</form>:!error&&<p>Cargando parámetros del buscador…</p>}</section>
}
