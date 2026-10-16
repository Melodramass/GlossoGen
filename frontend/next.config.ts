import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Stops `next dev` from writing an AGENTS.md here; CLAUDE.md carries its advice instead.
  agentRules: false,
};

export default nextConfig;
