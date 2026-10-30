"use client";
import {FormEvent,useEffect,useRef,useState} from "react";
import {QrLogin} from "./QrAccess";
import {useLoginAppearance} from "./LoginAppearance";
import "./login-screen.css";

type Props={onLogin:(email:string,password:string)=>Promise<void>;onQrLogin:(token:string)=>Promise<void>;error:string;onBeginAccess:()=>void};
export default function LoginScreen({onLogin,onQrLogin,error,onBeginAccess}:Props){
 const appearance=useLoginAppearance(),container=useRef<HTMLDivElement>(null);
 const [failedImage,setFailedImage]=useState<string|null>(null),[kiosk,setKiosk]=useState(false);
 const imageUrl=appearance.image_url!==failedImage?appearance.image_url:null;
 const [loginError,setLoginError]=useState(''),[email,setEmail]=useState(''),[password,setPassword]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
  // Tall portrait screens use the same top-to-bottom composition as phones.
  const forced=new URLSearchParams(window.location.search).get('kiosk')==='1';
  const updateLayout=()=>{
   if(container.current?.contains(document.activeElement)&&document.activeElement instanceof HTMLInputElement)return;
   setKiosk(forced||window.matchMedia('(min-width: 721px) and (min-height: 900px) and (max-aspect-ratio: 2/3)').matches);
  };
  updateLayout();window.addEventListener('resize',updateLayout);
  let frame=0;
  const reveal=()=>{
   cancelAnimationFrame(frame);
   frame=requestAnimationFrame(()=>{
    const field=document.activeElement;
    if(field instanceof HTMLInputElement&&container.current?.contains(field))field.scrollIntoView({block:'center',behavior:'auto'});
   });
  };
  window.visualViewport?.addEventListener('resize',reveal);
  return()=>{cancelAnimationFrame(frame);window.removeEventListener('resize',updateLayout);window.visualViewport?.removeEventListener('resize',reveal)};
 },[]);
 function begin(){onBeginAccess();setLoginError('')}
 async function submit(event:FormEvent){event.preventDefault();if(busy)return;begin();setBusy(true);try{await onLogin(email,password)}catch(error){setLoginError((error as Error).message)}finally{setBusy(false)}}
 const message=loginError||error;
 return <div ref={container} className={`login access-screen ${kiosk?'login--kiosk':''}`}>
  <section className={`login-brand ${imageUrl?'has-cover':''}`} aria-label="Bermúdez Ulloa">
   {imageUrl?<img className="login-cover" src={imageUrl} alt="Bermúdez Ulloa · Imagen de acceso" onError={()=>setFailedImage(imageUrl)}/>:<div className="login-brand-copy"><img className="login-logo" src="/bermudez-ulloa-logo.jpg" alt="Bermúdez Ulloa"/><h1>Material profesional.<br/>Pedido en segundos.</h1><p>Consulta tu precio, comprueba stock local y deja el pedido preparado para recoger en Almeiras.</p></div>}
  </section>
  <section className="login-panel" aria-labelledby="access-title"><div className="login-form">
   <form onSubmit={submit} aria-labelledby="access-title"><h2 id="access-title">Acceso profesional</h2><p className="small">Entra con la cuenta de tu empresa.</p>
    <label className="label" htmlFor="access-user">Usuario o email</label><input id="access-user" className="input" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} enterKeyHint="next" value={email} onChange={event=>{begin();setEmail(event.target.value)}} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();document.getElementById('access-password')?.focus()}}}/>
    <label className="label" htmlFor="access-password">Contraseña</label><input id="access-password" className="input" name="password" type="password" autoComplete="current-password" enterKeyHint="go" value={password} onChange={event=>{begin();setPassword(event.target.value)}} aria-describedby={message?'access-message':undefined}/>
    {message&&<p id="access-message" className="error" role="alert">{message}</p>}
    <button type="submit" className="primary block" disabled={busy}>{busy?'Entrando…':'Iniciar sesión'}</button>
   </form>
   <details className="login-qr"><summary>Acceso con QR</summary><QrLogin onLogin={onQrLogin}/></details>
  </div></section>
 </div>;
}
