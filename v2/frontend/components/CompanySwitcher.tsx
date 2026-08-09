"use client";

import {useCallback,useEffect,useState} from "react";
import {authorizedCompanies,AuthorizedCompany,COMPANY_ACCESS_CHANGED,selectAuthorizedCompany} from "../lib/api";

type Company=AuthorizedCompany;

export function CompanySwitcher(){
  const[companies,setCompanies]=useState<Company[]>([]);const[selected,setSelected]=useState("");
  const refresh=useCallback(async()=>{try{setCompanies(await authorizedCompanies())}catch{/* surfaced by page-level API states */}},[]);
  useEffect(()=>{const raw=window.sessionStorage.getItem("ba_session_info");if(raw){try{setSelected(JSON.parse(raw).company_id||"")}catch{}}
    void refresh();const onChanged=()=>void refresh();window.addEventListener(COMPANY_ACCESS_CHANGED,onChanged);return()=>window.removeEventListener(COMPANY_ACCESS_CHANGED,onChanged)},[refresh]);
  function choose(companyId:string){setSelected(companyId);const company=companies.find(item=>item.id===companyId);if(company&&selectAuthorizedCompany(company))window.location.reload()}
  const developmentId=process.env.NEXT_PUBLIC_COMPANY_ID||"";
  return <label className="switcher"><span>Company</span><select aria-label="Selected company" value={selected||developmentId||"none"} onChange={event=>choose(event.target.value)}>
    {companies.length?companies.map(company=><option key={company.id} value={company.id}>{company.name}</option>):<option value={developmentId||"none"}>{developmentId?`Development company ${developmentId.slice(0,8)}…`:"No authorized company"}</option>}
  </select></label>;
}
