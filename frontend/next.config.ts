import type { NextConfig } from "next";
const config: NextConfig = {
  distDir: process.env.CI_SENSE_BUILD_DIR || ".next",
  async headers() { return [{source:"/:path*",headers:[
    {key:"X-Content-Type-Options",value:"nosniff"},
    {key:"Referrer-Policy",value:"no-referrer"},
    {key:"X-Frame-Options",value:"DENY"}
  ]}]; }
};
export default config;
