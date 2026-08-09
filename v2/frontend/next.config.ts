import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000"}/:path*` }];
  },
};

export default nextConfig;
