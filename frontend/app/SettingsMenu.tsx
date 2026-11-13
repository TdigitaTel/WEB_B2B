'use client';
export const settingsGroups=[
 {id:'orders',label:'Pedidos',options:[['order-display','Visualización de pedidos'],['pickup','Recogida y horarios'],['line-planning','Fechas por línea'],['series','Series de pedidos'],['email','Correo de pedidos']]},
 {id:'catalog',label:'Catálogo',options:[['search','Buscador y sinónimos'],['brands','Marcas']]},
 {id:'web',label:'Web',options:[['refresh','Actualización de pantallas'],['appearance','Imagen de acceso'],['home-banner','Banner de inicio']]},
];
export default function SettingsMenu({selected,onSelect}:{selected:string;onSelect:(id:string)=>void}){
 return <nav className="settings-menu" aria-label="Opciones de parámetros">{settingsGroups.map(group=><section className="settings-menu-group" key={group.id} aria-labelledby={`settings-group-${group.id}`}><h2 id={`settings-group-${group.id}`}>{group.label}</h2><div className="settings-menu-options">{group.options.map(([id,label])=><button type="button" key={id} id={`settings-tab-${id}`} aria-current={selected===id?'page':undefined} aria-controls={`settings-panel-${id}`} onClick={()=>onSelect(id)}>{label}</button>)}</div></section>)}</nav>
}
