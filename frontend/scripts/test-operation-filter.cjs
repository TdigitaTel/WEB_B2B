const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];
global.IS_REACT_ACT_ENVIRONMENT=true;window.setInterval=()=>1;window.clearInterval=()=>{};
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{createRoot}=require('react-dom/client');
const {operationGroup}=require('../app/OrderOperationFilter.tsx'),{default:Calendar,calendarDate}=require('../app/OrderDailyCalendar.tsx');
const today=calendarDate(new Date()),orders=[
 {id:'pending',estado_registro_exit:'PENDIENTE'},
 {id:'registered',estado_registro_exit:'REGISTRADO'},
 {id:'processing',estado_registro_exit:'EN_PREPARACION'},
 {id:'partial-prepared',estado_registro_exit:'ATENDIDO',pickup_summary:{prepared_complete:false,state:'PENDIENTE_RECOGIDA_PARCIAL'}},
 {id:'prepared',estado_registro_exit:'ATENDIDO',pickup_summary:{prepared_complete:true,state:'PENDIENTE_RECOGIDA_TOTAL'}},
 {id:'delivered',estado_registro_exit:'ENTREGADO'},
 {id:'partial-delivered',estado_registro_exit:'ATENDIDO',pickup_summary:{prepared_complete:false,state:'ENTREGADO_PARCIAL'}},
 {id:'invoiced',estado_registro_exit:'FACTURADO',pickup_summary:{prepared_complete:false,state:'PENDIENTE_RECOGIDA_PARCIAL'}}
].map(row=>({...row,number:row.id,calendar_date:today,attention_deadline_at:today+'T10:00:00Z',customer:'Cliente de prueba'}));
for(const row of orders)assert.equal(operationGroup(row),['pending','registered','processing','partial-prepared'].includes(row.id)?'POR_ATENDER':'ATENDIDO',row.id);
for(const state of ['BORRADOR','BLOQUEADO','EN_PROCESO','EN_PROCESAMIENTO'])assert.equal(operationGroup({estado_registro_exit:state}),'POR_ATENDER');
for(const state of ['ATENDIDO','PREPARADO','PENDIENTE_RECOGIDA_TOTAL','ENTREGADO_TOTAL','FACTURADO'])assert.equal(operationGroup({estado_registro_exit:state}),'ATENDIDO');
let opened=null,requests=0;
global.fetch=async()=>{requests++;return new Response(JSON.stringify({orders}))};
const root=createRoot(document.getElementById('root'));
(async()=>{
 await React.act(async()=>root.render(React.createElement(Calendar,{delegation:'TODAS',onOpenOrder:order=>opened=order})));
 const select=document.querySelector('[aria-label="Estado de la operación"]');assert.ok(select);
 assert.deepEqual([...select.options].map(option=>option.textContent),['Por atender','Atendido']);assert.equal(select.value,'POR_ATENDER');
 const visible=()=>[...document.querySelectorAll('.calendar-event b')].map(el=>el.textContent).sort();
 assert.deepEqual(visible(),['partial-prepared','pending','processing','registered']);
 await React.act(async()=>{select.value='ATENDIDO';select.dispatchEvent(new Event('change',{bubbles:true}))});
 assert.deepEqual(visible(),['delivered','invoiced','partial-delivered','prepared']);assert.equal(requests,1,'Changing the operation filter is immediate and does not reuse a different API state');
 await React.act(async()=>document.querySelector('.calendar-event').click());assert.ok(['delivered','invoiced','partial-delivered','prepared'].includes(opened.id));
 await React.act(async()=>root.unmount());dom.window.close();console.log('Operation filter: exactly two choices, pending preparation, prepared/delivered/invoiced groups and detail navigation passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
