const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{createRoot}=require('react-dom/client'),Component=require('../app/ManualClassification.tsx').default;
const tree={areas:[{id:1,code:'A1',name:'Origen'},{id:2,code:'A2',name:'Destino'}],families:[{id:10,area_id:1,code:'F1',name:'Familia origen'},{id:11,area_id:2,code:'F2',name:'Familia destino'}],subfamilies:[{id:20,family_id:10,code:'S1',name:'Subfamilia origen'}],product_types:[{id:30,subfamily_id:20,code:'T1',name:'Tipo origen'}]};
const materials=['0001','0002','0003'].map(code=>({code,description:'Material '+code,classification:'Clasificación anterior'}));
const calls=[];let failed=true;
global.fetch=async(url,options={})=>{calls.push({url:String(url),options});let body,status=200;
 if(String(url).endsWith('/tree'))body=tree;
 else if(String(url).includes('/materials?')){const params=new URL(url,'https://example.test').searchParams;body={items:params.get('q')?[materials[1]]:params.get('page')==='2'?[materials[2]]:materials.slice(0,2),total:params.get('q')?1:51}}
 else if(String(url).endsWith('/subfamilies')){const data=JSON.parse(options.body);assert.equal(data.parent_id,11);tree.subfamilies.push({id:22,family_id:11,code:'S2',name:data.name});body={id:22,name:data.name,created:true}}
 else if(String(url).endsWith('/product-types')){const data=JSON.parse(options.body);assert.equal(data.parent_id,22);tree.product_types.push({id:32,subfamily_id:22,code:'T2',name:data.name});body={id:32,name:data.name,created:true}}
 else if(String(url).endsWith('/assign')){if(failed){status=409;body={detail:'La clasificación cambió. Revisa el destino.'}}else body={assigned:2,created_products:0,destination:'Destino / Familia destino / Nueva subfamilia / Nuevo tipo'}}
 else throw Error('Unexpected '+url);
 return new Response(JSON.stringify(body),{status});};
const root=createRoot(document.getElementById('root'));
const button=text=>{const value=[...document.querySelectorAll('button')].find(el=>el.textContent===text);assert.ok(value,text);return value};
async function click(text){await React.act(async()=>button(text).click())}
async function change(el,value){assert.ok(el);await React.act(async()=>{const prototype=el.tagName==='SELECT'?dom.window.HTMLSelectElement.prototype:dom.window.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(prototype,'value').set.call(el,value);el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));})}
const field=label=>document.querySelector(`[aria-label="${label}"]`);
(async()=>{
 await React.act(async()=>root.render(React.createElement(Component)));
 await click('Seleccionar esta página');assert.match(document.body.textContent,/2 seleccionados/);
 await click('Siguiente');assert.match(document.body.textContent,/Página 2 de 2/);
 await React.act(async()=>field('Seleccionar 0003').click());assert.match(document.body.textContent,/3 seleccionados/);
 await React.act(async()=>field('Quitar 0002 de la selección').click());assert.match(document.body.textContent,/2 seleccionados/);
 await change(document.querySelector('.manual-material-search input'),'válvula');await click('Buscar materiales');
 assert.match(document.body.textContent,/2 seleccionados/,'Search changes retain the explicit selection');
 assert.ok(calls.some(call=>call.url.includes('q=v%C3%A1lvula')));
 await change(field('Destino: Categoría'),'2');await change(field('Destino: Familia'),'11');
 await change(document.querySelector('.manual-create-classification input'),'Nueva subfamilia');await click('Crear clasificación');
 assert.equal(field('Destino: Subfamilia').value,'22');assert.equal(field('Destino: Tipo de producto').value,'');
 await change(document.querySelector('.manual-create-classification select'),'product-types');await change(document.querySelector('.manual-create-classification input'),'Nuevo tipo');await click('Crear clasificación');
 assert.equal(field('Destino: Tipo de producto').value,'32');
 await click('Revisar asignación (2)');assert.match(document.querySelector('[aria-label="Revisar asignación"]').textContent,/Nuevo tipo/);
 await click('Confirmar asignación');assert.match(document.querySelector('[role=alert]').textContent,/La clasificación cambió/);assert.match(document.body.textContent,/2 seleccionados/);
 failed=false;await click('Confirmar asignación');
 const assigned=calls.filter(call=>call.url.endsWith('/assign'));assert.equal(assigned.length,2);
 assert.deepEqual(JSON.parse(assigned[1].options.body),{codes:['0001','0003'],product_type_id:32});assert.match(document.body.textContent,/0 seleccionados/);assert.match(document.body.textContent,/2 materiales asignados/);
 await React.act(async()=>root.unmount());dom.window.close();console.log('Manual classification: selection across pages/search, removal, hierarchy creation, review, failed save retention and successful bulk assignment passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
