import type {Metadata} from 'next';
import OrderTracking from '../OrderTracking';
export const metadata:Metadata={title:'Seguimiento de pedido · Bermúdez Ulloa',robots:{index:false,follow:false},referrer:'no-referrer'};
export default function TrackingPage(){return <OrderTracking/>}
