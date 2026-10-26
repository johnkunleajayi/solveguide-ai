import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const source = readFileSync(new URL('../src/components/PointerLight.tsx', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText

class Events {
  listeners = new Map()
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set())
    this.listeners.get(name).add(callback)
  }
  removeEventListener(name, callback) { this.listeners.get(name)?.delete(callback) }
  emit(name, event = {}) { for (const callback of this.listeners.get(name) ?? []) callback(event) }
  count() { return [...this.listeners.values()].reduce((sum, set) => sum + set.size, 0) }
}

class ElementDouble {
  dataset = {}
  properties = new Map()
  style = {
    setProperty: (name, value) => this.properties.set(name, value),
    removeProperty: name => this.properties.delete(name),
  }
  constructor({ interactive = false, surface = null } = {}) {
    this.interactive = interactive
    this.surface = surface
  }
  closest(selector) {
    if (selector === '.app-shell') return this
    if (selector === '[data-spotlight]') return this.surface
    return this.interactive ? this : null
  }
  getBoundingClientRect() { return { left: 10, top: 20 } }
}

function mount({ enabled = true, fine = true, reduced = false, contrast = false } = {}) {
  const light = new ElementDouble()
  const root = new ElementDouble()
  const document = new Events()
  document.documentElement = root
  const window = new Events()
  const media = new Map([
    ['(hover: hover) and (pointer: fine)', Object.assign(new Events(), { matches: fine })],
    ['(prefers-reduced-motion: reduce)', Object.assign(new Events(), { matches: reduced })],
    ['(forced-colors: active)', Object.assign(new Events(), { matches: contrast })],
  ])
  window.matchMedia = query => media.get(query)
  const frames = new Map()
  let frameId = 0
  let hookCalls = 0
  let effect
  const react = {
    useRef: () => { hookCalls++; return { current: light } },
    useEffect: callback => { hookCalls++; effect = callback },
  }
  const module = { exports: {} }
  const evaluate = new Function('require', 'module', 'exports', 'window', 'document', 'Element', 'requestAnimationFrame', 'cancelAnimationFrame', compiled)
  evaluate(name => name === 'react' ? react : require(name), module, module.exports,
    window, document, ElementDouble,
    callback => { frames.set(++frameId, callback); return frameId },
    id => frames.delete(id))
  module.exports.PointerLight({ enabled })
  const unmount = effect()
  const move = (target, x = 100, y = 80, extra = {}) => document.emit('pointermove', {
    target, clientX: x, clientY: y, pointerType: 'mouse', isPrimary: true, ...extra,
  })
  let time = 0
  const tick = () => {
    time += 16
    const pending = [...frames.values()]
    frames.clear()
    for (const callback of pending) callback(time)
  }
  const setMedia = (query, value) => { const item = media.get(query); item.matches = value; item.emit('change') }
  return { light, root, document, window, frames, media, move, tick, setMedia, unmount, hookCalls: () => hookCalls }
}

test('fine pointer follows with transforms, lights only its surface, and settles without React updates', () => {
  const app = mount()
  const surface = new ElementDouble()
  const target = new ElementDouble({ surface })
  assert.equal(app.root.dataset.pointerEnhanced, 'true')
  app.move(target)
  app.tick()
  assert.match(app.light.style.transform, /translate3d\(100px,80px,0\)/)
  assert.equal(surface.properties.get('--spot-x'), '90px')
  app.move(target, 220, 160)
  app.tick()
  assert.notEqual(app.light.style.transform, 'translate3d(220px,160px,0)')
  for (let i = 0; i < 80; i++) app.tick()
  assert.equal(app.frames.size, 0)
  assert.equal(app.hookCalls(), 2)
  app.unmount()
  assert.equal(surface.dataset.lit, undefined)
})

test('interactive hover and primary press/release provide bounded feedback', () => {
  const app = mount()
  app.move(new ElementDouble({ interactive: true }))
  assert.equal(app.light.dataset.interactive, 'true')
  app.document.emit('pointerdown', { pointerType: 'mouse', button: 0 })
  assert.equal(app.light.dataset.pressed, 'true')
  app.document.emit('pointerup')
  assert.equal(app.light.dataset.pressed, 'false')
  app.unmount()
})

test('a text drag stays unobstructed until pointer release', () => {
  const app = mount()
  const text = new ElementDouble()
  app.move(text)
  app.document.emit('pointerdown', { pointerType: 'mouse', button: 0 })
  app.move(text, 110)
  app.move(text, 130)
  assert.equal(app.light.dataset.visible, 'false')
  assert.equal(app.frames.size, 0)
  app.document.emit('pointerup')
  app.move(text, 150)
  assert.equal(app.light.dataset.visible, 'true')
  app.unmount()
})

for (const [name, options] of [
  ['preference off (including native-dialog suspension)', { enabled: false }],
  ['coarse pointer', { fine: false }],
  ['reduced motion', { reduced: true }],
  ['forced colors', { contrast: true }],
]) {
  test(name + ' retains native cursor eligibility and schedules no animation', () => {
    const app = mount(options)
    app.move(new ElementDouble())
    assert.equal(app.root.dataset.pointerEnhanced, undefined)
    assert.equal(app.frames.size, 0)
    assert.equal(app.light.dataset.visible, 'false')
    app.unmount()
  })
}

test('live motion and pointer changes cancel effects and can re-enable them', () => {
  const app = mount()
  const target = new ElementDouble()
  app.move(target)
  app.setMedia('(prefers-reduced-motion: reduce)', true)
  assert.equal(app.frames.size, 0)
  assert.equal(app.root.dataset.pointerEnhanced, undefined)
  app.setMedia('(prefers-reduced-motion: reduce)', false)
  assert.equal(app.root.dataset.pointerEnhanced, 'true')
  app.move(target, 40, 30, { pointerType: 'touch' })
  assert.equal(app.light.dataset.visible, 'false')
  app.setMedia('(hover: hover) and (pointer: fine)', false)
  assert.equal(app.root.dataset.pointerEnhanced, undefined)
  app.unmount()
})

test('keyboard, blur, scrolling and cleanup hide light and release all listeners/frames', () => {
  const app = mount()
  const target = new ElementDouble()
  for (const [events, name, event] of [
    [app.document, 'keydown', { key: 'Tab' }],
    [app.document, 'scroll', {}],
    [app.window, 'blur', {}],
    [app.window, 'resize', {}],
    [app.document, 'pointercancel', {}],
    [app.document, 'pointerout', { relatedTarget: null }],
  ]) {
    app.move(target)
    events.emit(name, event)
    assert.equal(app.light.dataset.visible, 'false')
    assert.equal(app.frames.size, 0)
  }
  app.unmount()
  assert.equal(app.document.count() + app.window.count(), 0)
  for (const media of app.media.values()) assert.equal(media.count(), 0)
  assert.equal(app.root.dataset.pointerEnhanced, undefined)
})
