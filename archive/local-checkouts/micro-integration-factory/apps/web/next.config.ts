import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  devIndicators: false,
  transpilePackages: ["@spec2event/shared"]
};

export default nextConfig;
