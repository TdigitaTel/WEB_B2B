const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{createRoot}=require('react-dom/client'),View=require('../app/Replenishment.tsx').default;
let listLoads=0,queries=[];
const saved={id:'saved',delegation:'02',delegation_name:'Ferrol',captured_at:'2026-11-09T08:00:00Z',calculated_at:'2026-11-09T08:00:00Z',temporary_parameters:{},summary:{articles_analyzed:1},filters:{date_from:'2026-10-01',date_to:'2026-10-31',delegations:['02'],skus:[]}};
global.fetch=async(url)=>{let data;
 if(url.endsWith('/options'))data={article_limit:1000,maximum_article_limit:10000,server_date:'2026-11-09',delegations:[{code:'02',name:'Ferrol'}],areas:[],families:[],subfamilies:[],types:[]};
 else if(url.endsWith('/jobs/current'))data={job:null,latest_result:null};
 else if(url.endsWith('/calculations')){listLoads++;data={items:[saved],missing_delegations:[]}}
 else if(url.includes('/results?')){queries.push(url);data={items:[],summary:{},total:0}}
 else throw Error('Unexpected '+url);
 return {ok:true,status:200,json:async()=>data,text:async()=>JSON.stringify(data)};
};
const root=createRoot(document.getElementById('root'));
const panel=id=>document.getElementById('repl-panel-'+id),tab=id=>document.getElementById('repl-tab-'+id);
(async()=>{
 await React.act(async()=>root.render(React.createElement(View)));
 assert.equal(tab('calculation').getAttribute('aria-selected'),'true');assert.equal(panel('redistribution').hidden,true);assert.equal(listLoads,0);
 const field=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith('Días hasta la próxima reposición')).querySelector('input');
 await React.act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(field,'11');field.dispatchEvent(new Event('input',{bubbles:true}));});
 await React.act(async()=>tab('redistribution').click());
 assert.equal(panel('calculation').hidden,true);assert.equal(panel('redistribution').hidden,false);assert.equal(listLoads,1);
 assert.ok(panel('redistribution').textContent.includes('Cálculos guardados por delegación'));
 await React.act(async()=>tab('calculation').click());assert.equal(field.value,'11');
 await React.act(async()=>tab('calculation').dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true})));
 assert.equal(tab('redistribution').getAttribute('aria-selected'),'true');assert.equal(document.activeElement,tab('redistribution'));assert.equal(listLoads,1);
 await React.act(async()=>[...panel('redistribution').querySelectorAll('button')].find(b=>b.textContent==='Ver cálculo').click());
 assert.equal(panel('calculation').hidden,false);assert.equal(panel('redistribution').hidden,true);
 await React.act(async()=>new Promise(resolve=>setTimeout(resolve,220)));
 assert.ok(queries.some(url=>url.includes('delegation=02')),'Saved calculation loads only its delegation');
 await React.act(async()=>root.unmount());dom.window.close();console.log('Replenishment tabs: lazy saved list, preserved form, keyboard navigation and delegation detail passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
