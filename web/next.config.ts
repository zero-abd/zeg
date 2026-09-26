import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    // The read-only prepared demo is a static page copied in by scripts/copy-assets.mjs.
    async rewrites() {
        return [{ source: "/demo", destination: "/demo.html" }];
    },
};

export default nextConfig;
