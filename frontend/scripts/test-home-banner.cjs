const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Node','Event','CustomEvent'])global[key]=dom.window[key];global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{createRoot}=require('react-dom/client');
const Banner=require('../app/HomeBanner.tsx').default;
let motion=false;window.matchMedia=()=>({matches:motion,addEventListener(){},removeEventListener(){}});
let tick,requests=0,navigate=0;const timeout=global.setTimeout,clear=global.clearTimeout;
global.setTimeout=(fn,ms,...args)=>{if(ms===3000){tick=fn;return 'banner-timer'}return timeout(fn,ms,...args)};global.clearTimeout=id=>{if(id==='banner-timer')tick=undefined;else clear(id)};
const original={id:'original',alt:'Diseño original',enabled:true,image_url:null};
let stored={revision:'r1',interval_seconds:3,slides:[original,{id:'image1',alt:'Promoción',enabled:true,image_url:'/api/v1/home-banner/images/image1'},{id:'hidden',alt:'Oculta',enabled:false,image_url:'/api/v1/home-banner/images/hidden'}]};
global.fetch=async()=>{requests++;return {ok:true,status:200,json:async()=>structuredClone(stored)}};
let root=createRoot(document.getElementById('root'));
(async()=>{
 await React.act(async()=>root.render(React.createElement(Banner,{customerName:'Cliente de prueba',onExplore:()=>navigate++})));
 assert.match(document.body.textContent,/Cliente de prueba/);assert.equal(requests,1);assert.equal(typeof tick,'function');
 const cta=document.querySelector('.home-banner-explore');assert.equal(cta.parentElement,document.querySelector('.home-banner'));
 await React.act(async()=>tick());assert.equal(document.querySelector('.home-banner-image').alt,'Promoción');assert.equal(document.querySelector('.home-banner-controls span').textContent,'2 / 2');
 assert.equal(document.querySelector('.home-banner-explore'),cta,'CTA stays outside the changing slide');
 await React.act(async()=>cta.click());assert.equal(navigate,1);
 await React.act(async()=>document.querySelector('[aria-label="Pausar banner"]').click());assert.equal(tick,undefined);
 await React.act(async()=>document.querySelector('[aria-label="Imagen siguiente"]').click());assert.match(document.body.textContent,/Cliente de prueba/);
 await React.act(async()=>document.querySelector('[aria-label="Reanudar banner"]').click());assert.equal(typeof tick,'function');
 await React.act(async()=>tick());await React.act(async()=>document.querySelector('.home-banner-image').dispatchEvent(new Event('error')));assert.match(document.body.textContent,/Todo lo que necesitas/,'Broken images retain original content and CTA');
 await React.act(async()=>root.unmount());assert.equal(tick,undefined);
 motion=true;root=createRoot(document.getElementById('root'));
 await React.act(async()=>root.render(React.createElement(Banner,{configuration:stored,onExplore:()=>{}})));assert.equal(tick,undefined,'Reduced motion disables automatic advance');assert.equal(requests,1);
 await React.act(async()=>root.unmount());
 // Operator workflow: edit order and visibility, save, sequential multi-file upload, delete.
 require('../app/login-image-upload.ts').prepareLoginImage=async file=>file;
 const Settings=require('../app/HomeBannerSettings.tsx').default;
 let calls=[],uploadActive=false,uploaded=0;
 global.fetch=async(url,options={})=>{calls.push([url,options]);let response=stored;
  if(options.method==='PUT'){const body=JSON.parse(options.body);stored={...stored,...body,revision:'r2',slides:body.slides.map(slide=>({...slide,image_url:slide.id==='original'?null:'/api/v1/home-banner/images/'+slide.id}))};response=stored;}
  if(options.method==='POST'){assert.equal(uploadActive,false);uploadActive=true;assert.ok(options.body.get('file'));await Promise.resolve();uploaded++;stored={...stored,revision:'u'+uploaded,slides:[...stored.slides,{id:'new'+uploaded,alt:'Nueva',enabled:true,image_url:'/api/v1/home-banner/images/new'+uploaded}]};response=stored;uploadActive=false;}
  if(options.method==='DELETE'){assert.match(url,/revision=u2/);stored={...stored,revision:'deleted',slides:stored.slides.filter(slide=>slide.id!=='new2')};response=stored;}
  return {ok:true,status:200,json:async()=>structuredClone(response)};
 };
 root=createRoot(document.getElementById('root'));await React.act(async()=>root.render(React.createElement(Settings)));
 assert.equal(document.querySelector('input[type=file]').multiple,true);
 assert.ok([...document.querySelectorAll('.home-banner-admin-list img')].every(img=>img.src.includes('/store/home-banner/')),'Disabled images use authenticated preview');
 await React.act(async()=>document.querySelector('[aria-label="Bajar imagen 1"]').click());
 await React.act(async()=>document.querySelector('.home-banner-admin-list input[type=checkbox]').click());
 assert.equal(document.querySelector('input[type=file]').matches(':disabled'),true,'Unsaved edits cannot be lost during upload');
 await React.act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Guardar banner').click());
 const saved=JSON.parse(calls.find(([,o])=>o.method==='PUT')[1].body);assert.equal(saved.slides[0].id,'image1');assert.equal(saved.slides[0].enabled,false);
 const input=document.querySelector('input[type=file]');Object.defineProperty(input,'files',{value:[new File(['a'],'one.png',{type:'image/png'}),new File(['b'],'two.png',{type:'image/png'})],configurable:true});
 await React.act(async()=>input.dispatchEvent(new Event('change',{bubbles:true})));
 await React.act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Añadir imágenes').click());assert.equal(uploaded,2);assert.match(document.body.textContent,/2 imágenes añadidas/);
 const last=document.querySelector('.home-banner-admin-list article:last-child');await React.act(async()=>[...last.querySelectorAll('button')].find(b=>b.textContent==='Eliminar').click());assert.match(document.body.textContent,/Imagen eliminada/);
 await React.act(async()=>root.unmount());global.setTimeout=timeout;global.clearTimeout=clear;dom.window.close();console.log('Home banner: automatic/manual rotation, pause, reduced motion, fallback, persistent CTA and operator image management passed');
})().catch(error=>{console.error(error);global.setTimeout=timeout;global.clearTimeout=clear;dom.window.close();process.exitCode=1});
