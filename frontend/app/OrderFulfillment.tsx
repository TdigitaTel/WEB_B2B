import {orderFulfillment,type FulfillmentLine} from './orderFulfillmentProgress';
import './order-fulfillment.css';
export function OrderFulfillment({items}:{items:FulfillmentLine[]}){
 const result=orderFulfillment(items);
 return <span className="order-fulfillment" role="group" aria-label="Atención de materiales">
  {result.percent===null?<small>Sin materiales activos</small>:<>
   <b>Atendido al {result.percent}%</b>
   <progress aria-label="Porcentaje de materiales atendidos" value={result.completed} max={result.total}/>
   <small>{result.completed} de {result.total} materiales atendidos · {result.pending===0?'No faltan materiales':result.pending===1?'Falta 1 material':`Faltan ${result.pending} materiales`}</small>
  </>}
 </span>
}
