const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server'),{JSDOM}=require('jsdom');
const {default:Analysis,orderedConsumption}=require('../app/ConsumptionAnalysis.tsx');
const quantities=[...Array(66).fill(18),...Array(46).fill(20),38,...Array(17).fill(118),114,-2,...Array(191).fill(0)];
const days=quantities.map((demand,i)=>({day:new Date(Date.UTC(2026,0,1+i)).toISOString().slice(0,10),demand}));
const outliers=days.filter(d=>d.demand>94).map(d=>({...d,times_normal:d.demand/18}));
const analysis={status:'POSSIBLE_SPOT',normal_daily_median:18,upper_threshold:94,outliers,flagged_quantity:2120,flagged_share_percent:2120/4266*100,daily_mean:4264/323,daily_mean_without_peaks:2144/323,mean_uplift_percent:2120/2144*100};
const props={analysis,positiveDays:131,observedDays:323,unit:'PZ',days};
const render=value=>new JSDOM(renderToStaticMarkup(React.createElement(Analysis,value)));
const ordered=orderedConsumption(days);
assert.equal(ordered.positive.length,131);assert.equal(ordered.total,4266);
assert.equal(ordered.positive[65].demand,18);assert.equal(ordered.pareto[17].count,18);
assert.equal(ordered.pareto[17].share,2120/4266*100);assert.equal(ordered.pareto.at(-1).share,100);
assert.ok(ordered.pareto.every((d,i)=>i===0||d.share>=ordered.pareto[i-1].share));
let dom=render(props),doc=dom.window.document;
assert.equal(doc.querySelectorAll('.repl-stat-step').length,4);
assert.deepEqual([...doc.querySelectorAll('.repl-stat-number')].map(n=>n.textContent),['1','2','3','4']);
assert.equal(doc.querySelectorAll('svg').length,3);assert.equal(doc.querySelectorAll('.repl-stat-day').length,323);
assert.equal(doc.querySelectorAll('.repl-stat-day[fill="#b96812"]').length,18);
assert.equal(doc.querySelectorAll('.repl-stat-day[fill="#b83d47"]').length,1);
assert.equal(doc.querySelectorAll('.repl-stat-ranked-day').length,131);
assert.match(doc.querySelectorAll('svg')[1].getAttribute('aria-label'),/mediana.*18 PZ/);
assert.match(doc.querySelectorAll('svg')[2].textContent,/49,7 % en 18 días/);
assert.match(doc.body.textContent,/18 es un número de días, no una cantidad de PZ/);
assert.match(doc.body.textContent,/192 días tuvieron neto cero o negativo/);
assert.match(doc.body.textContent,/No se ha eliminado ninguna venta del cálculo real/);
assert.doesNotMatch(doc.body.innerHTML,/NaN|Infinity/);
// A fixture-based preview uses the same component, not a separate hand-drawn mockup.
if(process.env.CONSUMPTION_PREVIEW){fs.writeFileSync('/private/tmp/consumption-story.html','<!doctype html><meta charset="utf-8"><style>body{font-family:Arial;background:#f1f5f7;margin:20px}*{box-sizing:border-box}'+fs.readFileSync('app/replenishment.css','utf8')+'</style>'+doc.body.innerHTML)}
dom.window.close();
for(const values of [[],[0,0],[-2,0],[30],[5,15]]){
 const data=values.map((demand,i)=>({day:`2026-01-0${i+1}`,demand})),positive=data.filter(d=>d.demand>0);
 const a=positive.length===1?{status:'SINGLE_CONSUMPTION',normal_daily_median:positive[0].demand,outliers:[]}:undefined;
 dom=render({days:data,analysis:a,positiveDays:positive.length,observedDays:data.length,unit:'UD'});
 assert.doesNotMatch(dom.window.document.body.innerHTML,/NaN|Infinity/);
 if(values.length===2&&values[0]===5)assert.match(dom.window.document.body.textContent,/Mediana: 10 UD/);
 dom.window.close();
}
dom=render({...props,days:[]});assert.equal(dom.window.document.querySelectorAll('svg').length,0);
assert.match(dom.window.document.body.textContent,/No hay una serie diaria completa/);dom.window.close();
console.log('Statistical story: chronological returns, ordered-day median, Pareto concentration, four vertical steps and sparse/legacy cases passed');
