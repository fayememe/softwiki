import type { NextConfig } from "next";

const API_PORT = process.env.NEXT_PUBLIC_API_PORT || '6200';
const API_INTERNAL_URL =
  process.env.API_INTERNAL_URL || `http://127.0.0.1:${API_PORT}`;

const nextConfig: NextConfig = {
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${API_INTERNAL_URL}/api/:path*`,
      },
      {
        source: '/wiki/:path*',
        destination: `${API_INTERNAL_URL}/wiki/:path*`,
      },
      {
        source: '/wiki',
        destination: `${API_INTERNAL_URL}/wiki`,
      },
    ];
  },
};

export default nextConfig;
