const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{createRoot}=require('react-dom/client'),View=require('../app/Procurement.tsx').default;
let posted,polls=0,requests=[],exportCount=0;
const proposal={daily_reference:10,safety_stock:0,target_stock:950,quantity:845,quantity_with_multiple:852,coverage_now:10.5,status:'BUY',statistic_available:true};
const row={sku:'03283',description:'Material de prueba',brand_name:'BOSCH',brand_code:'42',unit_type:'UD',stock:100,central_stock:20,incoming:10,outgoing:5,inventory_position:105,monthly_mean:300,daily_std:0,coverage_days:90,lead_days:5,protection_days:95,exit_multiple:12,proposal,variants:{MEAN:proposal,MEDIAN:proposal,MODE:proposal},notes:['Comprobar la llegada de entradas pendientes.'],captured_at:'2026-11-18T10:00:00Z',observed_days:365,positive_days:100};
function job(status,progress){return {id:'purchase-1',status,progress,phase:'Calculando compra',request:posted,processed_articles:progress===100?1001:1000,total_articles:1001,completed_batches:progress===100?2:1,total_batches:2,summary:{MEAN:{buy:1001,review:0,covered:0}}}}
global.URL.createObjectURL=()=> 'blob:purchase';global.URL.revokeObjectURL=()=>{};dom.window.HTMLAnchorElement.prototype.click=function(){};
global.fetch=async(url,options={})=>{requests.push(url);let data;
 if(url.endsWith('/jobs/current'))data={job:null,latest_result:null};
 else if(url.endsWith('/jobs')&&options.method==='POST'){posted=JSON.parse(options.body);data=job('RUNNING',99)}
 else if(url.includes('/export.xlsx')){exportCount++;return {ok:true,status:200,headers:{get:()=> 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},blob:async()=>new Blob(['excel'])}}
 else if(url.includes('/results?'))data={items:[row],total:101,brands:[{code:'42',name:'BOSCH'}]};
 else if(url.endsWith('/jobs/purchase-1')){polls++;data=job('COMPLETED',100)}
 else throw Error('Unexpected '+url);
 return {ok:true,status:200,text:async()=>JSON.stringify(data)};
};
const root=createRoot(document.getElementById('root'));
const wait=ms=>React.act(async()=>new Promise(resolve=>setTimeout(resolve,ms)));
const label=text=>[...document.querySelectorAll('label')].find(n=>n.textContent.startsWith(text));
async function input(node,value){await React.act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new Event('input',{bubbles:true}))})}
(async()=>{
 await React.act(async()=>root.render(React.createElement(View,{classifications:{areas:[],families:[],subfamilies:[],types:[]},serverDate:'2026-11-18'})));
 assert.equal(label('Ventas desde').querySelector('input').value,'2025-11-18');assert.equal(label('Ventas desde').querySelector('input').disabled,true);
 const period=label('Periodo de ventas').querySelector('select');await React.act(async()=>{period.value='CUSTOM';period.dispatchEvent(new Event('change',{bubbles:true}))});assert.equal(label('Ventas desde').querySelector('input').disabled,false);
 await React.act(async()=>{period.value='90';period.dispatchEvent(new Event('change',{bubbles:true}))});assert.equal(label('Ventas desde').querySelector('input').disabled,true);assert.equal(label('Ventas desde').querySelector('input').value,'2026-08-21');
 await input(label('Materiales').querySelector('input'),'03283, 91463E');await input(label('Marca').querySelector('input'),'BOSCH');
 await React.act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Calcular compra').click());
 assert.deepEqual(posted.filters.delegations,['00','01','02','04','05']);assert.deepEqual(posted.filters.skus,['03283','91463E']);assert.equal(posted.filters.brand,'BOSCH');
 assert.equal(document.querySelector('progress').value,99);
 await wait(1300);await wait(230);
 assert.equal(document.querySelector('progress').value,100);assert.match(document.querySelector('.repl-purchase-results').textContent,/845.*852/);
 const before=polls;await wait(2200);assert.equal(polls,before,'Completed calculation must stop polling');
 await React.act(async()=>{const node=label('Marca del resultado').querySelector('select');node.value='42';node.dispatchEvent(new Event('change',{bubbles:true}))});await wait(220);
 assert.ok(requests.some(url=>url.includes('/results?')&&url.includes('brand=42')));
 await React.act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Siguiente').click());await wait(220);assert.ok(requests.some(url=>url.includes('page=2')));
 await React.act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Ver').click());assert.match(document.querySelector('[aria-label="Detalle de compra"]').textContent,/Comprobar la llegada/);
 await React.act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Excel filtrado').click());assert.equal(exportCount,1);assert.ok(requests.find(url=>url.includes('/export.xlsx')).includes('brand=42'));
 await React.act(async()=>root.unmount());dom.window.close();console.log('Procurement: dates, network request, CSV codes, progress, no completed polling, filters, pagination, detail and Excel passed');
})().catch(error=>{console.error(error);process.exitCode=1;dom.window.close()});
