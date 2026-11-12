const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];
Object.defineProperty(global,'navigator',{value:dom.window.navigator,configurable:true});global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
let sequence=0;const intervals=new Map();window.setInterval=(fn,ms)=>{const id=++sequence;intervals.set(id,{fn,ms});return id};window.clearInterval=id=>intervals.delete(id);
const React=require('react'),{createRoot}=require('react-dom/client'),View=require('../app/Replenishment.tsx').default;
const calculation={id:'saved',consumption_bases:['MEAN','MEDIAN','MODE'],filters:{date_from:'2026-04-01',date_to:'2026-04-30',delegations:['01','02','04','05'],skus:[]},temporary_parameters:{consumption_basis:'MEAN',multiple_mode:'NONE',target_mode:'POINT'},captured_at:'2026-04-30T10:00:00Z'};
let mode='idle',calls=[],reads=0;
const job=status=>({id:'job',status,filters:calculation.filters,temporary_parameters:calculation.temporary_parameters,phase:'Procesando',error:status==='FAILED'?'Prueba de fallo':null,progress:status==='COMPLETED'?100:50,total_articles:2,processed_articles:1,total_batches:2,completed_batches:1,result:status==='COMPLETED'?calculation:null});
global.fetch=async url=>{calls.push(url);let data;
 if(url.endsWith('/options'))data={article_limit:1000,maximum_article_limit:10000,server_date:'2026-04-30',delegations:[],areas:[],families:[],subfamilies:[],types:[]};
 else if(url.endsWith('/jobs/current'))data={job:mode==='idle'?null:job('RUNNING'),latest_result:mode==='idle'?calculation:null};
 else if(url.endsWith('/jobs/job'))data=job(++reads===1?'RUNNING':mode==='failed'?'FAILED':'COMPLETED');
 else if(url.includes('/results?'))data={items:[],total:0,summary:{articles_analyzed:2}};
 else throw Error('Unexpected '+url);
 return {ok:true,status:200,text:async()=>JSON.stringify(data)};
};
const root=createRoot(document.getElementById('root')),pause=()=>React.act(async()=>new Promise(resolve=>setTimeout(resolve,230)));
async function idleEvents(){await React.act(async()=>{for(let i=0;i<3;i++)for(const timer of [...intervals.values()])timer.fn();window.dispatchEvent(new Event('focus'));window.dispatchEvent(new Event('online'));document.dispatchEvent(new Event('visibilitychange'));});await pause();}
(async()=>{
 await React.act(async()=>root.render(React.createElement(View,{key:mode})));await pause();
 assert.equal(calls.filter(url=>url.endsWith('/jobs/current')).length,1);assert.equal(intervals.size,0,'Saved calculations do not subscribe to live refresh');
 let count=calls.length;await idleEvents();assert.equal(calls.length,count,'Idle/focus/online must not replace saved results');
 for(const scenario of ['completed','failed']){
  mode=scenario;reads=0;calls=[];
  await React.act(async()=>root.render(React.createElement(View,{key:mode})));
  assert.equal(reads,1);assert.equal(intervals.size,1,'Active calculation polls only its progress');
  await React.act(async()=>{for(const timer of [...intervals.values()])timer.fn()});await pause();
  assert.equal(reads,2);assert.equal(intervals.size,0,'Progress polling stops after '+scenario);
  assert.equal(calls.filter(url=>url.endsWith('/jobs/current')).length,1);
  if(scenario==='completed')assert.equal(calls.filter(url=>url.includes('/results?')).length,1);
  else assert.match(document.querySelector('[role=alert]').textContent,/Prueba de fallo/);
  count=calls.length;await idleEvents();assert.equal(calls.length,count,'No background requests after '+scenario);
 }
 await React.act(async()=>root.unmount());dom.window.close();console.log('Replenishment snapshot: one initial load, progress only while running, stable results after completion/failure and focus passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
