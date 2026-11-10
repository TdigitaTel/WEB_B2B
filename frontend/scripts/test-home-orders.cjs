const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require('typescript');
const {JSDOM}=require('jsdom');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const dom=new JSDOM('<div id="root"></div>',{url:'https://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement'])global[key]=dom.window[key];
global.IS_REACT_ACT_ENVIRONMENT=true;
let tick;
window.setInterval=(fn,ms)=>{assert.equal(ms,5000);tick=fn;return 1;};
window.clearInterval=()=>{};
const React=require('react');
const {createRoot}=require('react-dom/client');
const filename=path.resolve(__dirname,'../app/HomeOrders.tsx');
const loaded=new Module(filename,module);loaded.filename=filename;loaded.paths=Module._nodeModulePaths(path.dirname(filename));
const originalRequire=loaded.require.bind(loaded);loaded.require=name=>name==='./AutoRefresh'?{useRefreshSeconds:()=>5}:originalRequire(name);
loaded._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,filename);
const HomeOrders=loaded.exports.default;
const root=createRoot(document.getElementById('root'));
let calls=0,resolve,reject,signal;
const load=s=>{calls++;signal=s;return new Promise((a,b)=>{resolve=a;reject=b;});};
const text=()=>document.body.textContent;
(async()=>{
 await React.act(async()=>root.render(React.createElement(HomeOrders,{load,onNavigate:()=>{}})));
 assert.match(text(),/Consultando pedidos/);assert.doesNotMatch(text(),/No tienes/);assert.equal(calls,1);
 await React.act(async()=>{window.dispatchEvent(new window.Event('focus'));tick();});assert.equal(calls,1,'No overlapping requests');
 await React.act(async()=>{resolve([{id:'1',number:'WEB-1',origen_pedido:'B2B',store:'Almeiras',estado_registro_exit:'PENDIENTE'}]);});
 assert.match(text(),/WEB-1/);assert.doesNotMatch(text(),/Consultando/);
 await React.act(async()=>{void tick();});assert.equal(calls,2);assert.match(text(),/WEB-1/,'Keep known orders during refresh');
 await React.act(async()=>{reject(new Error('Offline'));});assert.match(text(),/No se pudieron/);assert.match(text(),/WEB-1/);assert.doesNotMatch(text(),/No tienes/);
 await React.act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Reintentar').click());
 await React.act(async()=>{resolve([{id:'2',number:'WEB-NULL',origen_pedido:'B2B',store:'Almeiras',estado_registro_exit:null}]);});assert.match(text(),/WEB-NULL/);assert.match(text(),/Pendiente/);
 await React.act(async()=>{void tick();});await React.act(async()=>{resolve([]);});assert.match(text(),/Todavía no tienes pedidos WEB/);
 await React.act(async()=>{void tick();});await React.act(async()=>{resolve([{id:'3',number:'WEB-FACTURADO-PARCIAL',origen_pedido:'B2B',store:'Almeiras',estado_registro_exit:'FACTURADO',pickup_summary:{state:'ENTREGADO_PARCIAL',total_materials:2,prepared_materials:1,delivered_materials:1,partial_delivered_materials:0,ready_materials:0,pending_materials:1,prepared_percent:50,delivered_percent:50,prepared_complete:false,legacy_delivery:false,requires_review:false,lines:[]}}]);});assert.match(text(),/WEB-FACTURADO-PARCIAL/);assert.match(text(),/Entregado parcial/,'Invoiced orders with pending material remain visible');
 await React.act(async()=>{void tick();});await React.act(async()=>{resolve([
  {id:'removed',number:'WEB-2026-9999998',web_number:'WEB-2026-9999998',origen_pedido:'B2B',store:'Almeiras',estado_registro_exit:'ELIMINADO_EN_EXIT'},
  ...[1,7,3,5,2,6,4].map(n=>({id:'web-'+n,number:'2026/AL/'+(100-n),web_number:'WEB-2026-'+String(n).padStart(7,'0'),origen_pedido:'B2B',store:'Almeiras',estado_registro_exit:n===7?'FACTURADO':'ENTREGADO'})),
  {id:'store',number:'2026/AL/99999999',origen_pedido:'EXIT',is_web_order:true,web_number:'WEB-2026-9999999',store:'Almeiras',estado_registro_exit:'PENDIENTE'},
  {id:'unknown',number:'WEB-UNKNOWN',store:'Almeiras',estado_registro_exit:'PENDIENTE'}
 ]);});
 assert.deepEqual([...document.querySelectorAll('.compact-order>b')].map(el=>el.textContent),[7,6,5,4,3].map(n=>'WEB-2026-'+String(n).padStart(7,'0')),'Only five canonical WEB orders, descending by WEB number, including invoiced and delivered');
 assert.equal(document.querySelector('.count').textContent,'5');assert.doesNotMatch(text(),/99999999|WEB-UNKNOWN|WEB-2026-9999999|WEB-2026-9999998/);
 assert.match(text(),/Facturado/);
 await React.act(async()=>{void tick();});const pending=resolve;await React.act(async()=>root.unmount());assert.equal(signal.aborted,true);await React.act(async()=>pending([]));
 console.log('Home orders: loading, independent result, refresh, no overlap, retry, cleanup passed');dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1;});
