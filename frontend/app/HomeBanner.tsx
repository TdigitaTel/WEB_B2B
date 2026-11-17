'use client';
import {useEffect,useState} from 'react';
import './home-banner.css';
export type BannerSlide={id:string;alt:string;enabled:boolean;image_url:string|null};
export type BannerConfig={revision:string;interval_seconds:number;slides:BannerSlide[]};
export const originalBanner:BannerSlide={id:'original',alt:'Todo lo que necesitas. Listo para tu próxima obra.',enabled:true,image_url:null};
export const initialBanner:BannerConfig={revision:'initial',interval_seconds:5,slides:[originalBanner]};
export async function readBannerResponse(response:Response):Promise<BannerConfig>{
 const body=await response.json().catch(()=>null);
 if(!response.ok){if(response.status===401)window.dispatchEvent(new Event('session-expired'));throw Error(typeof body?.detail==='string'?body.detail:response.status===413?'La imagen es demasiado grande.':'No se pudo cargar o guardar el banner. Inténtalo de nuevo.')}
 if(!body||!Array.isArray(body.slides)||!Number.isFinite(body.interval_seconds))throw Error('El servidor no devolvió una configuración válida.');
 return body;
}
export default function HomeBanner({customerName,onExplore,configuration}:{customerName?:string;onExplore:()=>void;configuration?:BannerConfig}){
 const [remote,setRemote]=useState(initialBanner),[index,setIndex]=useState(0),[paused,setPaused]=useState(false),[hidden,setHidden]=useState(false),[reduced,setReduced]=useState(false),[failed,setFailed]=useState<string[]>([]);
 const config=configuration||remote;
 const active=config.slides.filter(slide=>slide.enabled),slides=active.length?active:[originalBanner];
 const current=slides[index%slides.length];
 useEffect(()=>{if(configuration)return;const controller=new AbortController();fetch('/api/v1/home-banner',{credentials:'include',cache:'no-store',signal:controller.signal}).then(readBannerResponse).then(setRemote).catch(()=>{});return()=>controller.abort()},[configuration]);
 useEffect(()=>{setIndex(0);setFailed([])},[config.revision]);
 useEffect(()=>{const visibility=()=>setHidden(document.hidden);visibility();document.addEventListener('visibilitychange',visibility);const motion=window.matchMedia?.('(prefers-reduced-motion: reduce)');setReduced(!!motion?.matches);const change=()=>setReduced(!!motion?.matches);motion?.addEventListener?.('change',change);return()=>{document.removeEventListener('visibilitychange',visibility);motion?.removeEventListener?.('change',change)}},[]);
 useEffect(()=>{if(slides.length<2||paused||hidden||reduced)return;const timer=setTimeout(()=>setIndex(value=>(value+1)%slides.length),Math.max(3,config.interval_seconds)*1000);return()=>clearTimeout(timer)},[index,slides.length,config.interval_seconds,paused,hidden,reduced]);
 const original=!current.image_url||failed.includes(current.id);
 return <section className="home-banner" aria-label="Información destacada" aria-roledescription="carrusel">
  <div className="home-banner-slide" role="group" aria-roledescription="diapositiva" aria-label={`${index%slides.length+1} de ${slides.length}`}>
   {original?<div className="home-banner-original"><div><span className="eyebrow">TU MOSTRADOR DIGITAL</span><h1>Todo lo que necesitas.<br/>Listo para tu próxima obra.</h1><p>Hola, {customerName||'profesional'}. Encuentra tu material y recógelo en tienda.</p></div><div className="home-banner-note"><span>01 / BUSCA</span><span>02 / AÑADE</span><span>03 / RECOGE</span><b>Menos esperas.<br/>Más tiempo en obra.</b></div></div>:<><h1 className="home-banner-sr">Tu mostrador digital</h1><img className="home-banner-image" src={current.image_url!} alt={current.alt} onError={()=>setFailed(value=>[...value,current.id])}/></>}
  </div>
  <button type="button" className="primary home-banner-explore" onClick={onExplore}>Explorar catálogo →</button>
  {slides.length>1&&<>
   <div className="home-banner-dots" role="group" aria-label="Seleccionar imagen del banner">{slides.map((slide,position)=><button key={slide.id} type="button" className="home-banner-dot" aria-label={`Ver imagen ${position+1}: ${slide.alt}`} aria-current={position===index%slides.length?'true':undefined} onClick={()=>setIndex(position)}><span/></button>)}</div>
   <button type="button" className="home-banner-pause" aria-label={paused?'Reanudar banner':'Pausar banner'} aria-pressed={paused} onClick={()=>setPaused(value=>!value)}>{paused?'▶':'Ⅱ'}</button>
  </>}
 </section>;
}
