export default function OrderReadyPreview({expectedAt,delivery=false,slotStart,slotEnd,fallback="Selecciona una fecha y franja disponibles"}:{expectedAt?:string|null;delivery?:boolean;slotStart?:string|null;slotEnd?:string|null;fallback?:string}){
 const instant=Date.parse(expectedAt||'');
 const date=Number.isFinite(instant)?new Date(instant).toLocaleString('es-ES',{timeZone:'Europe/Madrid',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}):fallback;
 return <p className="attention-deadline">{delivery?"Preparación probable":"Pedido listo para recoger, previsión"}: <b>{date}</b>{slotStart&&slotEnd&&<small>Franja de recogida: {slotStart} – {slotEnd}</small>}</p>
}
