const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];
global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
const React=require('react'),{createRoot}=require('react-dom/client'),Menu=require('../app/SettingsMenu.tsx').default;
const root=createRoot(document.getElementById('root')),calls=[];
function Screen(){const[selected,setSelected]=React.useState('pickup');return React.createElement(Menu,{selected,onSelect:id=>{calls.push(id);setSelected(id)}})}
(async()=>{
 await React.act(async()=>root.render(React.createElement(Screen)));
 const buttons=[...document.querySelectorAll('nav button')];assert.equal(buttons.length,8);assert.equal(new Set(buttons.map(b=>b.getAttribute('aria-controls'))).size,8);
 assert.deepEqual([...document.querySelectorAll('h2')].map(el=>el.textContent),['Pedidos','Catálogo','Web']);
 assert.equal(document.querySelector('[aria-current=page]').textContent,'Recogida y horarios');
 for(const button of buttons){await React.act(async()=>button.click());assert.equal(document.querySelectorAll('[aria-current=page]').length,1);assert.equal(document.querySelector('[aria-current=page]'),button);assert.equal(button.type,'button');assert.equal(button.tabIndex,0,'All menu options remain reachable by keyboard')}
 assert.equal(new Set(calls).size,8,'Every existing settings panel remains reachable');
 if(process.env.SETTINGS_PREVIEW){const css=fs.readFileSync(require('node:path').resolve(__dirname,'../app/settings.css'),'utf8');fs.writeFileSync(process.env.SETTINGS_PREVIEW,'<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font:16px system-ui;background:#f2f6f8;color:#233b49;margin:24px}h1{font-size:32px}</style><style>'+css+'</style><main class="settings-page"><h1>Parámetros</h1><p class="settings-intro">Selecciona la configuración que quieres consultar.</p>'+document.getElementById('root').innerHTML+'</main></html>')}
 await React.act(async()=>root.unmount());dom.window.close();console.log('Settings menu: all eight panels, grouped navigation, selected state and keyboard reachability passed');
})().catch(e=>{console.error(e);process.exitCode=1;dom.window.close()});
