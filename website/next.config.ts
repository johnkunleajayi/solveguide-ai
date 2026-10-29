import type { NextConfig } from 'next'
import path from 'node:path'
const config: NextConfig = {
  poweredByHeader: false,
  outputFileTracingRoot: path.resolve(process.cwd(), '..'),
  async headers() {
    return [{ source: '/:path*', headers: [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
      { key: 'X-Frame-Options', value: 'DENY' },
    ] }]
  },
}
export default config
