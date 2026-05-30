import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // output: "standalone" is used for Docker self-hosting.
  // Remove it (or set NEXT_OUTPUT=standalone) for Vercel deployments.
  ...(process.env.NEXT_OUTPUT === "standalone" ? { output: "standalone" as const } : {}),
  async rewrites() {
    // API_URL is a server-only variable (not exposed to the browser).
    // Set it on Vercel to your Render backend URL, e.g. https://your-app.onrender.com
    // NEXT_PUBLIC_API_URL is supported for backward compatibility.
    const backendUrl =
      process.env.API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
