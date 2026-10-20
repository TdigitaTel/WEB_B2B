"use client";
import {useEffect,useRef,useState} from "react";
import jsQR from "jsqr";

function extractToken(value:string){
 const trimmed=value.trim();
 try{const link=new URL(trimmed);return new URLSearchParams(link.hash.slice(1)).get("qr")||""}catch{return trimmed}
}

export function QrLogin({onLogin}:{onLogin:(token:string)=>Promise<void>}){
 const [value,setValue]=useState(""),[error,setError]=useState(""),[busy,setBusy]=useState(false),[camera,setCamera]=useState(false),[cameraVersion,setCameraVersion]=useState(0),[cameraReady,setCameraReady]=useState(false),[starting,setStarting]=useState(false);
 const video=useRef<HTMLVideoElement>(null),stream=useRef<MediaStream|null>(null),processing=useRef(false),cameraRequest=useRef(0);
 function stop(){cameraRequest.current++;setCameraReady(false);setStarting(false);stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;setCamera(false)}
 async function enter(raw:string){if(processing.current)return;const token=extractToken(raw);if(!/^[a-f0-9-]{36}\.[A-Za-z0-9_-]{43}$/.test(token)){setError("El código no es un QR de acceso válido");return}processing.current=true;stop();setBusy(true);setError("");try{await onLogin(token)}catch(e){setError((e as Error).message)}finally{processing.current=false;setBusy(false)}}
 useEffect(()=>{const token=new URLSearchParams(window.location.hash.slice(1)).get("qr");if(token){history.replaceState(null,"",location.pathname+location.search);void enter(token)}return()=>{cameraRequest.current++;stream.current?.getTracks().forEach(track=>track.stop())}},[]);
 useEffect(()=>{
  if(!camera||!stream.current||!video.current)return;
  const element=video.current,current=stream.current;
  let active=true,frame=0;
  element.srcObject=current;
  element.muted=true;
  const canvas=document.createElement("canvas"),ctx=canvas.getContext("2d",{willReadFrequently:true});
  function read(){
   if(!active)return;
   if(element.readyState>=2&&element.videoWidth>0&&element.videoHeight>0&&ctx){
    canvas.width=element.videoWidth;canvas.height=element.videoHeight;
    ctx.drawImage(element,0,0);
    const pixels=ctx.getImageData(0,0,canvas.width,canvas.height),result=jsQR(pixels.data,pixels.width,pixels.height);
    if(result&&/^[a-f0-9-]{36}\.[A-Za-z0-9_-]{43}$/.test(extractToken(result.data))){void enter(result.data);return}
   }
   frame=requestAnimationFrame(read);
  }
  const timeout=window.setTimeout(()=>{if(active&&(!element.videoWidth||element.paused)){setError("La cámara se abrió pero no envía imagen. Cierra otras aplicaciones que la estén usando y pulsa Escanear QR de nuevo.");stop()}},10000);
  element.play().then(()=>{if(active)frame=requestAnimationFrame(read)}).catch(()=>{if(active){setError("No se pudo reproducir la cámara. Revisa el permiso del navegador y vuelve a escanear.");stop()}});
  return()=>{active=false;cancelAnimationFrame(frame);clearTimeout(timeout);element.pause();element.srcObject=null};
 },[camera,cameraVersion]);
 async function start(){
  stop();setError("");setStarting(true);const request=cameraRequest.current;
  try{
   if(!navigator.mediaDevices?.getUserMedia)throw Error("La cámara requiere HTTPS. Puedes leer una imagen del QR desde Avanzado.");
   const captured=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:"environment"},width:{ideal:1280},height:{ideal:720}},audio:false});
   if(request!==cameraRequest.current){captured.getTracks().forEach(track=>track.stop());return}
   stream.current=captured;setCameraReady(false);setCamera(true);setCameraVersion(value=>value+1);
  }catch(e){if(request===cameraRequest.current){setError((e as Error).message);stop()}}
  finally{if(request===cameraRequest.current)setStarting(false)}
 }
 async function image(file:File){setError("");const url=URL.createObjectURL(file);try{const picture=new Image();picture.src=url;await picture.decode();const canvas=document.createElement("canvas");canvas.width=picture.width;canvas.height=picture.height;const ctx=canvas.getContext("2d");if(!ctx)return;ctx.drawImage(picture,0,0);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height);const qr=jsQR(pixels.data,pixels.width,pixels.height);if(!qr)throw Error("No se encontró un código QR legible en la imagen");await enter(qr.data)}catch(e){setError((e as Error).message)}finally{URL.revokeObjectURL(url)}}
 return <div className="qr-login"><h3>Escanea tu QR</h3><p className="small">Acerca tu código de cliente a la cámara para entrar.</p><button type="button" className="secondary block" disabled={busy||starting} onClick={()=>void start()}>{busy?"Entrando…":starting?"Abriendo cámara…":camera?"Reiniciar cámara":"Escanear QR"}</button>{camera&&<>{!cameraReady&&<p className="small" role="status">Conectando con la cámara…</p>}<video ref={video} autoPlay muted playsInline onPlaying={()=>setCameraReady(true)} className="qr-camera"/><button type="button" className="ghost" onClick={stop}>Cerrar cámara</button></>}{error&&<p className="error" role="alert">{error}</p>}<details className="qr-advanced"><summary>Avanzado</summary><label className="label">Seleccionar imagen del QR<input type="file" accept="image/*" disabled={busy} onChange={event=>{const file=event.target.files?.[0];if(file)void image(file);event.target.value=""}}/></label><label className="label">Enlace de acceso<input className="input" autoComplete="off" type="password" value={value} onChange={e=>setValue(e.target.value)}/></label><button type="button" className="secondary" disabled={busy||!value.trim()} onClick={()=>void enter(value)}>Entrar con enlace</button></details></div>

}

type Qr={image:string;url:string;expires_at:string;customer_code:string};
export function CustomerQr({code}:{code:string}){
 const [qr,setQr]=useState<Qr|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 useEffect(()=>{setQr(null);setError("")},[code]);
 async function request(action:"show"|"regenerate"|"revoke"){
  if(action!=="show"&&!window.confirm(action==="revoke"?"¿Deshabilitar el QR del cliente?":"¿Generar otro QR? El anterior dejará de funcionar."))return;
  setBusy(true);setError("");try{const response=await fetch(`/api/v1/store/customer-access/qr${action==="revoke"?"/revoke":""}`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({customer_code:code,regenerate:action==="regenerate"})});const data=await response.json();if(!response.ok)throw Error(data.detail||"No se pudo generar el QR");setQr(action==="revoke"?null:data)}catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <section className="access-credentials"><h3>Acceso con QR</h3><p>El QR permite entrar a la cuenta. Entrégalo solo al cliente. Caduca a los 90 días.</p><div className="access-actions"><button className="secondary" disabled={busy} onClick={()=>void request("show")}>Ver QR</button><button className="secondary" disabled={busy} onClick={()=>void request("regenerate")}>Generar nuevo QR</button><button className="secondary" disabled={busy} onClick={()=>void request("revoke")}>Deshabilitar QR</button></div>{error&&<p className="error" role="alert">{error}</p>}{qr&&<><img className="customer-access-qr" src={qr.image} alt={`QR de acceso del cliente ${code}`}/><p>Válido hasta {new Date(qr.expires_at).toLocaleDateString("es-ES")}</p><a className="secondary" href={qr.image} download={`acceso-cliente-${code}.svg`}>Descargar QR</a></>}</section>
}
