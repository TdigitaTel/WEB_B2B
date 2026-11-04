const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];
global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
const React=require('react'),{createRoot}=require('react-dom/client'),Preview=require('../app/OrderEmailPreview.tsx').default;
const calls=[];let failure=false;
global.fetch=async(url,options)=>{calls.push({url,options});return new Response(JSON.stringify(failure?{detail:'Vista no disponible'}:{subject:'Pedido · '+new URL('https://example.test'+url).searchParams.get('state'),html:'<html><body>Ejemplo</body></html>',text:'Versión de texto'}),{status:failure?502:200})};
const root=createRoot(document.getElementById('root'));
function Screen(){const[state,setState]=React.useState('ENTREGADO_PARCIAL');return React.createElement(Preview,{state,onStateChange:setState,states:{ENTREGADO_PARCIAL:'Entregado parcial',ENTREGADO_TOTAL:'Entregado total'}})}
(async()=>{
 await React.act(async()=>root.render(React.createElement(Screen)));assert.equal(calls.length,0,'No preview requests until opened');
 await React.act(async()=>document.querySelector('button').click());assert.equal(calls.length,1);assert.ok(calls[0].url.endsWith('ENTREGADO_PARCIAL'));
 const frame=document.querySelector('iframe');assert.equal(frame.getAttribute('sandbox'),'');assert.equal(frame.getAttribute('referrerpolicy'),'no-referrer');assert.match(frame.getAttribute('srcdoc'),/Ejemplo/);
 await React.act(async()=>{const select=document.querySelector('select');select.value='ENTREGADO_TOTAL';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))});assert.match(document.body.textContent,/Pedido · ENTREGADO_TOTAL/);
 failure=true;await React.act(async()=>{const select=document.querySelector('select');select.value='ENTREGADO_PARCIAL';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))});assert.match(document.querySelector('[role=alert]').textContent,/Vista no disponible/);assert.equal(document.querySelector('iframe'),null,'Never display a stale state as the current preview');
 assert.ok(calls.every(c=>c.options.credentials==='include'&&!c.options.method),'Previews are read-only authenticated requests');
 await React.act(async()=>root.unmount());dom.window.close();console.log('Email preview: on-demand loading, state selection, isolated HTML, errors and read-only requests passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
