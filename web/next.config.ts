import type { NextConfig } from "next";

const API_PORT = process.env.NEXT_PUBLIC_API_PORT || '6200';

const nextConfig: NextConfig = {
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `http://127.0.0.1:${API_PORT}/api/:path*`,
      },
      {
        source: '/wiki/:path*',
        destination: `http://127.0.0.1:${API_PORT}/wiki/:path*`,
      },
      {
        source: '/wiki',
        destination: `http://127.0.0.1:${API_PORT}/wiki`,
      },
    ];
  },
};

export default nextConfig;
