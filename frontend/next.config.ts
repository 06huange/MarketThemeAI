import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root to this folder. Otherwise Next.js picks the highest
  // lockfile it finds above the project (e.g. a stray ~/package-lock.json) and
  // scans that whole directory tree.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
