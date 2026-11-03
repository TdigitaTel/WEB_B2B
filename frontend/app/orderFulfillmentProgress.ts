export type FulfillmentLine={quantity:number;served_quantity?:number|null;pending_quantity?:number|null;exit_removed_at?:string|null;removed_in_exit?:boolean;exit_line_status?:string};
export function orderFulfillment(lines:FulfillmentLine[]){
 const active=lines.filter(line=>!line.exit_removed_at&&!line.removed_in_exit&&line.exit_line_status!=='ELIMINADA_EN_EXIT'&&Number.isFinite(line.quantity)&&line.quantity>0);
 const completed=active.filter(line=>{
  const served=line.served_quantity??(line.pending_quantity==null?0:Math.max(0,line.quantity-line.pending_quantity));
  return Number.isFinite(served)&&served>=line.quantity;
 }).length;
 const total=active.length,pending=total-completed;
 return {total,completed,pending,percent:total?Math.floor(completed*100/total):null};
}
