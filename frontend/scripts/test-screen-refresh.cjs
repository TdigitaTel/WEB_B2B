const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),ts=require('typescript');
const {JSDOM}=require('jsdom');
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','MouseEvent','AbortController'])global[key]=dom.window[key];
Object.defineProperty(global,'navigator',{value:dom.window.navigator,configurable:true});
global.IS_REACT_ACT_ENVIRONMENT=true;
let hidden=false,online=true;
Object.defineProperty(document,'visibilityState',{get:()=>hidden?'hidden':'visible'});
Object.defineProperty(navigator,'onLine',{get:()=>online});
let now=Date.now();const originalNow=Date.now;Date.now=()=>now;
let sequence=0;const timers=new Map();
window.setInterval=(fn,ms)=>{const id=++sequence;timers.set(id,{fn,ms});return id};
window.clearInterval=id=>timers.delete(id);
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(module,filename)=>{let source=fs.readFileSync(filename,'utf8');if(filename.endsWith('/app/page.tsx'))source+='\nexports.__Operations=Operations;';module._compile(ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,filename)};
require.extensions['.css']=module=>{module.exports={}};
const {startPolling}=require('../app/screenPolling.ts');
const React=require('react'),{createRoot}=require('react-dom/client');
const {AutoRefreshProvider,ScreenRefreshParameters,useAutoRefresh,RefreshScope}=require('../app/AutoRefresh.tsx');
const {__Operations:Operations}=require('../app/page.tsx');
let configured=5;
global.fetch=async(url,options={})=>{
 if(url.includes('screen-refresh-settings')){
  if(options.method==='PATCH')configured=JSON.parse(options.body).interval_seconds;
  return new Response(JSON.stringify({interval_seconds:configured}));
 }
 if(url.includes('line-planning'))return new Response(JSON.stringify({lines:[]}));
 return new Response('[]');
};
const tick=ms=>{now+=ms;return [...timers.values()].filter(timer=>timer.ms===ms).forEach(timer=>timer.fn())};
const root=createRoot(document.getElementById('root'));
function clickText(text){const button=[...document.querySelectorAll('button')].find(el=>el.textContent.trim().startsWith(text));assert.ok(button,`Button ${text}`);button.click()}
function setInput(input,value){Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new window.Event('input',{bubbles:true}))}
(async()=>{
 let calls=0,release,lastSignal;
 const stop=startPolling(signal=>{calls++;lastSignal=signal;return new Promise(resolve=>release=resolve)},5);
 tick(5000);tick(5000);assert.equal(calls,1,'Slow query must not overlap');release();await Promise.resolve();
 hidden=true;tick(5000);assert.equal(calls,1);hidden=false;online=false;tick(5000);assert.equal(calls,1);online=true;
 const edit=document.createElement('input');document.body.append(edit);edit.focus();edit.dispatchEvent(new window.Event('input',{bubbles:true}));window.dispatchEvent(new window.Event('focus'));assert.equal(calls,1,'Pause while typing');edit.blur();edit.remove();
 tick(5000);assert.equal(calls,2);stop();assert.ok(lastSignal.aborted);release();await Promise.resolve();assert.equal(timers.size,0);
 const boardCalls=[];let offlineBoard=false;
 const onRefresh=async(...args)=>{boardCalls.push(args);if(offlineBoard)throw Error('Consulta temporalmente no disponible')};
 await React.act(async()=>root.render(React.createElement(AutoRefreshProvider,null,React.createElement(Operations,{orders:[],onRefresh}))));
 assert.match(document.body.textContent,/Todas las vistas se actualizan cada 5 segundos/);
 for(const [button,mode] of [['Activos Kardex','active_kardex'],['Atendidos','attended'],['Activos SGA','active_sga'],['Pedidos WEB','web']]){
  await React.act(async()=>clickText(button));boardCalls.length=0;
  await React.act(async()=>tick(5000));assert.equal(boardCalls.length,1,`${mode} automatic refresh`);assert.equal(boardCalls[0][0],mode);
 }
 // Unsaved filter changes do not silently become the submitted query.
 const state=[...document.querySelectorAll('select')].find(el=>[...el.options].some(o=>o.value==='ENTREGADO'));
 await React.act(async()=>{state.value='ENTREGADO';state.dispatchEvent(new window.Event('change',{bubbles:true}))});
 boardCalls.length=0;await React.act(async()=>tick(5000));assert.equal(boardCalls[0][3],'TODOS');
 await React.act(async()=>clickText('Consultar'));boardCalls.length=0;
 await React.act(async()=>tick(5000));assert.equal(boardCalls[0][3],'ENTREGADO');
 const order={id:'order-1',number:'WEB-2026-000001',customer:'Cliente de prueba',store:'Almeiras',created_at:'2026-10-30T08:00:00Z',origen_pedido:'B2B',estado_registro_exit:'PENDIENTE',items:[]};
 await React.act(async()=>root.render(React.createElement(AutoRefreshProvider,null,React.createElement(Operations,{orders:[order],onRefresh}))));
 const detail=document.querySelector('.operator-web-order');assert.ok(detail);
 await React.act(async()=>{detail.open=true;detail.dispatchEvent(new window.Event('toggle'))});
 offlineBoard=true;await React.act(async()=>tick(5000));assert.match(document.body.textContent,/WEB-2026-000001/,'Retain last good orders on failed refresh');assert.equal(detail.open,true);
 offlineBoard=false;await React.act(async()=>root.render(React.createElement(AutoRefreshProvider,null,React.createElement(Operations,{orders:[{...order,customer:'Cliente actualizado'}],onRefresh}))));
 assert.equal(document.querySelector('.operator-web-order').open,true,'Keep expanded order details');
 let probeCalls=0;
 function Probe(){useAutoRefresh(async()=>{probeCalls++});return null}
 await React.act(async()=>root.render(React.createElement(AutoRefreshProvider,null,React.createElement(React.Fragment,null,React.createElement(ScreenRefreshParameters),React.createElement(Probe),React.createElement(RefreshScope,{active:false},React.createElement(Probe))))));
 await React.act(async()=>tick(5000));assert.equal(probeCalls,1,'Only visible settings tab polls');
 const number=document.querySelector('input[type="number"]');
 await React.act(async()=>setInput(number,'20'));
 await React.act(async()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 assert.equal(configured,20);assert.match(document.body.textContent,/Intervalo guardado/);
 assert.ok([...timers.values()].some(timer=>timer.ms===20000),'Saved parameter changes active timers');
 const before=probeCalls;await React.act(async()=>tick(20000));assert.equal(probeCalls,before+1);
 await React.act(async()=>setInput(number,'35'));configured=30;
 await React.act(async()=>tick(5000));assert.equal(number.value,'35','Remote refresh preserves unsaved parameter edit');
 await React.act(async()=>root.unmount());assert.equal(timers.size,0,'All subscriptions removed on unmount');
 console.log('Automatic refresh: all four operator views, applied filters, configurable cadence, pause/visibility, no overlap, cancellation and draft preservation passed');dom.window.close();
})().catch(error=>{console.error(error);dom.window.close();process.exitCode=1});
