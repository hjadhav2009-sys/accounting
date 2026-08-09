"use client";

import { useRouter } from "next/navigation";
import { apiContext, tenantHeaders } from "../lib/api";

export function AuthControls() {
  const router=useRouter();const context=apiContext();
  async function logout(){
    if(context)await fetch(`${context.apiUrl}/api/v2/auth/logout`,{method:"POST",headers:tenantHeaders(context)}).catch(()=>undefined);
    window.sessionStorage.removeItem("ba_csrf_token");window.sessionStorage.removeItem("ba_session_info");router.push("/login");router.refresh();
  }
  return <button className="notification" onClick={logout}>Log out</button>;
}
