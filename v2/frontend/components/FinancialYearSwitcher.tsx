"use client";

import {useEffect,useState} from "react";
import {apiContext,tenantHeaders} from "../lib/api";

type Year={id:string;label:string;starts_on:string;ends_on:string};

export function FinancialYearSwitcher(){
  const context=apiContext();const[years,setYears]=useState<Year[]>([]);const[selected,setSelected]=useState("");
  useEffect(()=>{if(!context)return;const saved=window.sessionStorage.getItem("ba_financial_year")||"";fetch(`${context.apiUrl}/api/v2/financial-years`,{headers:tenantHeaders(context)}).then(async response=>response.ok?response.json():null).then(body=>{if(!body)return;setYears(body.items);const value=body.items.some((item:Year)=>item.id===saved)?saved:(body.items[0]?.id||"");setSelected(value);if(value)window.sessionStorage.setItem("ba_financial_year",value)}).catch(()=>{})},[context]);
  function choose(value:string){setSelected(value);if(value)window.sessionStorage.setItem("ba_financial_year",value);else window.sessionStorage.removeItem("ba_financial_year");window.location.reload()}
  return <label className="switcher compact"><span>Financial year</span><select aria-label="Financial year" value={selected} onChange={event=>choose(event.target.value)}><option value="">All dates</option>{years.map(year=><option value={year.id} key={year.id}>{year.label}</option>)}</select></label>;
}
