const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];global.IS_REACT_ACT_ENVIRONMENT=true;
dom.window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')};
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};

const React=require('react'),{createRoot}=require('react-dom/client'),Component=require('../app/OrderEmailHistory.tsx').default;
const root=createRoot(document.getElementById('root'));
let fail=false,calls=[];
const body={limit:50,notice:'La aceptación SMTP no confirma entrega en bandeja de entrada.',deliveries:[{id:42,revision:2,state_label:'Pendiente',status:'SENT',status_label:'Aceptado por SMTP',attempts:2,created_at:'2026-11-10T10:00:00Z',updated_at:'2026-11-10T10:03:00Z',next_attempt_at:null,completed_slots:['email1'],diagnostic:null}],events:[{id:7,created_at:'2026-11-10T10:02:00Z',state_label:'Pendiente',status:'RETRY',status_label:'Error · reintento pendiente',mode:'AUTOMATIC',revision:2,attempt:1,reason:'Error de autenticación',completed_slots:[],diagnostic:{phase:'AUTH',exception:'SMTPAuthenticationError',smtp_code:535,response:'Credenciales rechazadas',reference:'ref-42'}}]};
global.fetch=async(url,options={})=>{calls.push({url,options});return new Response(JSON.stringify(fail?{detail:'Registro no disponible'}:body),{status:fail?503:200})};
(async()=>{
 await React.act(async()=>root.render(React.createElement(Component,{endpoint:'/api/v1/store/orders/order-1/email',refreshKey:''})));
 assert.match(document.body.textContent,/Aceptado por SMTP/);
 assert.match(document.body.textContent,/Destinos aceptados: Email1/);
 assert.match(document.body.textContent,/SMTPAuthenticationError/);
 assert.match(document.body.textContent,/535/);
 assert.match(document.body.textContent,/Credenciales rechazadas/);
 assert.match(document.body.textContent,/no confirma entrega/);
 assert.ok(calls.every(call=>!call.options.method||call.options.method==='GET'));
 fail=true;await React.act(async()=>[...document.querySelectorAll('button')].find(button=>button.textContent==='Actualizar registro').click());
 assert.match(document.querySelector('[role=alert]').textContent,/Registro no disponible/);
 assert.match(document.body.textContent,/Aceptado por SMTP/,'Keep the known history when refresh fails');
 await React.act(async()=>root.unmount());dom.window.close();console.log('Order email history: acceptance, retained failure, provider response, destination slots and read-only refresh passed');
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
