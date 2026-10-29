import type { Metadata } from 'next'
export const routes = [
  ['/', 'Home'], ['/features', 'Features'], ['/how-it-works', 'How it works'], ['/privacy', 'Privacy'], ['/download', 'Download'],
] as const
// A preview host is not automatically a verified public product domain.
export function publicOrigin(value = process.env.SITE_URL): string | null {
  if (!value) return null
  const url = new URL(value)
  if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error('SITE_URL must be a public HTTPS origin without a path or credentials.')
  return url.origin
}
export function pageMetadata(title: string, description: string, pathname: string): Metadata {
  const origin = publicOrigin()
  return { title: pathname === '/' ? { absolute: `SolveGuide AI — ${title}` } : title, description, ...(origin ? { alternates: { canonical: pathname } } : {}), openGraph: { title: `${title} | SolveGuide AI`, description, type: 'website', siteName: 'SolveGuide AI', images: [{ url: '/social-card.png', width: 1200, height: 630, alt: 'SolveGuide AI — Your intelligent desktop learning companion' }], ...(origin ? { url: pathname } : {}) }, twitter: { card: 'summary_large_image', images: ['/social-card.png'], title: `${title} | SolveGuide AI`, description } }
}
