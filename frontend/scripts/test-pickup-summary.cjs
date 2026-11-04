const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];
global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{createRoot}=require('react-dom/client'),{PickupSummaryView}=require('../app/OrderPickup.tsx');
const root=createRoot(document.getElementById('root'));
const summary={state:'ENTREGADO_PARCIAL',total_materials:7,prepared_materials:2,delivered_materials:2,partial_delivered_materials:0,ready_materials:0,pending_materials:5,prepared_percent:28,delivered_percent:28,prepared_complete:false,legacy_delivery:false,requires_review:true,last_pickup_at:'2026-11-03T14:24:00Z',lines:[]};
const view=s=>React.createElement('details',null,React.createElement('summary',null,React.createElement(PickupSummaryView,{summary:s,warning:'Revisar origen'})),React.createElement('p',null,'Detalle del pedido'));
(async()=>{
 await React.act(async()=>root.render(view(summary)));
 const button=document.querySelector('button'),advanced=document.getElementById(button.getAttribute('aria-controls'));
 assert.equal(button.textContent,'Información avanzada');assert.equal(button.getAttribute('aria-expanded'),'false');assert.ok(advanced.hidden);
 const top=[...document.querySelector('.pickup-summary').children].filter(el=>el!==advanced).map(el=>el.textContent).join(' ');
 assert.match(top,/Entregado parcial/);assert.match(top,/Avance: 28%/);assert.doesNotMatch(top,/Preparados|Disponibles|Última|Faltan|Revisar/);
 const progress=document.querySelector('progress');assert.equal(progress.value,2);assert.equal(progress.max,7);
 await React.act(async()=>button.click());assert.equal(button.getAttribute('aria-expanded'),'true');assert.equal(advanced.hidden,false);assert.equal(document.querySelector('details').open,false,'Information button does not open or close the order card');
 assert.match(advanced.textContent,/Preparados completos: 2 de 7/);assert.match(advanced.textContent,/Faltan por completar: 5/);assert.match(advanced.textContent,/Última recogida/);assert.match(advanced.textContent,/Revisar origen/);
 await React.act(async()=>root.render(view({...summary,delivered_materials:3,delivered_percent:42})));
 assert.equal(document.querySelector('button').getAttribute('aria-expanded'),'true','Refresh preserves the chosen detail view');assert.match(document.querySelector('.pickup-progress-label').textContent,/42%/);
 await React.act(async()=>button.click());assert.ok(advanced.hidden);
 await React.act(async()=>root.render(view({...summary,state:'SIN_MATERIALES_ACTIVOS',total_materials:0,delivered_percent:null})));
 assert.equal(document.querySelector('progress'),null);assert.doesNotMatch(document.querySelector('.pickup-summary').textContent,/Avance: null/);
 if(process.env.SUMMARY_PREVIEW){await React.act(async()=>root.render(view(summary)));const css=fs.readFileSync(require('node:path').resolve(__dirname,'../app/order-pickup.css'),'utf8');fs.writeFileSync(process.env.SUMMARY_PREVIEW,'<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font:16px system-ui;color:#233c4a;margin:24px}.card{max-width:360px;padding:24px;border:1px solid #cad8e0;border-radius:12px}.pickup-summary{font-size:16px}.pickup-summary .pickup-state{font-size:20px}</style><style>'+css+'</style><h1>Resumen del pedido</h1><div class="card">'+document.querySelector('.pickup-summary').outerHTML+'</div></html>')}
 await React.act(async()=>root.unmount());dom.window.close();console.log('Compact pickup summary: status/progress, hidden advanced data, safe card interaction, refresh preservation and zero materials passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
