/** One in-flight request per subscription; silent failures keep the last known data. */
export function startPolling(task:(signal:AbortSignal)=>unknown|Promise<unknown>,seconds:number,options:{pauseEditing?:boolean}={}){
  let running=false,stopped=false,editingUntil=0;
  const editing=(event:Event)=>{if(event.target instanceof HTMLElement&&event.target.matches('input,textarea,select,[contenteditable="true"]'))editingUntil=Date.now()+1500};
  const controller=new AbortController();
  const tick=async()=>{
    if(stopped||running||document.visibilityState==='hidden'||navigator.onLine===false)return;
    if(options.pauseEditing!==false&&Date.now()<editingUntil)return;
    running=true;
    try{await task(controller.signal)}catch{/* Each view retains its data; next tick retries. */}finally{running=false}
  };
  const timer=window.setInterval(()=>void tick(),seconds*1000);
  document.addEventListener('input',editing);document.addEventListener('change',editing);
  window.addEventListener('focus',tick);window.addEventListener('online',tick);document.addEventListener('visibilitychange',tick);
  return()=>{stopped=true;controller.abort();window.clearInterval(timer);document.removeEventListener('input',editing);document.removeEventListener('change',editing);window.removeEventListener('focus',tick);window.removeEventListener('online',tick);document.removeEventListener('visibilitychange',tick)};
}
