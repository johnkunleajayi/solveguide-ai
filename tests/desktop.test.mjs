import assert from 'node:assert/strict'
import test from 'node:test'
import { desktopFixture } from './helpers/desktop.mjs'

test('redesigned workspace preserves explicit action order and a single current workflow step', () => {
  const html = desktopFixture()
  assert.ok(html.indexOf('Read Question') < html.indexOf('Get Suggested Answer'))
  assert.equal((html.match(/aria-current="step"/g) ?? []).length, 1)
  assert.match(html, /aria-label="Learning workflow"/)
  assert.match(html, /aria-label="Visible answer options"/)
  assert.match(html, /aria-label="Recommended options"/)
})
test('materials disclosure leaves modes visible and includes explicit consent and readiness controls', () => {
  const html = desktopFixture('consent')
  assert.ok(html.indexOf('Reasoning mode') < html.indexOf('<details class="reasoning-materials"'))
  assert.match(html, /<summary>Reference documents &amp; permissions · 1 selected<\/summary>/)
  assert.match(html, /Refresh readiness/)
  assert.match(html, /I allow selected relevant passages/)
  assert.match(html, /I allow OpenAI to receive the document text/)
  assert.doesNotMatch(html, /class="reasoning-consent"><input[^>]*checked/)
})
test('source inspection and insufficient-evidence states remain honest', () => {
  const answered = desktopFixture()
  assert.match(answered, /data-status="answered"/)
  assert.match(answered, /Practice automation reference · Page 2/)
  assert.match(answered, /Open source document/)
  const insufficient = desktopFixture('insufficient')
  assert.match(insufficient, /data-status="insufficient_information"/)
  assert.match(insufficient, /Insufficient document evidence/)
  assert.doesNotMatch(insufficient, /aria-label="Recommended options"|Answer confidence ·/)
})
test('sign-in presentation keeps the learning workspace gated', () => {
  const html = desktopFixture('auth')
  assert.match(html, /Sign in with Google/)
  assert.match(html, /SolveGuide/)
  assert.doesNotMatch(html, /id="workspace-title"|reasoning-controls|Get Suggested Answer/)
})
test('library, capture and settings retain labelled controls and privacy status', () => {
  assert.match(desktopFixture('library'), /aria-label="Extracted document text"/)
  const capture = desktopFixture('capture')
  assert.match(capture, /aria-label="Practice question/)
  assert.match(capture, /disabled=""[^>]*>Capture window/)
  const settings = desktopFixture('settings')
  assert.match(settings, /data-state="enabled"/)
  assert.match(settings, /Screen-share privacy/)
  assert.match(settings, /Pointer light/)
  assert.match(settings, /value="system"/)
})

test('empty, reading and retry states keep actions explicit and expose status text', () => {
  assert.match(desktopFixture('empty'), /No capture selected/)
  const reading = desktopFixture('loading')
  assert.match(reading, /Cancel reading/)
  assert.doesNotMatch(reading, /aria-label="Recommended options"/)
  const error = desktopFixture('error')
  assert.match(error, /role="alert"/)
  assert.match(error, /Try Again/)
})
