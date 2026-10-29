import Link from 'next/link'
import { Brand } from './Brand'
import { ThemeControl } from './ThemeControl'
import { MobileMenu } from './MobileMenu'
const links = [['/features','Features'],['/how-it-works','How it works'],['/privacy','Privacy']] as const
export function Header() {
  return <header className="site-header"><div className="container header-inner"><Brand /><nav className="desktop-nav" aria-label="Main navigation">{links.map(([href,label]) => <Link key={href} href={href}>{label}</Link>)}</nav><div className="header-tools"><ThemeControl /><Link className="button button-small header-download" href="/download">Windows <span aria-hidden="true">↗</span></Link><MobileMenu /></div></div></header>
}
export function Footer() {
 return <footer className="site-footer"><div className="container"><div className="footer-top"><div><Brand /><p>A little clarity changes everything.</p></div><nav aria-label="Footer navigation">{links.map(([href,label]) => <Link key={href} href={href}>{label}</Link>)}<Link href="/download">Download</Link></nav></div><div className="footer-bottom"><p>SolveGuide AI · Windows desktop learning companion.</p><p>Public release coming soon.</p></div></div></footer>
}
export function DownloadLink({ compact = false }: { compact?: boolean }) { return <Link className="button button-primary" href="/download">{compact ? 'Windows release · Coming Soon' : 'Download for Windows — Coming Soon'}<span aria-hidden="true">↗</span></Link> }
export function Closing() { return <section className="closing section"><div className="container"><p className="eyebrow">A CLEARER WAY TO LEARN</p><h2>Bring the question.<br /><span className="gradient-text">Leave with understanding.</span></h2><p>One focused desktop workspace. Your questions, your materials, your next step.</p><DownloadLink /></div></section> }
export function PageIntro({ eyebrow, title, accent, children }: { eyebrow: string; title: string; accent: string; children: React.ReactNode }) { return <section className="page-intro container"><p className="eyebrow">{eyebrow}</p><h1>{title}<br /><span className="gradient-text">{accent}</span></h1><div className="lede">{children}</div></section> }
