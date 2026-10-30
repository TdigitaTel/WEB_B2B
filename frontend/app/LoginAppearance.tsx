"use client";
import {useAutoRefresh} from "./AutoRefresh";
import {useEffect,useState} from "react";
import "./login-appearance.css";
import {Appearance, prepareLoginImage, readAppearanceResponse, validateLoginImage} from "./login-image-upload";
export type {Appearance} from "./login-image-upload";
export function useLoginAppearance(){
 const [appearance,setAppearance]=useState<Appearance>({image_url:null});
 useEffect(()=>{const controller=new AbortController();fetch("/api/v1/login-appearance",{cache:"no-store",signal:controller.signal}).then(readAppearanceResponse).then(setAppearance).catch(()=>{});return()=>controller.abort()},[]);
  useAutoRefresh(async signal=>{const data=await fetch("/api/v1/login-appearance",{cache:"no-store",signal}).then(readAppearanceResponse);if(!signal.aborted)setAppearance(data)});
  return appearance;
}
export default function LoginAppearanceSettings(){
 const initial=useLoginAppearance();
 const [current,setCurrent]=useState<Appearance|null>(null),[file,setFile]=useState<File|null>(null),[preview,setPreview]=useState(""),[busy,setBusy]=useState(false),[preparing,setPreparing]=useState(false),[message,setMessage]=useState(""),[error,setError]=useState("");
 const saved=current||initial;
 useEffect(()=>{if(!file){setPreview("");return}const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url)},[file]);
 async function persist(restore=false){
  if(!restore&&!file)return;
  setBusy(true);setError("");setMessage("");
  try{
   const body=new FormData();
   if(!restore&&file){setPreparing(true);const prepared=await prepareLoginImage(file);setPreparing(false);body.append("file",prepared)}
   const response=await fetch("/api/v1/login-appearance",{method:restore?"DELETE":"PUT",credentials:"include",...(restore?{}:{body})});
   if(response.status===401)window.dispatchEvent(new Event("session-expired"));
   const data=await readAppearanceResponse(response);setCurrent(data);setFile(null);
   setMessage(restore?"Diseño original restaurado.":"Imagen de acceso guardada. Se mostrará al entrar en la web.");
  }catch(e){setError((e as Error).message)}finally{setPreparing(false);setBusy(false)}
 }

 return <section className="appearance-settings"><h2>Imagen de acceso</h2><p>Elige el gráfico de la pantalla donde los clientes inician sesión.</p><div className="appearance-layout"><div><label className="label" htmlFor="login-image-file">Subir imagen</label><input id="login-image-file" key={saved.image_url||"default"} type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={event=>{const selected=event.target.files?.[0];setError("");setMessage("");setFile(null);if(!selected)return;try{validateLoginImage(selected);setFile(selected)}catch(e){setError((e as Error).message);event.target.value=""}}}/><p className="small">JPG, PNG o WebP · Máximo 8 MB. Hasta 20 megapíxeles. Se optimiza automáticamente antes de subir. Recomendado: 1600 × 1800 px. La imagen se adapta sin deformarse ni recortarse.</p><p className="small">La imagen personalizada se muestra sin textos, logotipos ni capas oscuras añadidas. En móvil y kiosco ocupa una cabecera compacta. El texto integrado en el gráfico se conserva.</p><div className="appearance-actions"><button className="primary" disabled={!file||busy} onClick={()=>void persist()}>{preparing?"Preparando imagen…":busy?"Guardando…":"Guardar imagen"}</button><button className="ghost" disabled={busy||!saved.image_url} onClick={()=>void persist(true)}>Restaurar diseño original</button></div>{message&&<p role="status">{message}</p>}{error&&<p className="error" role="alert">{error}</p>}</div><div><h3>Vista previa {file?"· Sin guardar":""}</h3><div className={`access-image-preview ${(preview||saved.image_url)?"has-cover":""}`}>{(preview||saved.image_url)?<img src={preview||saved.image_url||""} alt="Vista previa de la imagen de acceso"/>:<div><img className="preview-logo" src="/bermudez-ulloa-logo.jpg" alt="Bermúdez Ulloa"/><h3>Material profesional.<br/>Pedido en segundos.</h3><p>Tu portal profesional</p></div>}</div></div></div></section>;
}
