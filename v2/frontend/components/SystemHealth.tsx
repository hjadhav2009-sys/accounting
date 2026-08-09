"use client";

import {useEffect,useState} from "react";
import {apiContext,tenantHeaders} from "../lib/api";

type Health={status:string;components:Record<string,{status:string;message:string}>};

export function SystemHealth(){
  const context=apiContext();const[health,setHealth]=useState<Health|null>(null);const[error,setError]=useState("");
  async function run(){if(!context)return;setError("");const response=await fetch(`${context.apiUrl}/api/v2/admin/health`,{headers:tenantHeaders(context)});if(response.ok)setHealth(await response.json());else setError(response.status===403?"Administrator permission is required.":"System check could not be completed.")}
  useEffect(()=>{void run()},[]);
  if(!context)return <div className="config-state">Sign in to run the system check.</div>;
  return <section className="panel"><div className="panel-heading"><div><p className="eyebrow">Passive, non-destructive checks</p><h2>{health?.status==="HEALTHY"?"All Systems Operational":"System status"}</h2></div><button className="filter-button" onClick={()=>void run()}>Run System Check</button></div>
    {error&&<p className="inline-message" role="alert">{error}</p>}<div className="health-grid">{health&&Object.entries(health.components).map(([name,item])=><article className="health-card" key={name}><div><strong>{name.replaceAll("_"," ")}</strong><span className={`status status-${item.status.toLowerCase()}`}>{item.status}</span></div><p>{item.message}</p></article>)}</div></section>;
}
