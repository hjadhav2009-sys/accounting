export type ApiContext = {
  apiUrl: string;
  organizationId: string;
  companyId: string;
  userId: string;
};

let cachedContext: ApiContext | null | undefined;

export function apiContext(): ApiContext | null {
  if (cachedContext !== undefined) return cachedContext;
  const context = {
    apiUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    organizationId: process.env.NEXT_PUBLIC_ORGANIZATION_ID || "",
    companyId: process.env.NEXT_PUBLIC_COMPANY_ID || "",
    userId: process.env.NEXT_PUBLIC_USER_ID || "",
  };
  cachedContext = context.organizationId && context.companyId && context.userId ? context : null;
  return cachedContext;
}

export function tenantHeaders(context: ApiContext): HeadersInit {
  return {
    "X-Organization-ID": context.organizationId,
    "X-Company-ID": context.companyId,
    "X-User-ID": context.userId,
  };
}
