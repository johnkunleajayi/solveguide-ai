import type { MetadataRoute } from 'next'
import { publicOrigin } from '@/lib/site'
export default function robots(): MetadataRoute.Robots { const origin = publicOrigin(); return { rules: { userAgent: '*', ...(origin ? { allow: '/' } : { disallow: '/' }) }, ...(origin ? { sitemap: `${origin}/sitemap.xml` } : {}) } }
