type Prices={price_with_tax:number|null;price_without_tax:number|null;highlight_price_without_tax?:boolean};
export const highlightedPrice=(product:Prices)=>product.highlight_price_without_tax?product.price_without_tax:product.price_with_tax;
const money=(value:number|null)=>value===null?"—":new Intl.NumberFormat("es-ES",{style:"currency",currency:"EUR"}).format(value);
export default function CatalogPrice({withTax,withoutTax,highlightWithoutTax=false}:{withTax:number|null;withoutTax:number|null;highlightWithoutTax?:boolean}){
 return <div className="price-block"><span>Precio {highlightWithoutTax?"sin IVA":"con IVA"}</span><div className="price">{money(highlightWithoutTax?withoutTax:withTax)}</div><small>{money(highlightWithoutTax?withTax:withoutTax)} {highlightWithoutTax?"con IVA":"sin IVA"}</small></div>;
}
