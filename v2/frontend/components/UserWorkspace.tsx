"use client";

import { FormEvent,useCallback,useEffect,useState } from "react";
import { apiContext,tenantHeaders } from "../lib/api";

type User={id:string;email:string;display_name:string;status:string;last_login_at:string|null;created_at:string;companies:{company_id:string;company_name:string;role:string}[]};

export function UserWorkspace(){
  const context=apiContext();const[users,setUsers]=useState<User[]>([]);const[message,setMessage]=useState("");
  const load=useCallback(async()=>{if(!context)return;const response=await fetch(`${context.apiUrl}/api/v2/admin/users`,{headers:tenantHeaders(context)});if(response.ok)setUsers((await response.json()).items);else setMessage(response.status===403?"Administrator permission is required.":"Users could not be loaded.")},[context]);
  useEffect(()=>{void load()},[load]);
  async function create(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!context)return;const form=new FormData(event.currentTarget);
    const response=await fetch(`${context.apiUrl}/api/v2/admin/users`,{method:"POST",headers:{...tenantHeaders(context),"Content-Type":"application/json"},body:JSON.stringify({email:form.get("email"),display_name:form.get("name"),temporary_password:form.get("password"),assignments:[{company_id:context.companyId,role:form.get("role")}]})});
    if(response.ok){event.currentTarget.reset();setMessage("User created. A password change is required at first sign-in.");await load()}else{const body=await response.json().catch(()=>({}));setMessage(typeof body.detail==="string"?body.detail:"User creation failed.")}}
  async function changeStatus(user:User){if(!context)return;const action=user.status==="ACTIVE"?"disable":"reactivate";const response=await fetch(`${context.apiUrl}/api/v2/admin/users/${user.id}/${action}`,{method:"POST",headers:tenantHeaders(context)});if(response.ok)await load();else setMessage("User status could not be changed.")}
  if(!context)return <div className="config-state">Sign in or configure the local development identity.</div>;
  return <><form className="user-create panel" onSubmit={create}><div><p className="eyebrow">Authorized administration</p><h2>Create user</h2></div><label><span>Name</span><input name="name" required minLength={2}/></label><label><span>Email</span><input name="email" type="email" required/></label><label><span>Temporary password</span><input name="password" type="password" required minLength={12}/></label><label><span>Role</span><select name="role">{["ACCOUNTANT","OPERATOR","REVIEWER","VIEWER","ADMIN"].map(role=><option key={role}>{role}</option>)}</select></label><button className="primary">Create user</button></form>
    {message&&<p className="inline-message" role="status">{message}</p>}<section className="panel"><div className="panel-heading"><div><p className="eyebrow">Organization access</p><h2>Users</h2></div></div><div className="table-wrap"><table><thead><tr><th>User</th><th>Companies and roles</th><th>Last login</th><th>Status</th><th>Action</th></tr></thead><tbody>{users.map(user=><tr key={user.id}><td><strong>{user.display_name}</strong><small>{user.email}</small></td><td>{user.companies.map(company=><small key={`${company.company_id}-${company.role}`}>{company.company_name} · {company.role}</small>)}</td><td>{user.last_login_at?new Date(user.last_login_at).toLocaleString():"Never"}</td><td><span className={`status status-${user.status.toLowerCase()}`}>{user.status}</span></td><td><button className="filter-button" onClick={()=>void changeStatus(user)} type="button">{user.status==="ACTIVE"?"Disable":"Reactivate"}</button></td></tr>)}</tbody></table></div></section></>;
}
