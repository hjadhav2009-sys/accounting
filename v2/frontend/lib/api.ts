export type ApiContext = {
  apiUrl: string;
  organizationId: string;
  companyId: string;
  userId: string;
  roles: string;
};

export type AuthorizedCompany = {id:string;name:string;roles:string[]};
export const COMPANY_ACCESS_CHANGED = "ba:company-access-changed";

export class ApiError extends Error {
  constructor(public status:number,public code:string,message:string,public requestId:string){super(message);this.name="ApiError"}
}

function correlationId():string{
  return typeof crypto!=="undefined"&&"randomUUID" in crypto?crypto.randomUUID():`web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function apiFetch(input:string,init:RequestInit={}):Promise<Response>{
  const requestId=correlationId();const headers=new Headers(init.headers);headers.set("X-Request-ID",requestId);
  const csrf=typeof window!=="undefined"?window.sessionStorage.getItem("ba_csrf_token")||"":"";
  if(csrf&&!headers.has("X-CSRF-Token"))headers.set("X-CSRF-Token",csrf);
  try{return await fetch(input,{...init,headers,credentials:init.credentials||"same-origin"})}
  catch(reason){throw new ApiError(0,"NETWORK_ERROR",reason instanceof Error?reason.message:"The backend could not be reached.",requestId)}
}

export async function apiRequest<T>(input:string,init:RequestInit={}):Promise<T>{
  const response=await apiFetch(input,init);const requestId=response.headers.get("X-Request-ID")||"unknown";
  const body=await response.json().catch(()=>({}));
  if(!response.ok){const detail=body?.detail;const code=String(detail?.code||body?.code||
      (response.status===401?"AUTHENTICATION_REQUIRED":response.status===403?"PERMISSION_DENIED":"API_ERROR"));
    throw new ApiError(response.status,code,String(detail?.message||detail||body?.message||`Request failed (${response.status}).`),requestId)}
  return body as T;
}

export function selectAuthorizedCompany(company: AuthorizedCompany): boolean {
  if (typeof window === "undefined") return false;
  const raw=window.sessionStorage.getItem("ba_session_info");
  if(!raw)return false;
  try{
    const info=JSON.parse(raw);info.company_id=company.id;info.roles=company.roles;
    window.sessionStorage.setItem("ba_session_info",JSON.stringify(info));
    return true;
  }catch{return false}
}

export async function authorizedCompanies(apiUrl=process.env.NEXT_PUBLIC_API_URL||"/backend"):Promise<AuthorizedCompany[]>{
  const body=await apiRequest<{items:AuthorizedCompany[]}>(`${apiUrl}/api/v2/auth/companies`,{cache:"no-store"});
  return Array.isArray(body.items)?body.items:[];
}

let cachedContext: ApiContext | null | undefined;

export function apiContext(): ApiContext | null {
  if (typeof window !== "undefined") {
    const stored=window.sessionStorage.getItem("ba_session_info");
    if(stored){try{const value=JSON.parse(stored);return {apiUrl:process.env.NEXT_PUBLIC_API_URL||"/backend",
      organizationId:String(value.organization_id||""),companyId:String(value.company_id||""),
      userId:String(value.user?.id||""),roles:Array.isArray(value.roles)?value.roles.join(","):"VIEWER"}}catch{/* use development fallback */}}
  }
  if (cachedContext !== undefined) return cachedContext;
  const context = {
    apiUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    organizationId: process.env.NEXT_PUBLIC_ORGANIZATION_ID || "",
    companyId: process.env.NEXT_PUBLIC_COMPANY_ID || "",
    userId: process.env.NEXT_PUBLIC_USER_ID || "",
    roles: process.env.NEXT_PUBLIC_USER_ROLES || "ADMIN",
  };
  cachedContext = context.organizationId && context.companyId && context.userId ? context : null;
  return cachedContext;
}

export function tenantHeaders(context: ApiContext): HeadersInit {
  const csrf = typeof window !== "undefined" ? window.sessionStorage.getItem("ba_csrf_token") || "" : "";
  return {
    "X-Organization-ID": context.organizationId,
    "X-Company-ID": context.companyId,
    "X-User-ID": context.userId,
    "X-Roles": context.roles,
    ...(csrf ? { "X-CSRF-Token": csrf } : {}),
  };
}
