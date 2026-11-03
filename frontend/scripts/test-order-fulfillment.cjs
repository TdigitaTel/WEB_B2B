const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,f);
require.extensions['.css']=m=>m.exports={};
const {orderFulfillment}=require('../app/orderFulfillmentProgress.ts');
const done={quantity:2,served_quantity:2},partial={quantity:10,served_quantity:8};
const lines=[done,done,done,done,partial,{...done,exit_removed_at:'2026-11-03T10:00:00Z'},{quantity:4,served_quantity:0,exit_removed_at:'2026-11-03T10:00:00Z'}];
assert.deepEqual(orderFulfillment(lines),{total:5,completed:4,pending:1,percent:80});
assert.deepEqual(orderFulfillment([{quantity:1000,served_quantity:1000},{quantity:1,pending_quantity:1}]),{total:2,completed:1,pending:1,percent:50},'Do not mix quantities from different materials');
assert.equal(orderFulfillment([{quantity:2,pending_quantity:0}]).percent,100);
assert.equal(orderFulfillment([{quantity:2}]).percent,0,'Unknown served quantity is not complete');
assert.equal(orderFulfillment([{quantity:2,served_quantity:0,pending_quantity:0}]).percent,0,'Explicit served quantity takes precedence');
for(const removed of [{exit_removed_at:'date'},{removed_in_exit:true},{exit_line_status:'ELIMINADA_EN_EXIT'}])assert.deepEqual(orderFulfillment([{...done,...removed}]),{total:0,completed:0,pending:0,percent:null});
assert.equal(orderFulfillment([]).percent,null);
assert.equal(orderFulfillment([...Array(999).fill(done),partial]).percent,99,'Cannot round incomplete order up to 100%');
assert.equal(orderFulfillment([{...done,exit_removed_at:null}]).percent,100,'Restored line participates again');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server'),{OrderFulfillment}=require('../app/OrderFulfillment.tsx');
const markup=renderToStaticMarkup(React.createElement(OrderFulfillment,{items:lines}));assert.match(markup,/Atendido al 80%/);assert.match(markup,/Falta 1 material/);assert.match(markup,/<progress[^>]+value="4"[^>]+max="5"/);
assert.match(renderToStaticMarkup(React.createElement(OrderFulfillment,{items:[]})),/Sin materiales activos/);
// Verify actual customer/operator headings remain truthful even when EXIT says ATENDIDO.
const path=require('node:path'),Module=require('node:module'),filename=path.resolve(__dirname,'../app/page.tsx');
const page=new Module(filename,module);page.filename=filename;page.paths=Module._nodeModulePaths(path.dirname(filename));
page._compile(ts.transpileModule(fs.readFileSync(filename,'utf8')+'\nexport {Orders,OperatorWebOrders};',{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,filename);
const order={id:'example',number:'WEB-TEST',origen_pedido:'B2B',estado_registro_exit:'ATENDIDO',created_at:'2026-11-03T10:00:00Z',items:lines.map((line,index)=>({...line,sku:'TEST-'+index,description:'Material '+index,unit:'UD',unit_price:1,line_total:2})),total:10};
for(const [Component,props] of [[page.exports.Orders,{onRefresh:async()=>{},onRepeat:()=>{},onDelete:()=>{},onSubmitDraft:()=>{},refreshing:false}],[page.exports.OperatorWebOrders,{onDelivered:async()=>{}}]]){
 const rendered=renderToStaticMarkup(React.createElement(Component,{orders:[order],...props}));assert.match(rendered,/Atendido al 80%/);assert.match(rendered,/Falta 1 material/);
}
console.log('Order fulfilment: partial attention, deleted/restored lines, different units, empty orders, truthful percentages and both actual lists passed');
