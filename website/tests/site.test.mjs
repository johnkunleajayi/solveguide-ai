import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'
import test from 'node:test'
import ts from 'typescript'
const require = createRequire(import.meta.url)
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const root = fileURLToPath(new URL('../', import.meta.url))
const cache = new Map()
function load(file) {
  if (cache.has(file)) return cache.get(file)
  const output = ts.transpileModule(readFileSync(path.join(root, file), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText
  const compiled = { exports: {} }
  const resolve = id => {
    if (id.startsWith('@/') || id.startsWith('.')) {
      const relative = id.startsWith('@/') ? id.slice(2) : path.join(path.dirname(file), id)
      return load(relative + (['.ts', '.tsx'].find(ext => { try { readFileSync(path.join(root, relative + ext)); return true } catch { return false } }) ?? ''))
    }
    return require(id)
  }
  new Function('require', 'module', 'exports', output)(resolve, compiled, compiled.exports)
  cache.set(file, compiled.exports)
  return compiled.exports
}
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props))
const pages = ['app/page.tsx', 'app/features/page.tsx', 'app/how-it-works/page.tsx', 'app/privacy/page.tsx', 'app/download/page.tsx']
test('all public pages render one h1, metadata, and no forms or real download payload', () => {
  for (const file of pages) {
    const page = load(file)
    const html = render(page.default)
    assert.equal((html.match(/<h1[ >]/g) ?? []).length, 1, file)
    assert.ok(page.metadata.description.length > 50)
    assert.ok(page.metadata.openGraph.images[0].url.endsWith('.png'))
    assert.doesNotMatch(html, /<form|href="[^\"]*\.(exe|msi)|download="/)
  }
})
test('release messaging is honest and download remains disabled', () => {
  const html = render(load('app/download/page.tsx').default)
  assert.match(html, /Coming Soon/)
  assert.match(html, /<button[^>]*disabled=""[^>]*>Installer not yet available/)
  assert.match(html, /No release date has been announced/)
})
test('illustrations disclose fictional content and never impersonate live controls', () => {
  const html = render(load('components/ProductPreview.tsx').ProductPreview)
  assert.match(html, /fictional practice question/)
  assert.match(html, /aria-label="Illustrated capture source selection"/)
  assert.match(html, /Not a captured screenshot or live recommendation/)
  assert.doesNotMatch(html, /<button|<input|<form/)
})
test('workflow stays explicit and includes separate reading and recommendation', () => {
  const { steps, modes } = load('lib/content.ts')
  assert.deepEqual(steps.map(s => s[0]), ['Sign in', 'Choose the source', 'Capture the question', 'Read Question', 'Get Suggested Answer', 'Review and learn'])
  assert.deepEqual(modes.map(m => m[1]), ['General', 'Context Guided', 'Materials Only'])
  assert.match(render(load('app/how-it-works/page.tsx').default), /not the screenshot again/)
})
test('privacy distinguishes persistent materials, ephemeral learning and provider transmission', () => {
  const html = render(load('app/privacy/page.tsx').default)
  for (const phrase of ['ephemeral', 'Semantic indexing sends document text', 'SetWindowDisplayAffinity', 'not a legal privacy policy', 'not DRM', 'native memory']) assert.ok(html.includes(phrase), phrase)
  assert.doesNotMatch(html, /100%|guaranteed correct|undetectable/)
})
test('theme bootstrap resolves stored/system choices before paint, tolerating unavailable storage', () => {
  const { themeBootstrap } = load('lib/theme.ts')
  for (const [stored, systemDark, expected] of [['dark', false, 'dark'], ['light', true, 'light'], ['system', true, 'dark'], ['invalid', false, 'light'], [null, true, 'dark']]) {
    const document = { documentElement: { dataset: {} } }
    vm.runInNewContext(themeBootstrap, { document, localStorage: { getItem: () => stored }, matchMedia: () => ({ matches: systemDark }) })
    assert.equal(document.documentElement.dataset.theme, expected)
  }
  const document = { documentElement: { dataset: {} } }
  vm.runInNewContext(themeBootstrap, { document, localStorage: { getItem: () => { throw Error('blocked') } }, matchMedia: () => ({ matches: false }) })
  assert.equal(document.documentElement.dataset.theme, 'light')
})
test('mobile menu and theme control expose accessible native elements', () => {
  const menu = render(load('components/MobileMenu.tsx').MobileMenu)
  assert.match(menu, /<details/); assert.match(menu, /<summary>Menu/); assert.match(menu, /aria-label="Mobile navigation"/)
  const theme = render(load('components/ThemeControl.tsx').ThemeControl)
  assert.match(theme, /aria-label="Website theme"/)
  assert.equal((theme.match(/<option/g) ?? []).length, 3)
})
test('canonical and sitemap origins are explicit; unconfigured previews stay unindexed', () => {
  const { publicOrigin } = load('lib/site.ts')
  assert.equal(publicOrigin(''), null)
  assert.equal(publicOrigin('https://example.com'), 'https://example.com')
  for (const origin of ['http://example.com', 'https://user:secret@example.com', 'https://example.com/path']) assert.throws(() => publicOrigin(origin))
  const previous = process.env.SITE_URL
  try {
    delete process.env.SITE_URL
    assert.deepEqual(load('app/sitemap.ts').default(), [])
    assert.equal(load('app/robots.ts').default().rules.disallow, '/')
    process.env.SITE_URL = 'https://example.com'
    assert.equal(load('app/sitemap.ts').default().length, 5)
  } finally { if (previous === undefined) delete process.env.SITE_URL; else process.env.SITE_URL = previous }
})
test('website keeps application services out and shared CSS remains its brand source', () => {
  const files = directory => readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? files(path.join(directory, entry.name)) : [path.join(directory, entry.name)])
  for (const file of [...files(path.join(root, 'app')), ...files(path.join(root, 'components'))]) {
    const source = readFileSync(file, 'utf8')
    assert.doesNotMatch(source, /@tauri|OPENAI_API_KEY|GOOGLE_CLIENT_SECRET|DATABASE_URL|fetch\(|next\/font|googletagmanager|analytics\.js/)
  }
  const css = readFileSync(path.join(root, 'app/globals.css'), 'utf8')
  assert.match(css, /@import "\.\.\/\.\.\/brand\/tokens.css"/)
  assert.match(css, /prefers-reduced-motion:reduce/)
  assert.match(css, /forced-colors:active/)
  assert.match(css, /:focus-visible/)
})

