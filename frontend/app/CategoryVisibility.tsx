"use client";
import {useEffect,useState} from "react";
type Category={id:number;code:string;name:string;visible:boolean;image_url:string|null};
async function responseData(response:Response){
 if(response.status===401)window.dispatchEvent(new Event("session-expired"));
 const data=await response.json();
 if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"No se pudo guardar el cambio");
 return data;
}
export default function CategoryVisibility(){
 const [rows,setRows]=useState<Category[]>([]),[query,setQuery]=useState(""),[error,setError]=useState(""),[message,setMessage]=useState(""),[busy,setBusy]=useState<number|null>(null),[loading,setLoading]=useState(true);
 useEffect(()=>{fetch("/api/v1/store/category-visibility",{credentials:"include"}).then(responseData).then(setRows).catch(e=>setError(e.message)).finally(()=>setLoading(false))},[]);
 async function update(row:Category){setBusy(row.id);setError("");setMessage("");try{await responseData(await fetch(`/api/v1/store/category-visibility/${row.id}`,{method:"PATCH",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({visible:!row.visible})}));setRows(old=>old.map(item=>item.id===row.id?{...item,visible:!row.visible}:item))}catch(e){setError((e as Error).message)}finally{setBusy(null)}}
 async function upload(row:Category,file:File){
  setError("");setMessage("");
  if(file.size>10*1024*1024){setError("La imagen supera 10 MB");return;}
  setBusy(row.id);
  try{const form=new FormData();form.append("file",file);const result=await responseData(await fetch(`/api/v1/store/category-visibility/${row.id}/image`,{method:"POST",credentials:"include",body:form}));setRows(old=>old.map(item=>item.id===row.id?{...item,image_url:result.image_url}:item));setMessage(`Imagen guardada para ${row.name}`)}catch(e){setError((e as Error).message)}finally{setBusy(null)}
 }
 return <section className="page"><h1>Categorías e imágenes</h1><p>Selecciona qué categorías aparecen en el catálogo y carga una imagen para cada una. Las imágenes no cambian la visibilidad ni la clasificación.</p><p className="small">PNG, JPG o WebP · Máximo 10 MB · Hasta 4096 × 4096 píxeles.</p><input className="input" aria-label="Filtrar categorías" placeholder="Buscar por código o categoría" value={query} onChange={e=>setQuery(e.target.value)}/>{error&&<p className="error" role="alert">{error}</p>}{message&&<p className="category-image-success" role="status">{message}</p>}{loading?<p>Cargando categorías…</p>:<div className="visibility-table"><table><thead><tr><th>Código</th><th>Categoría</th><th>Imagen</th><th>Visible</th></tr></thead><tbody>{rows.filter(row=>`${row.code} ${row.name}`.toLowerCase().includes(query.toLowerCase())).map(row=><tr key={row.id}><td>{row.code}</td><td>{row.name}</td><td><div className="category-image-control">{row.image_url?<img className="category-image-preview" src={row.image_url} alt={`Imagen de ${row.name}`}/>:<span className="category-image-empty">Sin imagen</span>}<label className={`category-image-upload secondary ${busy!==null?"disabled":""}`}>{busy===row.id?"Guardando…":row.image_url?"Cambiar imagen":"Subir imagen"}<input type="file" accept="image/png,image/jpeg,image/webp" aria-label={`Subir imagen para ${row.name}`} disabled={busy!==null} onChange={e=>{const file=e.target.files?.[0];if(file)void upload(row,file);e.target.value=""}}/></label></div></td><td><label><input type="checkbox" checked={row.visible} disabled={busy!==null} onChange={()=>update(row)} aria-label={`Mostrar ${row.name}`}/>{row.visible?"Visible":"Oculta"}</label></td></tr>)}</tbody></table></div>}</section>
}
