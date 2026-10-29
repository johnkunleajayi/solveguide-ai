import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import ts from 'typescript'
const require = createRequire(import.meta.url)
const React = require('react')
const { renderToStaticMarkup: render } = require('react-dom/server')
function compile(path, dependencies = {}) {
  const output = ts.transpileModule(readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(id => dependencies[id] ?? require(id), module, module.exports)
  return module.exports
}
const css = readFileSync(new URL('../brand/tokens.css', import.meta.url), 'utf8')
const blocks = [...css.matchAll(/([^{}]+)\{([^{}]+)\}/g)]
const declarations = block => Object.fromEntries([...block.matchAll(/(--sg-[\w-]+):\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()]))
const primitive = declarations(blocks[0][2])
const themes = { dark: { ...primitive, ...declarations(blocks[1][2]) }, light: { ...primitive, ...declarations(blocks[2][2]) } }
function resolve(theme, name) {
  let value = theme[`--sg-${name}`]
  for (let i = 0; i < 8 && value?.startsWith('var('); i++) value = theme[value.slice(4, -1)]
  assert.ok(value, `Token ${name} must resolve`)
  return value
}
function luminance(hex) {
  assert.match(hex, /^#[0-9a-f]{6}$/i)
  const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4)
  return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]
}
function contrast(a, b) { const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (light + .05) / (dark + .05) }

test('approved foundation colours remain exact and framework-independent', () => {
  assert.deepEqual(['charcoal', 'white', 'mint', 'green', 'sage'].map(name => resolve(primitive, `color-${name}`)), ['#0B0E0D', '#FFFFFF', '#A3FFCF', '#55E6A5', '#9AADA1'])
  assert.doesNotMatch(css, /url\(|@import|@tailwind/)
})
for (const [name, theme] of Object.entries(themes)) {
  test(`${name} readable text and semantic statuses meet 4.5:1 across core surfaces`, () => {
    for (const foreground of ['text', 'text-secondary', 'text-muted', 'accent', 'success', 'warning', 'danger', 'info']) {
      for (const background of ['canvas', 'surface', 'surface-raised', 'surface-hover']) {
        const ratio = contrast(resolve(theme, foreground), resolve(theme, background))
        assert.ok(ratio >= 4.5, `${name} ${foreground}/${background}: ${ratio.toFixed(2)}:1`)
      }
    }
  })
  test(`${name} primary actions, selection, focus and control boundaries preserve contrast`, () => {
    for (const background of ['action-bg', 'action-hover']) assert.ok(contrast(resolve(theme, 'action-text'), resolve(theme, background)) >= 7)
    assert.ok(contrast(resolve(theme, 'selection-text'), resolve(theme, 'selection-bg')) >= 4.5)
    for (const background of ['canvas', 'surface', 'surface-raised']) {
      assert.ok(contrast(resolve(theme, 'focus'), resolve(theme, background)) >= 3)
      assert.ok(contrast(resolve(theme, 'border-control'), resolve(theme, background)) >= 3)
    }
  })
  test(`${name} gradient headline stops meet 4.5:1 without relying on glow`, () => {
    for (const stop of resolve(theme, 'gradient-text').match(/#[\da-f]{6}/gi)) {
      for (const background of ['canvas', 'surface']) assert.ok(contrast(stop, resolve(theme, background)) >= 4.5)
    }
  })
}
const { BrandShowcase } = compile('brand/BrandShowcase.tsx', { '../components/Brand': compile('components/Brand.tsx') })
test('both showcase themes expose labelled semantic specimens and honest demo-only copy', () => {
  for (const theme of ['dark', 'light']) {
    const html = render(React.createElement(BrandShowcase, { initialTheme: theme }))
    assert.match(html, new RegExp(`data-sg-theme="${theme}"`))
    assert.match(html, /SolveGuide/); assert.match(html, /no question or answer is being processed/)
    assert.match(html, /No account, capture or provider requests/)
    assert.match(html, /aria-label="Navigation specimen"/); assert.match(html, /role="status"/)
    assert.match(html, /for="brand-reference-title"/); assert.match(html, /disabled/)
    assert.match(html, /#A3FFCF/); assert.match(html, /Understand the question. Find the answer. Learn why./)
  }
})
test('showcase is separate from production workflows and appearance storage', () => {
  const entry = readFileSync(new URL('../src/brand/main.tsx', import.meta.url), 'utf8')
  const showcase = readFileSync(new URL('../src/brand/BrandShowcase.tsx', import.meta.url), 'utf8')
  const main = readFileSync(new URL('../src/main.tsx', import.meta.url), 'utf8')
  assert.match(entry, /import\.meta\.env\.DEV/)
  assert.doesNotMatch(entry + showcase, /from ['"].*(auth|capture|rag|vision|answer|api\/core)|localStorage|sessionStorage|fetch\(|invoke\(/)
  assert.doesNotMatch(main, /BrandShowcase|brand\/main/)
})

test('showcase preserves reduced-motion, forced-colour and visible-focus fallbacks', () => {
  const styles = readFileSync(new URL('../src/brand/showcase.css', import.meta.url), 'utf8')
  assert.match(styles, /prefers-reduced-motion: reduce/)
  assert.match(styles, /transition: none !important/)
  assert.match(styles, /forced-colors: active/)
  assert.match(styles, /-webkit-text-fill-color: CanvasText/)
  assert.match(styles, /:focus-visible/)
  assert.match(styles, /min-height: 44px/)
})
