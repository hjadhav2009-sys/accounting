"use client";

import {useEffect,useState} from "react";

type Company={id:string;name:string;roles:string[]};

export function CompanySwitcher(){
  const[companies,setCompanies]=useState<Company[]>([]);const[selected,setSelected]=useState("");
  useEffect(()=>{let active=true;const raw=window.sessionStorage.getItem("ba_session_info");if(raw){try{setSelected(JSON.parse(raw).company_id||"")}catch{}}
    fetch(`${process.env.NEXT_PUBLIC_API_URL||"/backend"}/api/v2/auth/companies`).then(async response=>response.ok?response.json():null).then(body=>{if(active&&body)setCompanies(body.items)}).catch(()=>{});return()=>{active=false}},[]);
  function choose(companyId:string){setSelected(companyId);const company=companies.find(item=>item.id===companyId);const raw=window.sessionStorage.getItem("ba_session_info");if(raw&&company){try{const info=JSON.parse(raw);info.company_id=company.id;info.roles=company.roles;window.sessionStorage.setItem("ba_session_info",JSON.stringify(info));window.location.reload()}catch{}}}
  const developmentId=process.env.NEXT_PUBLIC_COMPANY_ID||"";
  return <label className="switcher"><span>Company</span><select aria-label="Selected company" value={selected||developmentId||"none"} onChange={event=>choose(event.target.value)}>
    {companies.length?companies.map(company=><option key={company.id} value={company.id}>{company.name}</option>):<option value={developmentId||"none"}>{developmentId?`Development company ${developmentId.slice(0,8)}â€¦`:"No authorized company"}</option>}
  </select></label>;
}
