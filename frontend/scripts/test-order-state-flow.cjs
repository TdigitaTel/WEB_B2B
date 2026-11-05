const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server'),{JSDOM}=require('jsdom'),Flow=require('../app/OrderStateFlow.tsx').default;
const summary={state:'ENTREGADO_PARCIAL',total_materials:7,delivered_materials:2,legacy_delivery:false,last_pickup_at:'2026-11-03T14:24:00Z',completed_at:null};
const workflow=[{etapa:'PENDIENTE',completed_at:'2026-11-01T10:00:00Z'},{etapa:'EN_PROCESAMIENTO',completed_at:'2026-11-02T10:00:00Z'},{etapa:'PENDIENTE_RECOJO',completed_at:'2026-11-03T10:00:00Z'},{etapa:'ENTREGADO',completed_at:'2026-11-03T12:00:00Z'},{etapa:'FACTURADO',completed_at:'2026-11-04T00:00:00Z',date_only:true}];
function render(props={}){return new JSDOM(renderToStaticMarkup(React.createElement(Flow,{state:'FACTURADO',workflow,summary,...props}))).window.document}
for(const state of ['PENDIENTE_RECOGIDA_PARCIAL','PENDIENTE_RECOGIDA_TOTAL','ENTREGADO_PARCIAL','ENTREGADO_TOTAL']){
 const doc=render({summary:{...summary,state}}),nodes=doc.querySelectorAll('li');assert.equal(nodes.length,5,'Partial/total are never extra stages');
 assert.deepEqual([...nodes].map(n=>n.querySelector('b').textContent),['Pendiente','En procesamiento','Pendiente de recogida','Entregado','Facturado']);
 const active=doc.querySelector('[aria-current=step]');assert.equal(active.querySelector('b').textContent,state.startsWith('ENTREGADO')?'Entregado':'Pendiente de recogida');
 assert.equal(active.querySelector('.state-flow-substate').textContent,state.endsWith('PARCIAL')?'Parcial':'Total');
}
const doc=render();assert.equal(doc.querySelector('.state-flow-current').textContent,'Entregado parcial');assert.match(doc.querySelector('[aria-current=step] time').textContent,/15:24/);
assert.match(doc.querySelector('p').textContent,/facturación no confirma la entrega total/);
const invoice=doc.querySelector('li:last-child time');assert.doesNotMatch(invoice.textContent,/:/,'Date-only invoice has no invented time');
const legacy=render({summary:{...summary,state:'REVISAR_ENTREGA_HISTORICA',legacy_delivery:true}});assert.equal(legacy.querySelectorAll('li')[3].querySelector('time'),null,'No false physical date from old delivered flag');
const empty=render({workflow:[{etapa:'PENDIENTE',completed_at:'invalid'}],summary:null,registeredAt:null,deliveredAt:null,state:'PENDIENTE'});assert.equal(empty.querySelectorAll('time').length,0);assert.match(empty.body.textContent,/Sin fecha registrada/);
assert.equal(render({state:'ELIMINADO_EN_EXIT'}).querySelector('.state-flow-current').textContent,'No se va a atender');
const total=render({summary:{...summary,state:'ENTREGADO_TOTAL',delivered_materials:7,completed_at:'2026-11-05T14:30:00Z'}});assert.ok(total.querySelector('.state-flow-current.is-complete'));assert.match(total.querySelector('[aria-current=step] time').textContent,/15:30/);
console.log('Order flow: five parent stages, partial/total substates, real dates, invoice date-only, highlighted current status and no false legacy delivery passed');
