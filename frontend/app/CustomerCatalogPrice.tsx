"use client";
import {useAutoRefresh} from "./AutoRefresh";
import {useEffect,useState} from "react";
const endpoint="/api/v1/account/catalog-price";
async function responseData(response:Response){
 if(response.status===401)window.dispatchEvent(new Event("session-expired"));
 const data=await response.json().catch(()=>null);
 if(!response.ok)throw new Error(typeof data?.detail==="string"?data.detail:"No se pudo guardar la presentación de precios");
 return data as {highlight_price_without_tax:boolean};
}
export default function CustomerCatalogPrice({canEdit,onSaved}:{canEdit:boolean;onSaved:(withoutTax:boolean)=>void}){
 const [dirty,setDirty]=useState(false);
 const [withoutTax,setWithoutTax]=useState(false),[loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
 useEffect(()=>{
  let active=true;
  fetch(endpoint,{credentials:"include",cache:"no-store"}).then(responseData)
   .then(data=>{if(active){setWithoutTax(data.highlight_price_without_tax);setLoaded(true)}})
   .catch(e=>{if(active)setError((e as Error).message)});
  return()=>{active=false};
 },[]);
 useAutoRefresh(async signal=>{const data=await fetch(endpoint,{credentials:"include",cache:"no-store",signal}).then(responseData);if(!signal.aborted)setWithoutTax(data.highlight_price_without_tax)},loaded&&!dirty&&!busy);
 async function save(){setBusy(true);setError("");setMessage("");try{
  const data=await responseData(await fetch(endpoint,{method:"PATCH",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({highlight_price_without_tax:withoutTax})}));
  setWithoutTax(data.highlight_price_without_tax);setDirty(false);onSaved(data.highlight_price_without_tax);
  setMessage("Precio destacado guardado. Ya se aplica a tu catálogo y favoritos; tus subusuarios usarán esta elección al cargar los productos.");
 }catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <section className="section"><h2>Precios del catálogo</h2>{canEdit?<><label>¿Qué precio quieres ver destacado?<select className="input" value={withoutTax?"without":"with"} disabled={!loaded||busy} onChange={e=>{setDirty(true);setWithoutTax(e.target.value==="without");setMessage("")}}><option value="with">Con IVA destacado · sin IVA más pequeño</option><option value="without">Sin IVA destacado · con IVA más pequeño</option></select></label><p className="small">Esta elección se aplica a tu cliente y a todos sus subusuarios.</p><button className="primary" disabled={!loaded||busy} onClick={()=>void save()}>{busy?"Guardando…":"Guardar precio destacado"}</button></>:<p>{loaded?`Tu catálogo destaca el precio ${withoutTax?"sin IVA":"con IVA"}. `:"Cargando preferencia… "}Esta opción la configura la cuenta principal de tu cliente.</p>}{error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status">{message}</p>}</section>;
}
