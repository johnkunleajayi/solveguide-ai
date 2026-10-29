import { useId, useState } from 'react'
import { ArrowUpRight, BookOpen, Check, ChevronRight, Command, Moon, ShieldCheck, Sun } from 'lucide-react'
import { Brand } from '../components/Brand'

const palette = [
  ['Deep Charcoal', '#0B0E0D', 'charcoal'],
  ['Pure White', '#FFFFFF', 'white'],
  ['Luminous Mint', '#A3FFCF', 'mint'],
  ['Vibrant Green', '#55E6A5', 'green'],
  ['Muted Sage', '#9AADA1', 'sage'],
] as const

function ProductSpecimen() {
  const gradientId = useId()
  return <figure className="sg-specimen" aria-labelledby="specimen-caption">
    <div className="sg-specimen-top"><span className="sg-eyebrow">SOLVEGUIDE / CLARITY IN CONTEXT</span><span className="sg-signal" aria-hidden="true" /></div>
    <div className="sg-signal-field" aria-hidden="true">
      <svg viewBox="0 0 520 220" fill="none"><defs><linearGradient id={gradientId} x1="20" y1="210" x2="500" y2="20" gradientUnits="userSpaceOnUse"><stop stopColor="var(--sg-border)" /><stop offset=".55" stopColor="var(--sg-accent)" /><stop offset="1" stopColor="var(--sg-border)" /></linearGradient></defs>
        <path d="M25 175H132L192 110H320L382 47H495M25 47H132L192 110M320 110L382 175H495" stroke={`url(#${gradientId})`} />
        <circle cx="256" cy="110" r="62" stroke="var(--sg-border)" /><circle cx="256" cy="110" r="46" stroke="var(--sg-border-strong)" />
        <path d="M242 110h28M256 96v28" stroke="var(--sg-accent)" strokeWidth="2" />
        <circle cx="132" cy="175" r="4" fill="var(--sg-accent)" /><circle cx="382" cy="47" r="4" fill="var(--sg-accent)" />
      </svg>
      <span className="sg-node sg-node-source">Reference</span><span className="sg-node sg-node-understand">Understanding</span><span className="sg-node sg-node-clarity">Clarity</span>
    </div>
    <div className="sg-evidence-card"><div><BookOpen size={18} aria-hidden="true" /><span className="sg-eyebrow">EVIDENCE, WITH A PLACE</span></div><p>Make every recommendation traceable to its source.</p><span className="sg-caption">Source passage <ChevronRight size={13} aria-hidden="true" /> Clear explanation</span></div>
    <figcaption id="specimen-caption">Illustrative product specimen · no question or answer is being processed.</figcaption>
  </figure>
}