test('public links stay within implemented pages and do not point to development binaries', () => {
  const allowed = new Set(load('lib/site.ts').routes.map(([route]) => route))
  for (const file of pages) {
    const html = render(load(file).default)
    for (const [, href] of html.matchAll(/href="([^\"]+)"/g)) assert.ok(allowed.has(href.split('#')[0]), `${file}: ${href}`)
  }
})

test('shared dark/light text, accent and action roles preserve readable contrast', () => {
  const css = readFileSync(new URL('../../brand/tokens.css', import.meta.url), 'utf8')
  const blocks = [...css.matchAll(/([^{}]+)\{([^{}]+)\}/g)]
  const declarations = block => Object.fromEntries([...block.matchAll(/(--sg-[\w-]+):\s*([^;]+);/g)].map(([, key, value]) => [key, value.trim()]))
  const primitives = declarations(blocks[0][2])
  const luminance = hex => {
    const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4)
    return .2126 * r + .7152 * g + .0722 * b
  }
  const contrast = (a, b) => { const values = [luminance(a), luminance(b)].sort((a, b) => b - a); return (values[0] + .05) / (values[1] + .05) }
  for (const block of blocks.slice(1)) {
    const roles = { ...primitives, ...declarations(block[2]) }
    const resolve = name => { let value = roles[`--sg-${name}`]; for (let i = 0; i < 8 && value.startsWith('var('); i++) value = roles[value.slice(4, -1)]; return value }
    for (const foreground of ['text', 'text-secondary', 'text-muted', 'accent']) for (const background of ['canvas', 'canvas-deep', 'surface', 'surface-raised']) assert.ok(contrast(resolve(foreground), resolve(background)) >= 4.5, `${foreground}/${background}`)
    assert.ok(contrast(resolve('action-text'), resolve('action-bg')) >= 7)
  }
})
