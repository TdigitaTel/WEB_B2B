export const LOGIN_IMAGE_LIMIT = 8 * 1024 * 1024;
// Leave room for multipart headers below a 1 MB reverse-proxy limit.
export const LOGIN_IMAGE_UPLOAD_TARGET = 800 * 1024;
const MAX_PIXELS = 20_000_000;
const MAX_DIMENSION = 2400;
export type Appearance = {image_url:string|null};

export function validateLoginImage(file:File){
 if(file.size>LOGIN_IMAGE_LIMIT)throw new Error("La imagen debe ocupar como máximo 8 MB");
 if(!["image/jpeg","image/png","image/webp"].includes(file.type)&&!(file.type===""&&/\.(jpe?g|png|webp)$/i.test(file.name)))
  throw new Error("Selecciona una imagen JPG, PNG o WebP");
}

export async function prepareLoginImage(file:File):Promise<File>{
 validateLoginImage(file);
 const url=URL.createObjectURL(file);
 try{
  const picture=await new Promise<HTMLImageElement>((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error("No se pudo abrir la imagen. Selecciona un JPG, PNG o WebP válido"));image.src=url});
  if(!picture.naturalWidth||!picture.naturalHeight||picture.naturalWidth*picture.naturalHeight>MAX_PIXELS)
   throw new Error("Selecciona una imagen de hasta 20 megapíxeles");
  if(file.size<=LOGIN_IMAGE_UPLOAD_TARGET&&Math.max(picture.naturalWidth,picture.naturalHeight)<=MAX_DIMENSION)return file;
  const canvas=document.createElement("canvas");
  let scale=Math.min(1,MAX_DIMENSION/Math.max(picture.naturalWidth,picture.naturalHeight));
  for(let attempt=0;attempt<5;attempt++){
   canvas.width=Math.max(1,Math.round(picture.naturalWidth*scale));canvas.height=Math.max(1,Math.round(picture.naturalHeight*scale));
   const context=canvas.getContext("2d");if(!context)throw new Error("El navegador no pudo preparar la imagen");
   context.drawImage(picture,0,0,canvas.width,canvas.height);
   for(const quality of [0.88,0.78,0.68]){
    const blob=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve,"image/webp",quality));
    if(!blob)throw new Error("El navegador no pudo preparar la imagen");
    if(blob.size<=LOGIN_IMAGE_UPLOAD_TARGET){
     const extension=blob.type==="image/webp"?"webp":blob.type==="image/png"?"png":"jpg";
     return new File([blob],`imagen-acceso.${extension}`,{type:blob.type});
    }
   }
   scale*=0.75;
  }
  throw new Error("No se pudo reducir la imagen para la subida. Selecciona una imagen más pequeña");
 }finally{URL.revokeObjectURL(url)}
}

export async function readAppearanceResponse(response:Response):Promise<Appearance>{
 const data=await response.json().catch(()=>null);
 if(!response.ok){
  if(response.status===413)throw new Error("El servidor ha rechazado la imagen por tamaño. Prueba con una imagen más pequeña");
  if(response.status===401)throw new Error("La sesión ha caducado. Inicia sesión de nuevo");
  if(response.status===403)throw new Error("No tienes permiso para cambiar la imagen de acceso");
  if(typeof data?.detail==="string")throw new Error(data.detail);
  if([502,503,504].includes(response.status))throw new Error("El servicio de imágenes no está disponible. Inténtalo de nuevo en unos momentos");
  throw new Error("No se pudo guardar la imagen de acceso. Inténtalo de nuevo");
 }
 if(!data||!(data.image_url===null||typeof data.image_url==="string"))
  throw new Error("El servidor no devolvió la confirmación de la imagen. Actualiza la página para comprobar si se guardó");
 return data;
}
