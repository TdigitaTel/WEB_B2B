"use client";
import {useEffect,useRef,useState} from "react";
import jsQR from "jsqr";

function extractToken(value:string){
 const trimmed=value.trim();
 try{const link=new URL(trimmed);return new URLSearchParams(link.hash.slice(1)).get("qr")||""}catch{return trimmed}
}

export function QrLogin({onLogin}:{onLogin:(token:string)=>Promise<void>}){
 const [open,setOpen]=useState(false),[value,setValue]=useState(""),[error,setError]=useState(""),[busy,setBusy]=useState(false),[camera,setCamera]=useState(false);
 const video=useRef<HTMLVideoElement>(null),stream=useRef<MediaStream|null>(null),processing=useRef(false);
 function stop(){stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;setCamera(false)}
 async function enter(raw:string){if(processing.current)return;const token=extractToken(raw);if(!/^[a-f0-9-]{36}\.[A-Za-z0-9_-]{43}$/.test(token)){setError("El código no es un QR de acceso válido");return}processing.current=true;stop();setBusy(true);setError("");try{await onLogin(token)}catch(e){setError((e as Error).message)}finally{processing.current=false;setBusy(false)}}
 useEffect(()=>{const token=new URLSearchParams(window.location.hash.slice(1)).get("qr");if(token){history.replaceState(null,"",location.pathname+location.search);setOpen(true);void enter(token)}return()=>{stream.current?.getTracks().forEach(track=>track.stop())}},[]);
 useEffect(()=>{if(!camera)return;let frame=0,active=true;const canvas=document.createElement("canvas");const ctx=canvas.getContext("2d",{willReadFrequently:true});function read(){if(!active)return;const element=video.current;if(element&&element.readyState>=2&&ctx){canvas.width=element.videoWidth;canvas.height=element.videoHeight;ctx.drawImage(element,0,0);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height);const result=jsQR(pixels.data,pixels.width,pixels.height);if(result){void enter(result.data);return}}frame=requestAnimationFrame(read)}frame=requestAnimationFrame(read);return()=>{active=false;cancelAnimationFrame(frame)}},[camera]);
 async function start(){stop();setError("");try{if(!navigator.mediaDevices?.getUserMedia)throw Error("La cámara requiere HTTPS. Puedes leer una imagen del QR o escanearlo con la cámara de tu móvil.");stream.current=await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"},audio:false});setCamera(true);requestAnimationFrame(()=>{if(video.current){video.current.srcObject=stream.current;void video.current.play()}})}catch(e){setError((e as Error).message)}}
 async function image(file:File){setError("");const url=URL.createObjectURL(file);try{const picture=new Image();picture.src=url;await picture.decode();const canvas=document.createElement("canvas");canvas.width=picture.width;canvas.height=picture.height;const ctx=canvas.getContext("2d");if(!ctx)return;ctx.drawImage(picture,0,0);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height);const qr=jsQR(pixels.data,pixels.width,pixels.height);if(!qr)throw Error("No se encontró un código QR legible en la imagen");await enter(qr.data)}catch(e){setError((e as Error).message)}finally{URL.revokeObjectURL(url)}}
 return <div className="qr-login"><button type="button" className="secondary block" onClick={()=>{if(open)stop();setOpen(!open)}}>Acceder con QR</button>{open&&<div><p>Escanea tu QR de cliente o selecciona su imagen. También puedes abrirlo con la cámara del móvil.</p><button type="button" className="secondary" disabled={busy} onClick={()=>void start()}>Abrir cámara</button>{camera&&<><video ref={video} muted playsInline className="qr-camera"/><button type="button" className="ghost" onClick={stop}>Cerrar cámara</button></>}<label className="label">Leer imagen del QR<input type="file" accept="image/*" disabled={busy} onChange={event=>{const file=event.target.files?.[0];if(file)void image(file);event.target.value=""}}/></label><label className="label">O pega el enlace de acceso<input className="input" autoComplete="off" type="password" value={value} onChange={e=>setValue(e.target.value)}/></label><button type="button" className="primary" disabled={busy||!value.trim()} onClick={()=>void enter(value)}>{busy?"Entrando…":"Entrar con QR"}</button>{error&&<p className="error" role="alert">{error}</p>}</div>}</div>
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
