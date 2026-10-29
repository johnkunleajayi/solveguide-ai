import type { Metadata } from 'next'
import { Header, Footer } from '@/components/Shell'
import { publicOrigin } from '@/lib/site'
import { themeBootstrap } from '@/lib/theme'
import './globals.css'
const origin = publicOrigin()
export const metadata: Metadata = {
  metadataBase: new URL(origin ?? 'http://localhost:3000'),
  title: { default: 'SolveGuide AI — Your intelligent desktop learning companion', template: '%s | SolveGuide AI' },
  description: 'Understand questions, explore AI-assisted recommendations and work with your own reference materials. Built for Windows. Public download coming soon.',
  applicationName: 'SolveGuide AI',
  robots: { index: !!origin, follow: !!origin },
  openGraph: { siteName: 'SolveGuide AI', locale: 'en_US', type: 'website', images: [{ url: '/social-card.png', width: 1200, height: 630, alt: 'SolveGuide AI — Your intelligent desktop learning companion' }] },
  twitter: { card: 'summary_large_image', images: ['/social-card.png'] },
  icons: { icon: '/icon.svg' },
}
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeBootstrap }} /></head><body><noscript><style>{`.theme-control{display:none}`}</style></noscript><a className="skip-link" href="#main">Skip to content</a><Header /><main id="main" tabIndex={-1}>{children}</main><Footer /></body></html>
}
