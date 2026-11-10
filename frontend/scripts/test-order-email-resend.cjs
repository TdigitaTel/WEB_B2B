const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];global.IS_REACT_ACT_ENVIRONMENT=true;
dom.window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')};
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{createRoot}=require('react-dom/client'),Component=require('../app/ResendOrderEmail.tsx').default;
const root=createRoot(document.getElementById('root'));
let state={state_key:'PENDIENTE',state_label:'Pedido recibido',can_send:false,reason:'Este estado no está configurado para enviar correos.',status:null,requires_confirmation:false,recipient_count:0},fail=false;const calls=[];
global.fetch=async(url,options={})=>{calls.push({url,options});if(String(url).endsWith('/history'))return new Response(JSON.stringify({deliveries:[],events:[],notice:'Aceptación SMTP no confirma entrega.',limit:50}));if(options.method==='POST'){if(fail)return new Response(JSON.stringify({detail:'No se ha confirmado el envío.\nFase: AUTH · Librería: SMTPAuthenticationError · Código SMTP: 535'}),{status:502});return new Response(JSON.stringify({...state,status:'SENT',can_send:false,reason:'Aviso aceptado.',message:'El servidor de correo ha aceptado el aviso.'}))}return new Response(JSON.stringify(state))};
const button=text=>{const value=[...document.querySelectorAll('button')].find(el=>el.textContent===text);assert.ok(value,text);return value};
async function click(text){await React.act(async()=>button(text).click())}
(async()=>{
 await React.act(async()=>root.render(React.createElement(Component,{orderId:'order-1',number:'6008917'})));
 assert.equal(calls.length,0,'No queries until the operator opens the action');await click('Correo y registro');
 assert.match(document.querySelector('dialog').textContent,/no está configurado/);assert.equal(button('Enviar aviso del estado actual').disabled,true);assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
 await click('Cerrar');state={...state,state_key:'EN_PREPARACION',state_label:'En preparación',can_send:true,reason:'Listo para enviar',recipient_count:2,automatic_enabled:false};await click('Correo y registro');
 assert.match(document.querySelector('dialog').textContent,/envío es manual/);await click('Enviar aviso del estado actual');
 assert.deepEqual(JSON.parse(calls.find(c=>c.options.method==='POST').options.body),{expected_state_key:'EN_PREPARACION',confirm_uncertain:false});
 assert.match(document.querySelector('[role=status]').textContent,/ha aceptado/);assert.equal(button('Enviar aviso del estado actual').disabled,true);
 await click('Cerrar');state={...state,requires_confirmation:true,status:'UNCERTAIN'};await click('Correo y registro');
 assert.equal(button('Enviar aviso del estado actual').disabled,true);await React.act(async()=>document.querySelector('dialog input[type=checkbox]').click());
 assert.equal(button('Enviar aviso del estado actual').disabled,false);fail=true;await click('Enviar aviso del estado actual');
 const last=calls.filter(c=>c.options.method==='POST').at(-1);assert.equal(JSON.parse(last.options.body).confirm_uncertain,true);
 assert.match(document.querySelector('[role=alert]').textContent,/SMTPAuthenticationError/);assert.match(document.querySelector('[role=alert]').textContent,/535/);
 assert.equal(document.querySelector('dialog input[type=checkbox]').checked,false,'A fresh confirmation is required after an unsuccessful attempt');
 await React.act(async()=>root.unmount());dom.window.close();console.log('Order mail: unconfigured-state explanation, current-state send, SMTP acceptance, uncertain retry and diagnostic errors passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
