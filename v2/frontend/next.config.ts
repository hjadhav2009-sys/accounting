import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    return [{source:"/:path*",headers:[
      {key:"Content-Security-Policy",value:"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"},
      {key:"Referrer-Policy",value:"same-origin"},
      {key:"X-Content-Type-Options",value:"nosniff"},
      {key:"X-Frame-Options",value:"DENY"},
      {key:"Permissions-Policy",value:"camera=(), microphone=(), geolocation=()"},
    ]}];
  },
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000"}/:path*` }];
  },
};

export default nextConfig;
