import type { MetadataRoute } from 'next'
import { publicOrigin, routes } from '@/lib/site'
export default function sitemap(): MetadataRoute.Sitemap { const origin = publicOrigin(); return origin ? routes.map(([path]) => ({ url: `${origin}${path}`, changeFrequency: 'monthly', priority: path === '/' ? 1 : .7 })) : [] }
