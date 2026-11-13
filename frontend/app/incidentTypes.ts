export type Target={user_id:number;email:string};
export type Step={name:string;kind:'WORK'|'APPROVE'|'EXECUTE'|'CONFIRM';scope:'GENERAL'|'DELEGATION'|'ORIGIN'|'DESTINATION';general:Target|null;delegations:Record<string,Target>;substitute:Target|null;hours:number;files:'INHERIT'|'FORBIDDEN'|'OPTIONAL'|'REQUIRED';require_document:boolean};
export const activityLabels:Record<Step['kind'],string>={WORK:'Registrar',EXECUTE:'Ejecutar',APPROVE:'Autorizar',CONFIRM:'Cerrar'};
export const activityDescriptions:Record<Step['kind'],string>={WORK:'Registra información, comprobaciones y actuaciones para continuar el proceso.',EXECUTE:'Registra la ejecución de la actuación e indica su documento de referencia.',APPROVE:'Deja constancia de la aprobación necesaria para continuar el proceso.',CONFIRM:'El solicitante confirma la resolución y cierra la incidencia. Es la última actividad del flujo.'};
export type Flow={code:string;name:string;kind:string;active:boolean;notify:boolean;file_mode:'FORBIDDEN'|'OPTIONAL'|'REQUIRED';max_files:number;max_file_mb:number;extensions:string[];reasons:string[];steps:Step[]};
export type SavedFlow={revision:number;configuration:Flow};
export type Person={id:number;name:string;email:string};
export type Options={user_id:number;permissions:Record<string,boolean>;types:SavedFlow[];users:Person[];delegations:{id:string;name:string}[];destinations:{id:string;name:string}[]};
export type Line={sku:string;description:string;unit:string;expected:number|null;actual:number|null;counted:number|null;system_stock:number|null;manual_stock:boolean;manual_reason:string;location:string;counted_at?:string|null;delta?:number;stock_source?:string;stock_captured_at?:string};
export type Incident={id:string;number:string;type_code:string;type_name:string;kind:string;delegation_id:string;delegation_name:string;destination_id:string|null;document:string;description:string;reason:string;priority:string;needed_on:string|null;creator_id:number;creator_name:string;assignee_id:number|null;assignee_name:string|null;status:string;stage_index:number;stage:string;stage_kind:string|null;version:number;created_at:string;updated_at:string;entered_at:string|null;due_at:string|null;resolution_document:string};
export type Detail=Incident&{workflow:Flow;lines:Line[];file_mode:string;files:{id:string;filename:string;size:number;created_at:string}[];events:{id:number;action:string;actor:string;created_at:string;detail:Record<string,unknown>}[];emails:{id:number;stage:string;status:string;attempts:number;diagnostic:{response?:string}|null;updated_at:string}[];can_submit:boolean;can_work:boolean;can_attach:boolean;can_reassign:boolean;can_comment:boolean};
export const incidentBase='/api/v1/store/incidents';
export async function incidentApi<T>(path:string,options:RequestInit={}):Promise<T>{
 const response=await fetch(incidentBase+path,{credentials:'include',cache:'no-store',...options,headers:{...(!(options.body instanceof FormData)?{'Content-Type':'application/json'}:{}),...options.headers}});
 const body=await response.json().catch(()=>null);
 if(response.status===401)window.dispatchEvent(new Event('session-expired'));
 if(!response.ok){const issues=Array.isArray(body?.detail)?body.detail.map((issue:{msg?:string})=>(issue.msg||'').replace(/^Value error, /,'')).filter(Boolean).slice(0,3).join('; '):'';throw Error(typeof body?.detail==='string'?body.detail:issues|| (response.status===413?'El servidor rechazó el archivo por tamaño. Reduce su tamaño y vuelve a intentarlo.':'No se pudo completar la operación. Revisa los datos y vuelve a intentarlo.'))}
 if(body===null)throw Error('El servidor no devolvió una respuesta válida. Actualiza para comprobar el resultado.');
 return body;
}
export const statusLabels:Record<string,string>={DRAFT:'Borrador',OPEN:'En atención',CLOSED:'Cerrada',REJECTED:'Rechazada'};
export const mailLabels:Record<string,string>={PENDING:'En cola',SENDING:'Enviando',SENT:'Aceptado por SMTP',RETRY:'Error · reintento pendiente',FAILED:'Error de envío',UNCERTAIN:'Envío sin confirmar · revisar',NOT_CONFIGURED:'Correo no configurado',SUPERSEDED:'Aviso sustituido',DISABLED:'Avisos desactivados'};
export const formatIncidentDate=(value:string|null)=>value?new Date(value).toLocaleString('es-ES',{timeZone:'Europe/Madrid'}):'—';
