import test from 'node:test';
import assert from 'node:assert/strict';
import {deliveryDelay,delayLabel} from '../app/deliveryDeadline.ts';
const order={attention_deadline_at:'2026-10-22T09:00:00+02:00',estado_registro_exit:'PENDIENTE'};

test('solo hay retraso después del límite, comparando el mismo instante entre zonas',()=>{
 assert.equal(deliveryDelay(order,Date.parse('2026-10-22T06:59:59Z')).seconds,0);
 assert.equal(deliveryDelay(order,Date.parse('2026-10-22T07:00:00Z')).seconds,0);
 assert.equal(deliveryDelay(order,Date.parse('2026-10-22T07:00:01Z')).seconds,1);
 assert.equal(deliveryDelay(order,Date.parse('2026-10-23T09:03:04Z')).seconds,93784);
 assert.equal(delayLabel(93784),'1 d 02 h 03 min 04 s');
});
test('el retraso queda fijado a la entrega real',()=>{
 const delivered={...order,delivered_at:'2026-10-22T09:15:00+02:00',estado_registro_exit:'ENTREGADO'};
 assert.deepEqual(deliveryDelay(delivered,Date.parse('2026-10-25T10:00:00Z')),{seconds:900,closed:true});
 assert.equal(deliveryDelay({...delivered,delivered_at:'2026-10-22T08:59:00+02:00'},Date.now()).seconds,0);
});
test('no inventa retrasos si faltan el plazo, la hora del servidor o la entrega',()=>{
 assert.equal(deliveryDelay({},Date.now()).seconds,null);
 assert.equal(deliveryDelay({...order,attention_deadline_at:'invalida'},Date.now()).seconds,null);
 assert.equal(deliveryDelay(order,null).seconds,null);
 assert.equal(deliveryDelay({...order,estado_registro_exit:'FACTURADO'},Date.now()).seconds,null);
});
