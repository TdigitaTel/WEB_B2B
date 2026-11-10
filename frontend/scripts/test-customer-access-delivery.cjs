const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const {JSDOM}=require('jsdom'),dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','Event','CustomEvent'])global[key]=dom.window[key];
global.IS_REACT_ACT_ENVIRONMENT=true;
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true,target:ts.ScriptTarget.ES2020}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const React=require('react'),{createRoot}=require('react-dom/client'),Component=require('../app/CustomerAccess.tsx').default;
const clients=['00004','11264'].map((code,i)=>({erp_id:code,legal_name:'Cliente '+code,trade_name:'',email:'',enabled:true,username:code,status:i?'Activo':'Pendiente de cambiar contraseña'}));
const delivery={'00004':false,'11264':true},writes=[],warnings=[];
const originalError=console.error;console.error=(...args)=>{warnings.push(args.join(' '));};
global.fetch=async(url,options={})=>{let body;const parsed=new URL(url,'https://example.test');
 if(parsed.pathname.endsWith('/delivery')){
  const code=options.body?JSON.parse(options.body).customer_code:parsed.searchParams.get('customer_code');
  if(options.method==='POST'){const value=JSON.parse(options.body);writes.push(value);delivery[code]=value.delivery_enabled;}
  body={delivery_enabled:delivery[code]};
 }else if(parsed.pathname.endsWith('/initial'))body={credentials:null,message:''};
 else if(parsed.pathname==='/api/v1/store/customer-access')body={items:clients,next_after:null,total:2};
 else throw Error('Unexpected request '+url);
 return {ok:true,status:200,json:async()=>body};
};
const root=createRoot(document.getElementById('root'));
const aside=()=>document.querySelector('.access-detail');
function assertSingle(code){
 assert.equal([...aside().querySelectorAll('h3')].filter(el=>el.textContent==='Modalidad de entrega').length,1,'Delivery settings must not accumulate when changing customer');
 assert.equal([...aside().querySelectorAll('button')].filter(el=>el.textContent==='Guardar modalidad').length,1);
 assert.equal(aside().querySelector('input[type=checkbox]').checked,delivery[code]);
 assert.equal([...aside().querySelectorAll('h3')].filter(el=>el.textContent==='Acceso con QR').length,1);
}
(async()=>{try{
 await React.act(async()=>root.render(React.createElement(Component)));
 await React.act(async()=>document.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 for(const code of ['00004','11264','00004','11264','00004']){
  await React.act(async()=>document.querySelector(`[aria-label="Seleccionar ${code}"]`).click());
  assertSingle(code);
 }
 await React.act(async()=>aside().querySelector('input[type=checkbox]').click());
 await React.act(async()=>[...aside().querySelectorAll('button')].find(el=>el.textContent==='Guardar modalidad').click());
 assert.deepEqual(writes,[{customer_code:'00004',delivery_enabled:true}]);assertSingle('00004');
 assert.ok(!warnings.some(text=>/same key|unique.*key/i.test(text)),warnings.join('\n'));
 console.log('Customer delivery: single settings block, customer switching, independent values and correct save passed');
 }finally{await React.act(async()=>root.unmount());console.error=originalError;dom.window.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
