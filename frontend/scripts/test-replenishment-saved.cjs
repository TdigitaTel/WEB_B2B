const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test'});
for(const key of ['window','document','HTMLElement','Event'])global[key]=dom.window[key];global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
const React=require('react'),{createRoot}=require('react-dom/client'),View=require('../app/ReplenishmentSaved.tsx').default;
let opened=null,missing=true,stale=false,rawFailure=false,calls=[],downloaded='',currentJob=null,polls=0,sequence=0;
global.URL.createObjectURL=()=> 'blob:redistribution';global.URL.revokeObjectURL=()=>{};
dom.window.HTMLAnchorElement.prototype.click=function(){downloaded=this.download};
dom.window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')};dom.window.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')};
const saved={id:'saved',delegation:'01',delegation_name:'San Diego',calculated_at:'2026-11-08T10:30:00Z',summary:{articles_analyzed:4},filters:{date_from:'2026-10-01',date_to:'2026-10-31',delegations:['01']}};
const classifications={areas:[{id:1,name:'Herramientas'}],families:[{id:2,name:'Manuales',area_id:1}],subfamilies:[{id:3,name:'Llaves',family_id:2}],types:[{id:4,name:'Llave fija',subfamily_id:3}]};
const plan={fingerprint:'a'.repeat(64),movement_total:201,page:1,page_size:100,movements:[{detail_id:'1-0',sku:'MAT',description:'Material prueba',unit_type:'UD',from_delegation:'01',to_delegation:'02',quantity:3,kind:'TRANSFER'},{detail_id:'1-1',sku:'MAT',description:'Material prueba',unit_type:'UD',from_delegation:'01',to_delegation:'00',quantity:5,kind:'RETURN_CENTRAL'}],unmet_needs:[{sku:'OTHER',delegation:'05',quantity:2,unit_type:'M'}],material_warnings:[{sku:'INVALID',reason:'Falta cálculo del material.'}],warnings:['Los periodos son diferentes.'],calculations:[{delegation:'01',name:'San Diego',captured_at:'2026-11-08T10:00:00Z',date_from:'2026-10-01',date_to:'2026-10-31'}],summary:{materials:1,transfers:1,returns_to_central:1,unmet_needs:1,excluded_materials:1}};
const response=(body,status=200)=>({ok:status<400,status,text:async()=>JSON.stringify(body)});
global.fetch=async(url,options={})=>{
 calls.push([url,options]);
 if(url.includes('/movements/'))return response({movement:plan.movements[0],fingerprint:plan.fingerprint,consumption_basis_label:'Media',reconstructed:false,detail:{version:1,origin:{delegation:'01',stock:20,incoming:0,outgoing:2,maximum_stock:10,inventory_position:18,final_quantity:0},destination:null,raw_surplus:8,initial_surplus:8,origin_before:5,origin_after:0,already_allocated:3,dispatch_step:1,quantity_before_rounding:5,sequence:2,prior_movements:[],remaining_needs:[]}});
 if(url.endsWith('/export.xlsx'))return {...response({detail:'Los cálculos han cambiado. Vuelve a calcular la redistribución.'},stale?409:200),headers:{get:()=> 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},blob:async()=>new Blob(['excel'])};
 if(url.endsWith('/calculations'))return response({items:[saved,{...saved,delegation:'02',delegation_name:'Ferrol'}],missing_delegations:missing?[{code:'04',name:'Santiago'},{code:'05',name:'Sanxenxo'}]:[]});
 if(url.endsWith('/jobs/current'))return response({job:currentJob});
 if(url.endsWith('/redistribution/jobs')&&options.method==='POST'){
  if(rawFailure)return {ok:false,status:500,text:async()=> 'Internal Server Error'};
  if(missing)return response({detail:{message:'Faltan cálculos guardados.',missing_delegations:[{code:'04',name:'Santiago'}]}},409);
  const request=JSON.parse(options.body);polls=0;
  currentJob={id:'redistribution-'+(++sequence),status:'QUEUED',phase:'Esperando turno',progress:0,total_articles:2000,processed_articles:0,total_batches:2,completed_batches:0,batch_size:1000,consumption_basis:request.consumption_basis,filters:request.filters};return response(currentJob);
 }
 if(url.includes('/result?')){const query=new URL(url,dom.window.location.href).searchParams;return response({...plan,page:Number(query.get('page')),consumption_basis:currentJob.consumption_basis});}
 if(url.includes('/redistribution/jobs/')){polls++;currentJob={...currentJob,status:polls>1?'COMPLETED':'RUNNING',phase:polls>1?'Redistribución completa':'Procesando bloque 1 de 2',progress:polls>1?100:50,processed_articles:polls>1?2000:1000,completed_batches:polls>1?2:1};return response(currentJob);}
 throw Error('Unexpected '+url);
};
let root=createRoot(document.getElementById('root'));
const render=revision=>root.render(React.createElement(View,{revision,classifications,onOpen:value=>opened=value}));
const button=text=>[...document.querySelectorAll('button')].find(b=>b.textContent===text);
const pause=ms=>React.act(async()=>new Promise(resolve=>setTimeout(resolve,ms)));
const setInput=(input,value)=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));};
const choose=(label,value)=>{const select=document.querySelector(`[aria-label="${label}"]`);select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}));};
(async()=>{
 await React.act(async()=>render('1'));
 assert.match(document.body.textContent,/04 · Santiago, 05 · Sanxenxo/);assert.match(document.body.textContent,/8\/11\/2026/);
 await React.act(async()=>button('Ver cálculo').click());assert.equal(opened.id,'saved');assert.equal(opened.delegation,'01');
 await React.act(async()=>button('Calcular redistribución').click());
 assert.match(document.querySelector('[role=alert]').textContent,/Faltan: 04 · Santiago/);
 missing=false;await React.act(async()=>button('Actualizar lista').click());
 await React.act(async()=>choose('Área para redistribuir','1'));
 await React.act(async()=>choose('Familia para redistribuir','2'));
 await React.act(async()=>choose('Subfamilia para redistribuir','3'));
 await React.act(async()=>choose('Tipo para redistribuir','4'));
 await React.act(async()=>setInput(document.querySelector('[aria-label="Material para redistribuir"]'),'MAT'));
 await React.act(async()=>button('Calcular redistribución').click());
 const request=JSON.parse(calls.filter(c=>c[0].endsWith('/redistribution/jobs')).at(-1)[1].body);
 assert.equal(request.filters.q,'MAT');assert.equal(request.filters.family_id,2);assert.equal(request.filters.type_id,4);
 assert.equal(document.querySelector('[aria-label="Avance de redistribución"]').value,50);
 assert.equal(document.querySelector('[aria-label="Familia para redistribuir"]').matches(':disabled'),true);
 await pause(2150);await pause(200);
 assert.equal(document.querySelector('[aria-label="Avance de redistribución"]').value,100);
 assert.match(document.body.textContent,/3 UD/);assert.match(document.body.textContent,/5 UD/);
 assert.match(document.body.textContent,/necesidades sin cubrir/);assert.match(document.body.textContent,/INVALID/);
 assert.match(document.body.textContent,/Página 1 de 3/);
 const detailButton=document.querySelector('.repl-plan-table button');assert.equal(detailButton.textContent,'Ver cálculo');assert.equal(detailButton.disabled,false);
 await React.act(async()=>detailButton.click());assert.ok(document.querySelector('dialog[open]'));assert.match(document.querySelector('dialog').textContent,/Cuánto puede aportar el origen/);assert.ok(calls.some(c=>c[0].endsWith('/movements/1-0')));
 await React.act(async()=>document.querySelector('[aria-label="Cerrar cálculo de redistribución"]').click());assert.ok(!document.querySelector('dialog'));
 await React.act(async()=>button('Siguiente').click());await pause(200);
 assert.ok(calls.some(c=>c[0].includes('/result?page=2')));
 await React.act(async()=>button('Exportar redistribución a Excel').click());assert.equal(downloaded,'redistribucion.xlsx');
 const exported=calls.find(c=>c[0].endsWith('/export.xlsx'));assert.ok(exported[0].includes('/jobs/'));assert.equal(JSON.parse(exported[1].body).fingerprint,plan.fingerprint);
 const completedPolls=polls;await pause(2100);assert.equal(polls,completedPolls,'Completed results do not poll');
 await React.act(async()=>button('Limpiar filtros').click());assert.equal(document.querySelector('[aria-label="Familia para redistribuir"]').value,'');assert.ok(!button('Exportar redistribución a Excel'));
 await React.act(async()=>document.querySelector('input[value=MEDIAN]').click());
 await React.act(async()=>button('Calcular redistribución').click());await pause(2150);await pause(200);
 assert.equal(JSON.parse(calls.filter(c=>c[0].endsWith('/redistribution/jobs')).at(-1)[1].body).consumption_basis,'MEDIAN');
 // Leaving and returning restores a saved job and its paginated result.
 await React.act(async()=>root.unmount());root=createRoot(document.getElementById('root'));
 await React.act(async()=>render('2'));await pause(200);assert.ok(button('Exportar redistribución a Excel'));
 stale=true;await React.act(async()=>button('Exportar redistribución a Excel').click());
 assert.match(document.querySelector('[role=alert]').textContent,/Vuelve a calcular/);assert.ok(!button('Exportar redistribución a Excel'));
 rawFailure=true;await React.act(async()=>button('Calcular redistribución').click());
 assert.match(document.querySelector('[role=alert]').textContent,/servidor no pudo completar.*500/);assert.ok(!document.body.textContent.includes('Unexpected token'));
 await React.act(async()=>root.unmount());dom.window.close();console.log('Redistribution UI: configured filters, 1,000-item progress, pagination, restored jobs, saved Excel and non-JSON failures passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
