const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];
Object.defineProperty(global,'navigator',{value:dom.window.navigator,configurable:true});
global.IntersectionObserver=class{observe(){}disconnect(){}};
global.IS_REACT_ACT_ENVIRONMENT=true;
const timers=new Map();let sequence=0;window.setInterval=(fn,ms)=>{timers.set(++sequence,{fn,ms});return sequence};window.clearInterval=id=>timers.delete(id);
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const filename=path.resolve(__dirname,'../app/page.tsx'),m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8')+'\nexport {Operations};',{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,filename);
const React=require('react'),{createRoot}=require('react-dom/client'),{Operations}=m.exports,Parameters=require('../app/OrderDisplayParameters.tsx').default;
const order={id:'order1',number:'WEB-EXAMPLE',customer:'Cliente',store:'Almeiras',created_at:'2026-11-05T08:00:00Z',origen_pedido:'B2B',estado_registro_exit:'REGISTRADO',items:[{sku:'23568',description:'Soporte',quantity:2,unit:'UD',unit_price:8,line_total:16,created_in_web:true,fulfillment_zone:'KARDEX'},{sku:'24266',description:'Colector',quantity:1,unit:'UD',unit_price:10,line_total:10,created_in_web:null,fulfillment_zone:'KARDEX'}]};
global.fetch=async url=>new Response(JSON.stringify(String(url).includes('/delegations')?[]:String(url).includes('/order-calendar')?{orders:[]}:String(url).endsWith('/visual')?{family:'Accesorios'}:{lines:[],version:0}));
let fail=false;const saved=[];
function Screen(){const[images,setImages]=React.useState(false);return React.createElement(React.Fragment,null,React.createElement(Parameters,{value:images,onSave:async value=>{saved.push(value);if(fail)throw Error('No se pudo guardar');setImages(value)}}),React.createElement(Operations,{orders:[order],onRefresh:async()=>{},showImages:images}))}
const root=createRoot(document.getElementById('root'));
const toggle=()=>document.querySelector('.order-display-parameters input');
async function save(){await React.act(async()=>document.querySelector('.order-display-parameters button').click())}
async function view(name){await React.act(async()=>[...document.querySelectorAll('nav[aria-label="Tipo de pedidos"] button')].find(b=>b.textContent.startsWith(name)).click())}
(async()=>{
 await React.act(async()=>root.render(React.createElement(Screen)));
 assert.ok(document.querySelector('.calendar-week-grid'),'Calendar is the default WEB view');
 await React.act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Listado').click());
 const detail=document.querySelector('.operator-web-order');detail.open=true;
 assert.equal(document.querySelector('.ops-image-toggle'),null,'Microphotos are configured in Parameters');assert.equal(document.querySelector('.ops-heading'),null,'No large title banner');assert.equal(document.querySelectorAll('.ops-page .ops-refresh').length,1);assert.equal(toggle().checked,false);assert.equal(detail.querySelectorAll('img').length,0);
 await React.act(async()=>toggle().click());await save();assert.deepEqual(saved,[true]);assert.equal(toggle().checked,true);
 assert.equal(detail.open,true);assert.equal(detail.querySelectorAll('img').length,2);
 for(const image of detail.querySelectorAll('img')){assert.equal(image.getAttribute('loading'),'lazy');assert.match(image.src,/\/products\/by-sku\//)}
 assert.doesNotMatch(detail.textContent,/Sin confirmar/);assert.match(detail.textContent,/Tienda/);
 await React.act(async()=>detail.querySelector('img').dispatchEvent(new Event('error',{bubbles:true})));
 assert.ok(detail.querySelector('.thumbnail-placeholder'));assert.match(detail.textContent,/Accesorios/);
 for(const name of ['Activos Kardex','Atendidos','Activos SGA']){await view(name);assert.equal(document.querySelector('.ops-image-toggle'),null);assert.equal(document.querySelectorAll('.dispatch-line img').length,0,'Photos are restricted to WEB orders')}
 await view('Pedidos WEB');assert.equal(toggle().checked,true,'Changing view retains saved preference');
 fail=true;await React.act(async()=>toggle().click());await save();assert.equal(document.querySelectorAll('.operator-web-order img').length,2,'A failed save does not change the active preference');assert.match(document.querySelector('[role=alert]').textContent,/No se pudo guardar/);
 fail=false;await save();assert.equal(toggle().checked,false);assert.equal(document.querySelectorAll('.operator-web-order img').length,0);
 await React.act(async()=>root.unmount());dom.window.close();console.log('Operator WEB order images: parameter-only control, compact header, scope, save errors, retained preference and image fallback passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
