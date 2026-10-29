# SolveGuide AI brand foundation v1 — Stage 11A

This specification covers the existing Windows desktop product and its future
public website. It does not create a browser learning application, a new product
name or a final logo. The existing SolveGuide wordmark/mark remains unchanged.

## Direction and audit

Intelligent, precise and memorable: charcoal and white establish clarity; mint
marks intent; green adds energy; sage gives supporting information restraint.
The conceptual references were [Neon](https://neon.com) and
[MNTN](https://mountain.com): confident typography, generous space and controlled
luminous/product imagery. No assets, layouts, font combinations or source were copied.

The desktop already had useful spacing, type, motion and accessibility primitives.
Dark/light colour roles were duplicated and predominantly monochrome. Stage 11A
centralizes those roles and introduces the approved palette through a compatibility
bridge. It preserves application component structure, layout metrics, authentication,
capture, RAG, privacy and Pointer Light behavior. Full component redesign is Stage 11B.

## Source of truth

`brand/tokens.css` is framework-independent CSS with the `--sg-` namespace. It has
no runtime dependencies, assets or font downloads. Layers are:

1. Foundation primitives: exact palette, fonts, type/spacing/radius/motion scales.
2. Semantic roles: canvas, surfaces, text, action, focus, border, status and effects.
3. Desktop bridge: `src/styles/tokens.css` aliases existing component tokens to
   these roles. Desktop-only layout metrics and cursor assets stay in that bridge.

Use semantic roles in components, not raw swatch values. A future Next.js website
may import this CSS into its global stylesheet without importing desktop JavaScript,
Tauri, auth or Vite configuration. Do not create website tooling during Stage 11A.

| Foundation | Exact value | Purpose |
| --- | --- | --- |
| Deep Charcoal | `#0B0E0D` | Signature canvas / ink |
| Pure White | `#FFFFFF` | Primary dark text / light surface |
| Luminous Mint | `#A3FFCF` | Primary fill, selected highlights |
| Vibrant Green | `#55E6A5` | Hover fill, restrained gradient endpoint |
| Muted Sage | `#9AADA1` | Dark supporting text / visual balance |

## Themes and contrast

Dark is charcoal with opaque green-neutral surfaces (`#101812`, `#17221C`), white
text, silver-sage secondary text and mint focus/action emphasis. Light is off-white
(`#F6F9F7`) with white surfaces, charcoal ink, darker green (`#176044`, `#105637`)
for readable accent text and restrained neutral-green shadows. It is not an inversion.

The desktop keeps its persisted Light/Dark/System preference and OS resolution.
Shared CSS follows `:root[data-theme="light"]`; dark is the root default. A scoped
specimen can use `[data-sg-theme="dark"|"light"]` without changing application prefs.

Mint, vibrant green and raw sage must not be used as body text on white. Use the
theme's `--sg-accent`, `--sg-text-secondary` and `--sg-text-muted` roles. Brand tests
require 4.5:1 for text/status roles on core surfaces, 7:1 for primary action text,
and 3:1 for focus/control boundaries. Gradient stops are checked individually.
Subtle decorative separators do not replace visible input/control boundaries.
Disabled controls use explicit disabled roles and native disabled semantics.
Statuses combine words/icons with colour: gold/rose are restricted warning/error
signals, not competing signature accents. Never imply AI correctness through green alone.

## Typography and hierarchy

Use local Segoe UI Variable Display/Text, Segoe UI and system sans fallbacks.
Technical information uses Cascadia Code/Consolas/system monospace. No remote fonts.

| Role | Scale | Treatment |
| --- | --- | --- |
| Marketing headline | 40–88px fluid | 600 weight, 1.05 leading, -0.045em tracking |
| Application display | 44–72px fluid | Short, confident phrases |
| Title / section | 28px / 20px | 600 weight, clear heading structure |
| Body / compact app | 16px / 14px | 400 weight, 1.7 body leading |
| Label / metadata | 12px | Restrained uppercase, 0.12em tracking |
| Technical | 13–14px specimen | Preserve readable code/source structure |

Use one prominent headline and a clear action hierarchy. Keep body lines around
60–70 characters. Avoid all-uppercase body copy. Existing smaller desktop metadata
is retained for stability and needs a component-by-component Stage 11B readability
review; this foundation is not a complete WCAG audit of the application.

## Space, surfaces and interaction

The spacing scale is 4/8/12/16/20/24/32/40/48/64px. Radii are 6/10/16/22px plus
pill. Use 16px for substantial cards and 10px for controls. Avoid nested boxes and
excessive translucency. Elevation should come from hierarchy, opaque surfaces,
subtle borders and restrained shadows rather than continuous glow.

Primary actions use mint with charcoal labels; hover uses vibrant green.
Secondary controls use transparent/neutral surfaces and readable control borders.
Navigation uses a quiet active surface and accent text, plus semantic current state.
Keep visible 2px focus rings with 4px offset and at least 44px control targets in
new specimens. Hover must not be the only indicator of function. Preserve native
selection, keyboard operation, labels and disabled semantics.

Use `--sg-gradient-text` only on selected display words. Dark blends white/mint/green;
light blends charcoal/darker greens. Never apply transparent gradient text to body
copy or make glow necessary for readability. Use `--sg-gradient-surface` and
`--sg-glow-action` sparingly, with one dominant luminous moment per composition.

Motion tokens: press 110ms, hover 180ms, theme 260ms, reveal 680ms with restrained
ease-out/cinematic curves. No mandatory ambient loops or animated text sweeps.
The showcase disables transitions/transforms for reduced motion and restores
system text/focus/border colours in forced-colours mode. Preserve desktop motion
and Pointer Light accessibility fallbacks; this showcase does not mount Pointer Light.

## Development showcase

From `D:\solveguide-ai`, run `npm.cmd run dev`, then open
`http://127.0.0.1:1420/brand.html`. If the desktop dev server is already running,
use that same URL instead of starting a second server.

`brand.html` is an independent Vite development entry; `src/brand/main.tsx` is
guarded by `import.meta.env.DEV`. It is not linked from application navigation or
included in the standard production build inputs. Its theme switch affects only
the showcase, does not read/write appearance storage and has no System option.
The real desktop retains all three modes. Controls are labelled demonstration
specimens and make no account, capture, document or provider requests.

Inspect both themes, Tab focus/skip link, button feedback, navigation selection,
input focus/text selection and disabled states. Resize through desktop and compact
widths. Responsive grids collapse without changing production workspace layout.

Validation: `npm.cmd run test:interaction`, `npm.cmd run lint`,
`npm.cmd run typecheck`, `npm.cmd run build`. `tests/brand.test.mjs` covers palette,
role contrast, gradient stops, semantic specimens and entry-point isolation.
Automated contrast checks complement visual review; they do not certify every
composited pixel, font rendering or legacy component.

### Stage 11A verification record

Frontend: 114 tests pass (10 brand checks plus the existing 104), ESLint, TypeScript
and production build pass. Production output contains neither `brand.html` nor the
showcase component/styles. Backend regression: 186 passed, two optional PostgreSQL
checks skipped; Ruff passes. Two existing FastAPI/Starlette and Authlib HTTPX
deprecation warnings remain. Native regression: formatting, check, Clippy with
warnings denied and 21 Rust tests pass. Vite watcher exclusions are unchanged.

Browser inspection covered dark/light, sample action feedback, Tab focus (2px),
skip navigation, and no horizontal overflow at 640×640, 1280×800 and 1440×900.
No showcase console warnings/errors were recorded. Reduced-motion/forced-colour
rules have static regression coverage; actual OS-mode rendering remains for manual
review. The native window launched, but its enabled screen-share privacy prevents
reliable screenshot inspection. No privacy setting was changed and no Google login
or paid provider request was performed. Signed-in native workflows remain a manual
visual/regression check before approving Stage 11A.

## Desktop refinement and next stage

Stage 11B now refines metadata, semantic control/status roles and desktop hierarchy;
see [DESKTOP.md](DESKTOP.md) for implementation scope and remaining visual acceptance
checks. Real signed-in capture/library/citation flows require manual review while
preserving all functional contracts and screen-share privacy.

Stage 11C: build the separate public website only after approval. Reuse tokens and
brand rules with independently designed marketing layouts and original product
imagery. Keep desktop business logic, credentials and Tauri dependencies out of it.
