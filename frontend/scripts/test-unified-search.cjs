const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom');
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/',pretendToBeVisual:true});
for(const name of ['window','document','HTMLElement','Event','MouseEvent'])global[name]=dom.window[name];
global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.tsx','.ts'])require.extensions[ext]=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,filename);
require.extensions['.css']=module=>module.exports={};
const React=require('react'),{createRoot}=require('react-dom/client');
const Search=require('../app/SearchParameters.tsx').default;
const paths=[{id:1,area:'Fontanería',category_family:'Racorería',subfamily:'Latón'}];
let rows=[{key:'accesorio',name:'ACCESORIO',paths,synonyms:['complemento'],is_general:true,version:'1',needs_review:false},{key:'machon',name:'MACHÓN',paths,synonyms:['niple'],is_general:false,version:'1',needs_review:false}];
let settings={enabled:true,accessory_terms:['piezas','componentes'],piece_names:['codo'],materials:['inox','inoxidable','laton'],material_groups:[{name:'Inoxidable',synonyms:['inox']},{name:'Latón',synonyms:[]}]};
const calls=[];
global.fetch=async(url,options={})=>{
 calls.push([String(url),options]);let data;
 if(String(url).includes('/preview?'))data={selected_types:[{name:'MACHÓN'}],ignored:['accesorio'],term_groups:[['laton'],['1/2']],ambiguous:false};
 else if(String(url).endsWith('/group')){const body=JSON.parse(options.body);data={...rows.find(row=>row.name===body.type_name),...body,version:'2'};rows=rows.map(row=>row.key===data.key?data:row)}
 else if(String(url).includes('search-settings')){if(options.method==='PATCH')settings=JSON.parse(options.body);data=settings}
 else data=rows;
 return new Response(JSON.stringify(data));
};
const root=createRoot(document.getElementById('root'));
const click=text=>{const button=[...document.querySelectorAll('button')].find(el=>el.textContent.trim()===text);assert.ok(button,text);button.click()};
const tab=text=>[...document.querySelectorAll('[role="tab"]')].find(el=>el.textContent===text).click();
const input=(element,value)=>{Object.getOwnPropertyDescriptor(element.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype,'value').set.call(element,value);element.dispatchEvent(new window.Event('input',{bubbles:true}))};
(async()=>{
 await React.act(async()=>root.render(React.createElement(Search)));
 assert.equal(document.querySelectorAll('tbody tr').length,2);
 assert.match(document.body.textContent,/General/);assert.match(document.body.textContent,/Específico/);
 const edit=[...document.querySelectorAll('tr')].find(row=>row.textContent.includes('ACCESORIO')).querySelectorAll('button');
 await React.act(async()=>[...edit].find(button=>button.textContent==='Editar').click());
 const checkbox=[...document.querySelectorAll('input[type="checkbox"]')].find(el=>el.closest('label').textContent.includes('Es un tipo general'));
 assert.ok(checkbox.checked);await React.act(async()=>checkbox.click());
 await React.act(async()=>click('Guardar sinónimos'));
 const saved=JSON.parse(calls.find(([url])=>url.endsWith('/group'))[1].body);assert.equal(saved.is_general,false);assert.deepEqual(saved.synonyms,['complemento']);
 await React.act(async()=>tab('Palabras generales'));
 let words=document.querySelector('textarea');await React.act(async()=>input(words,'piezas, componentes, artículos'));
 await React.act(async()=>tab('Materiales'));assert.ok(document.body.textContent.includes('Inoxidable'));
 await React.act(async()=>tab('Palabras generales'));assert.equal(document.querySelector('textarea').value,'piezas, componentes, artículos','Keep pending rules when switching tabs');
 await React.act(async()=>click('Guardar reglas del buscador'));assert.deepEqual(settings.accessory_terms,['piezas','componentes','artículos']);assert.equal(settings.material_groups[0].name,'Inoxidable');
 await React.act(async()=>tab('Probar búsqueda'));
 await React.act(async()=>click('accesorio niple de latón 1/2'));
 const request=calls.find(([url])=>url.includes('/preview?'));assert.equal(new URL(request[0],'http://localhost').searchParams.get('q'),'accesorio niple de latón 1/2');
 const panel=document.querySelector('.search-plan');assert.match(panel.textContent,/MACHÓN/);assert.match(panel.textContent,/accesorio/);assert.match(panel.textContent,/laton y 1\/2/);
 await React.act(async()=>root.unmount());dom.window.close();console.log('Unified search UI: type flag, preserved aliases, rules tabs, material groups and search tester passed');
})().catch(error=>{console.error(error);dom.window.close();process.exitCode=1});
