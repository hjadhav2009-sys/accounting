export type ApiContext = {
  apiUrl: string;
  organizationId: string;
  companyId: string;
  userId: string;
  roles: string;
};

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
