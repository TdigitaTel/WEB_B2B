const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require('typescript');
const source=path.resolve(__dirname,'../app/login-image-upload.ts');
const code=ts.transpileModule(fs.readFileSync(source,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const loaded=new Module(source,module);loaded.filename=source;loaded.paths=Module._nodeModulePaths(path.dirname(source));loaded._compile(code,source);
const {prepareLoginImage,readAppearanceResponse,validateLoginImage,LOGIN_IMAGE_UPLOAD_TARGET}=loaded.exports;
(async()=>{
 for(const [status,message] of [[413,'tamaño'],[401,'sesión'],[403,'permiso'],[502,'no está disponible'],[504,'no está disponible'],[500,'No se pudo guardar']]){
  await assert.rejects(readAppearanceResponse(new Response('<html><head>Error</head></html>',{status})),e=>e.message.includes(message)&&!e.message.includes('Unexpected token')&&!e.message.includes('<html>'));
 }
 await assert.rejects(readAppearanceResponse(new Response('<html>Unexpected proxy response</html>')),/confirmación/);
 await assert.rejects(readAppearanceResponse(new Response(JSON.stringify({detail:'Formato no admitido'}),{status:422})),/Formato no admitido/);
 assert.deepEqual(await readAppearanceResponse(new Response(JSON.stringify({image_url:'/api/v1/login-appearance/image?v=ok'}))),{image_url:'/api/v1/login-appearance/image?v=ok'});
 assert.deepEqual(await readAppearanceResponse(new Response(JSON.stringify({image_url:null}))),{image_url:null});
 assert.throws(()=>validateLoginImage(new File(['x'],'test.svg',{type:'image/svg+xml'})),/JPG/);
 assert.throws(()=>validateLoginImage(new File([new Uint8Array(8*1024*1024+1)],'big.png',{type:'image/png'})),/8 MB/);
 let scenario={width:2000,height:1800,fail:false,nullBlob:false},revoked=0,draws=0;
 const oldURL=global.URL,oldImage=global.Image,oldDocument=global.document;
 global.URL={createObjectURL:()=> 'blob:fixture',revokeObjectURL:()=>revoked++};
 global.Image=class{constructor(){this.naturalWidth=scenario.width;this.naturalHeight=scenario.height}set src(value){queueMicrotask(()=>scenario.fail?this.onerror():this.onload())}};
 global.document={createElement:()=>({width:0,height:0,getContext:()=>({drawImage:()=>draws++}),toBlob(callback,type,quality){callback(scenario.nullBlob?null:new Blob([new Uint8Array(Math.ceil(this.width*this.height*quality))],{type}))}})};
 try{
  const small=new File(['small'],'image.png',{type:'image/png'});
  assert.equal(await prepareLoginImage(small),small);
  assert.equal(draws,0);assert.equal(revoked,1);
  const large=new File([new Uint8Array(5*1024*1024)],'photo.png',{type:'image/png'});
  const result=await prepareLoginImage(large);
  assert.ok(result.size<=LOGIN_IMAGE_UPLOAD_TARGET,'se envía por debajo del límite del proxy');
  assert.equal(result.type,'image/webp');assert.ok(draws>1,'reduce resolución si bajar calidad no basta');assert.equal(revoked,2);
  scenario.width=6000;scenario.height=4000;
  await assert.rejects(prepareLoginImage(small),/20 megapíxeles/);assert.equal(revoked,3);
  scenario.width=2000;scenario.height=1800;scenario.fail=true;
  await assert.rejects(prepareLoginImage(small),/No se pudo abrir/);assert.equal(revoked,4);
  scenario.fail=false;scenario.nullBlob=true;
  await assert.rejects(prepareLoginImage(large),/no pudo preparar/);assert.equal(revoked,5);
 }finally{global.URL=oldURL;global.Image=oldImage;global.document=oldDocument}
 console.log('Imagen de acceso: respuestas HTML/JSON, errores, límites, optimización y limpieza correctos');
})().catch(error=>{console.error(error);process.exitCode=1});
