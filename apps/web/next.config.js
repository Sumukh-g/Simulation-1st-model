/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The backend base URL is configurable so the same build works in dev,
  // Docker, and production without code changes.
  async rewrites() {
    const apiBase = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');
    return [
      {
        // Keep /api prefix — FastAPI mounts runs under /api
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
  webpack: (config) => {
    // Escape hatch for environments where a synced filesystem (e.g. OneDrive)
    // locks files under .next/cache and stalls the production build. Opt in
    // with NEXT_DISABLE_WEBPACK_CACHE=1; default behaviour is unchanged.
    if (process.env.NEXT_DISABLE_WEBPACK_CACHE === '1') {
      config.cache = false;
    }
    return config;
  },
};

module.exports = nextConfig;
