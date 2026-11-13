'use client';
import {useEffect,useState} from 'react';
import Replenishment from './Replenishment';
import Incidents from './Incidents';
import {RefreshScope} from './AutoRefresh';
export default function ReplenishmentWorkspace({permissions}:{permissions?:Record<string,boolean>}){
 const calculation=permissions?.replenishment!==false,incidents=Object.entries(permissions||{}).some(([key,value])=>key.startsWith('incident_')&&value);
 const [tab,setTab]=useState<string|null>(null),[visited,setVisited]=useState<string[]>([]);
 function selectTab(value:string){setTab(value);setVisited(current=>current.includes(value)?current:[...current,value])}
 useEffect(()=>{selectTab(incidents&&(!calculation||window.location.hash.startsWith('#incident='))?'incidents':'calculation');const hash=()=>{if(incidents&&window.location.hash.startsWith('#incident='))selectTab('incidents')};window.addEventListener('hashchange',hash);return()=>window.removeEventListener('hashchange',hash)},[incidents,calculation]);
 return <><nav className="page incident-workspace-tabs" aria-label="Reposiciones e incidencias">{calculation&&<button aria-pressed={tab==='calculation'} className={tab==='calculation'?'primary':'secondary'} onClick={()=>selectTab('calculation')}>Reposición y redistribución</button>}{incidents&&<button aria-pressed={tab==='incidents'} className={tab==='incidents'?'primary':'secondary'} onClick={()=>selectTab('incidents')}>Incidencias</button>}</nav>{visited.includes('calculation')&&calculation&&<div hidden={tab!=='calculation'}><RefreshScope active={tab==='calculation'}><Replenishment/></RefreshScope></div>}{visited.includes('incidents')&&incidents&&<div hidden={tab!=='incidents'}><RefreshScope active={tab==='incidents'}><Incidents/></RefreshScope></div>}</>;
}
