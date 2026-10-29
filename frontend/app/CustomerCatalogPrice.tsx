"use client";
import {useEffect,useState} from "react";
const endpoint="/api/v1/store/customer-access/catalog-price";
async function responseData(response:Response){
 if(response.status===401)window.dispatchEvent(new Event("session-expired"));
 const data=await response.json().catch(()=>null);
 if(!response.ok)throw new Error(typeof data?.detail==="string"?data.detail:"No se pudo guardar la presentación de precios");
 return data as {highlight_price_without_tax:boolean};
}
export default function CustomerCatalogPrice({code}:{code:string}){
 const [withoutTax,setWithoutTax]=useState(false),[loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
 useEffect(()=>{
  let active=true;setLoaded(false);setError("");setMessage("");
  fetch(`${endpoint}?${new URLSearchParams({customer_code:code})}`,{credentials:"include",cache:"no-store"})
   .then(responseData).then(data=>{if(active){setWithoutTax(data.highlight_price_without_tax);setLoaded(true)}})
   .catch(e=>{if(active)setError((e as Error).message)});
  return()=>{active=false};
 },[code]);
 async function save(){setBusy(true);setError("");setMessage("");try{const data=await responseData(await fetch(endpoint,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({customer_code:code,highlight_price_without_tax:withoutTax})}));setWithoutTax(data.highlight_price_without_tax);setMessage("Precio destacado guardado. Se aplica al cargar los productos del cliente y de sus subusuarios.")}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <section className="section"><h3>Precios del catálogo</h3><label>Precio que se muestra destacado<select className="input" value={withoutTax?"without":"with"} disabled={!loaded||busy} onChange={e=>{setWithoutTax(e.target.value==="without");setMessage("")}}><option value="with">Con IVA destacado · sin IVA más pequeño</option><option value="without">Sin IVA destacado · con IVA más pequeño</option></select></label><p className="small">Se aplica al catálogo, favoritos y sugerencias de este cliente y sus subusuarios.</p><button className="secondary" disabled={!loaded||busy} onClick={()=>void save()}>{busy?"Guardando…":"Guardar precio destacado"}</button>{error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status">{message}</p>}</section>;
}
