const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];
global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{createRoot}=require('react-dom/client');
const Slots=require('../app/PickupTimeSlots.tsx').default,{calendarGroups}=require('../app/OrderDailyCalendar.tsx');
const slots=[{start:'08:00',end:'09:00',ready_at:'2026-11-07T09:00:00+01:00'},{start:'09:00',end:'10:00',ready_at:'2026-11-07T09:00:00+01:00'}];
let requestUrl='',chosen=null,ready=null;
global.fetch=async url=>{requestUrl=url;return{ok:true,json:async()=>({pickup_slots:url.includes('2026-11-08')?[]:slots})}};
const root=createRoot(document.getElementById('root'));
function App({day}){const [value,setValue]=React.useState(null);return React.createElement(Slots,{company:0,delegation:'00',day,value,onChange:slot=>{chosen=slot;setValue(slot)},onReady:value=>{ready=value}})}
(async()=>{
 await React.act(async()=>root.render(React.createElement(App,{day:'2026-11-07'})));
 assert.match(requestUrl,/scheduled_date=2026-11-07/);assert.equal(chosen.start,'08:00');assert.equal(ready,slots[0].ready_at);
 await React.act(async()=>{const select=document.querySelector('select');select.value='09:00-10:00';select.dispatchEvent(new Event('change',{bubbles:true}));});
 assert.equal(chosen.start,'09:00');assert.equal(document.querySelector('select').value,'09:00-10:00');
 await React.act(async()=>root.render(React.createElement(App,{day:'2026-11-08'})));
 assert.equal(chosen,null);assert.equal(ready,null);assert.equal(document.querySelector('select').disabled,true);assert.match(document.body.textContent,/Sin franjas disponibles/);
 const groups=calendarGroups([{id:'old',pickup_date:'2026-11-07'}, {id:'later',pickup_date:'2026-11-07',pickup_slot_start:'10:00',pickup_slot_end:'11:00'}, {id:'early',pickup_date:'2026-11-07',pickup_slot_start:'08:00',pickup_slot_end:'09:00'}, {id:'immediate',attention_deadline_at:'2026-11-07T08:15:00Z'}]);
 assert.deepEqual(groups.map(g=>g.orders[0].id),['early','immediate','later','old']);assert.equal(groups[1].label,'09:00 – 10:00 · Inmediatos');
 await React.act(async()=>root.unmount());dom.window.close();console.log('Pickup slots: weekday request, selection, preview, closed day, calendar ordering and Madrid timezone passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
