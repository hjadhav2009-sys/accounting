"use client";

import { FormEvent,useState } from "react";
import { useRouter } from "next/navigation";

export function LoginForm(){
  const router=useRouter();const[busy,setBusy]=useState(false);const[message,setMessage]=useState("");
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setMessage("");const data=new FormData(event.currentTarget);
    try{const response=await fetch(`${process.env.NEXT_PUBLIC_API_URL||"/backend"}/api/v2/auth/login`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({organization:data.get("organization"),email:data.get("email"),password:data.get("password")})});
      const contentType=response.headers.get("content-type")||"";const body=contentType.includes("application/json")?await response.json():{};
      if(!response.ok)throw new Error(response.status===401?"Email, password, or organization was not accepted.":"The sign-in service is temporarily unavailable. Try again.");
      window.sessionStorage.setItem("ba_csrf_token",body.csrf_token);window.sessionStorage.setItem("ba_session_info",JSON.stringify(body));router.push("/");router.refresh();
    }catch(error){setMessage(error instanceof Error?error.message:"Login failed. Try again.")}finally{setBusy(false)}
  }
  return <form className="login-card" onSubmit={submit}><div className="brand login-brand"><span>BA</span><div><strong>Business Automation</strong><small>Secure V2 workspace</small></div></div>
    <div><p className="eyebrow">Production sign in</p><h1>Welcome back</h1><p>Use the account created by your organization administrator.</p></div>
    <label><span>Organization</span><input name="organization" autoComplete="organization" required/></label>
    <label><span>Email</span><input name="email" type="email" autoComplete="username" required/></label>
    <label><span>Password</span><input name="password" type="password" autoComplete="current-password" required minLength={12}/></label>
    {message&&<p className="login-error" role="alert">{message}</p>}<button className="primary" disabled={busy}>{busy?"Signing in…":"Sign in"}</button>
    <small className="muted">Sessions expire automatically and can be revoked by an administrator.</small></form>;
}
