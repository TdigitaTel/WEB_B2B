"use client";
export type ConsumptionBasis='MEAN'|'MEDIAN'|'MODE';
export const basisLabels:Record<ConsumptionBasis,string>={MEAN:'Media',MEDIAN:'Mediana',MODE:'Moda'};
export default function ConsumptionBasisPicker({value,onChange,name,disabled=false}:{value:ConsumptionBasis;onChange:(value:ConsumptionBasis)=>void;name:string;disabled?:boolean}){
 return <fieldset className="repl-basis" disabled={disabled}><legend>Criterio de consumo</legend>{(Object.entries(basisLabels) as [ConsumptionBasis,string][]).map(([key,label])=><label key={key}><input type="radio" name={name} value={key} checked={value===key} onChange={()=>onChange(key)}/>{label}</label>)}<p className="small">Media mantiene el cálculo habitual (promedio mensual ÷ 30). Mediana y moda usan días con consumo positivo; pueden dar una propuesta mayor. En empates de moda se utiliza la mayor; sin valores repetidos el material queda para revisión. La desviación y la seguridad mantienen el histórico completo.</p></fieldset>
}
