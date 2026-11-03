const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const {LinePlanningInfo}=require('../app/LinePlanningInfo.tsx');
const removed=renderToStaticMarkup(React.createElement(LinePlanningInfo,{sku:'A',lineKey:'1',removed:true,part:'note'}));
assert.match(removed,/Eliminada en EXIT/);
assert.match(removed,/Se conserva el pedido original/);
assert.doesNotMatch(removed,/Pendiente de planificación|En stock/);
const active=renderToStaticMarkup(React.createElement(LinePlanningInfo,{sku:'A',lineKey:'2',part:'note'}));
assert.match(active,/Pendiente de planificación/);
assert.doesNotMatch(active,/Eliminada en EXIT/);
console.log('Removed EXIT lines: explicit retained-history notice and active-line behavior passed');

// Render the actual customer and operator lists, without exporting test-only API.
require.extensions['.css']=m=>m.exports={};
const path=require('node:path'),Module=require('node:module');
const filename=path.resolve(__dirname,'../app/page.tsx');
const pageModule=new Module(filename,module);pageModule.filename=filename;pageModule.paths=Module._nodeModulePaths(path.dirname(filename));
pageModule._compile(ts.transpileModule(fs.readFileSync(filename,'utf8')+'\nexport {Orders,OperatorWebOrders};',{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,filename);
const original={line_key:'101',sku:'01067',description:'CURVA 90° CU M-H 5001A D.22',quantity:2,unit:'UD',unit_price:5,line_total:10,served_quantity:0,pending_quantity:2,fulfillment_zone:'OTROS',exit_removed_at:'2026-11-02T10:00:00Z'};
const order={id:'example',number:'6008552',order_number:'WEB-2026-0000321',web_number:'WEB-2026-0000321',exit_number:'6008552',nro_pedido_exit:'6008552',origen_pedido:'B2B',is_web_order:true,local_order:true,customer:'Cliente de ejemplo',customer_code:'PRUEBA',store:'Bermúdez Ulloa Almeiras',created_at:'2026-11-02T10:00:00Z',estado_registro_exit:'REGISTRADO',items:[original,{...original,line_key:'102',sku:'23493',description:'VASO EXPANSIÓN ACS 12L',exit_removed_at:null}],total:24.2,history:[],delivery_notes:[]};
const customer=renderToStaticMarkup(React.createElement(pageModule.exports.Orders,{orders:[order],refreshing:false,onRefresh:async()=>{},onRepeat:()=>{},onSubmitDraft:()=>{},onDelete:()=>{}}));
const operator=renderToStaticMarkup(React.createElement(pageModule.exports.OperatorWebOrders,{orders:[order],onDelivered:async()=>{}}));
for(const markup of [customer,operator]){assert.match(markup,/CURVA 90/);assert.match(markup,/VASO EXPANSIÓN/);assert.match(markup,/Eliminada en EXIT/);assert.match(markup,/Se conserva el pedido original/);}
console.log('Actual customer and operator order rows retain both articles and display the removed-line notice');
if(process.env.LINE_PREVIEW_DIR){
 fs.mkdirSync(process.env.LINE_PREVIEW_DIR,{recursive:true});
 const css=['globals.css','settings.css'].map(file=>fs.readFileSync(path.resolve(__dirname,'../app',file),'utf8')).join('\n');
 fs.writeFileSync(path.join(process.env.LINE_PREVIEW_DIR,'index.html'),'<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>'+css+'</style><body><p style="padding:16px">Vista de comprobación con datos simulados</p><h2>Cliente</h2>'+customer+'<h2>Operador</h2>'+operator+'</body></html>');
}