export function BrandShowcase({ initialTheme = 'dark' }: { initialTheme?: 'dark' | 'light' }) {
  const [theme, setTheme] = useState(initialTheme)
  const [feedback, setFeedback] = useState('Samples only. No account, capture or provider requests.')
  const [navigation, setNavigation] = useState('Workspace')
  const sample = (name: string) => setFeedback(`${name} sample selected. No application action was started.`)
  return <div className="sg-showcase" data-sg-theme={theme}>
    <a className="sg-skip" href="#brand-main">Skip to brand specimens</a>
    <header className="sg-showcase-header"><Brand /><span className="sg-development">BRAND FOUNDATION / 11A</span><button className="sg-button sg-button-secondary" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
      {theme === 'dark' ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}{theme === 'dark' ? 'Light' : 'Dark'} theme</button></header>
    <main id="brand-main" className="sg-showcase-main" tabIndex={-1}>
      <section className="sg-hero" aria-labelledby="brand-title"><div><span className="sg-eyebrow sg-accent">INTELLIGENCE. GIVEN DIRECTION.</span><h1 id="brand-title">Clarity,<br /><span className="sg-gradient-text">with direction.</span></h1><p className="sg-hero-copy">Understand the question. Find the answer. Learn why.</p><p className="sg-body-copy">A precise foundation for a more considered learning experience. Deep charcoal. Confident type. A purposeful edge of light.</p><a className="sg-button sg-button-primary" href="#brand-components">Explore the foundation <ArrowUpRight size={17} aria-hidden="true" /></a><span className="sg-caption sg-hero-note">Design specimen · development only</span></div><ProductSpecimen /></section>
      <section className="sg-section" aria-labelledby="palette-title"><div className="sg-section-title"><span className="sg-eyebrow">01 / COLOUR</span><h2 id="palette-title">A neutral foundation.<br />An unmistakable accent.</h2><p>Mint identifies intent. Green reinforces movement. Sage provides balance.</p></div><div className="sg-palette">{palette.map(([name, hex, key]) => <div className="sg-swatch" key={key}><div className={`sg-swatch-colour sg-swatch-${key}`} aria-hidden="true" /><h3>{name}</h3><code>{hex}</code></div>)}</div><p className="sg-caption">Raw palette colours are not universal text colours. Theme-specific semantic roles preserve contrast.</p></section>
      <section className="sg-section sg-type-grid" aria-labelledby="type-title"><div className="sg-section-title"><span className="sg-eyebrow">02 / TYPOGRAPHY</span><h2 id="type-title">Strong ideas.<br />Quiet precision.</h2><p>Local system typography. No remote font requests. Readable at application scale; expressive at display scale.</p></div><div className="sg-type-specimens"><div><span className="sg-caption">DISPLAY / 600 / COMPACT LEADING</span><p className="sg-type-display">Understanding,<br /><span className="sg-gradient-text">illuminated.</span></p></div><div><span className="sg-caption">APPLICATION HEADING / 600</span><p className="sg-type-heading">Evidence gives an answer direction.</p></div><div><span className="sg-caption">BODY / 400 / 1.7 LEADING</span><p className="sg-body-copy">Clear explanations should feel comfortable to read. Give important ideas space, keep sources visible, and let the content lead.</p></div><div><span className="sg-eyebrow">RESTRAINED METADATA</span><code className="sg-technical">source.reference · page 12 · UTF-8</code></div></div></section>
      <section id="brand-components" className="sg-section" aria-labelledby="components-title"><div className="sg-section-title"><span className="sg-eyebrow">03 / INTERACTION</span><h2 id="components-title">Confidence in every detail.</h2><p>One primary action. A visible focus. Feedback without theatre.</p></div><div className="sg-component-grid"><article className="sg-card"><h3>Action hierarchy</h3><p>Mint carries the primary action. Secondary actions stay composed.</p><div className="sg-actions"><button className="sg-button sg-button-primary" onClick={() => sample('Primary action')}>Primary action <ArrowUpRight size={16} aria-hidden="true" /></button><button className="sg-button sg-button-secondary" onClick={() => sample('Secondary action')}>Secondary action</button><button className="sg-button sg-button-quiet" onClick={() => sample('Quiet action')}>Quiet action <ChevronRight size={15} aria-hidden="true" /></button><button className="sg-button" disabled>Unavailable</button></div><p className="sg-caption" role="status" aria-live="polite">{feedback}</p></article><article className="sg-card"><h3>Navigation & focus</h3><nav className="sg-nav-specimen" aria-label="Navigation specimen">{(['Workspace', 'Materials'] as const).map(label => <button key={label} aria-current={navigation === label ? 'page' : undefined} onClick={() => { setNavigation(label); sample(label) }}>{label === 'Workspace' ? <Command size={16} aria-hidden="true" /> : <BookOpen size={16} aria-hidden="true" />}{label}</button>)}</nav><label className="sg-caption" htmlFor="brand-reference-title">Reference title · focus specimen</label><input id="brand-reference-title" className="sg-input" defaultValue="Learning notes" /><p className="sg-caption">Tab through the controls to inspect the focus ring.</p></article></div></section>
      <section className="sg-section sg-component-grid" aria-labelledby="surface-title"><div className="sg-section-title"><span className="sg-eyebrow">04 / SURFACES & SIGNALS</span><h2 id="surface-title">Light with a purpose.</h2><p>Opaque surfaces. Hairline separation. Glow reserved for moments of intent.</p><div className="sg-statuses"><span className="sg-status-success"><Check size={14} aria-hidden="true" />Ready</span><span className="sg-status-warning">Review needed</span><span className="sg-status-danger">Unavailable</span><span className="sg-status-info"><ShieldCheck size={14} aria-hidden="true" />Private by design</span></div></div><article className="sg-card sg-card-premium"><span className="sg-eyebrow sg-accent">SURFACE SPECIMEN</span><h3>A little clarity changes everything.</h3><p>Elevation comes from hierarchy and contrast. It does not require a wall of glowing panels.</p><div className="sg-rule" /><span className="sg-caption">16px radius · subtle elevation · controlled mint light</span></article></section>
      <footer className="sg-showcase-footer"><span>SolveGuide AI · Brand foundation v1</span><span>Desktop today. Shared identity for the future website.</span></footer>
    </main>
  </div>
}
