# SolveGuide AI public website — Milestone 11C

An independent Next.js App Router / strict TypeScript / Tailwind public information
website. The SolveGuide learning product remains the authenticated Windows desktop
application. This site has no sign-in, AI/backend integration, document upload,
waitlist, email collection, analytics, billing or installer download.

## Structure and boundaries

```text
website/
  app/                 Server-rendered pages, layout, metadata and global styles
    features/          Implemented desktop capabilities and current boundaries
    how-it-works/      The six explicit desktop workflow steps
    privacy/           Product architecture overview, not a legal policy
    download/          Coming Soon; disabled installer action
    robots.ts          Preview-safe crawl configuration
    sitemap.ts         Five canonical public pages when SITE_URL is configured
  components/          Shared shell, brand, theme/menu controls, UI illustrations
  lib/                 Public content, metadata/origin validation, theme bootstrap
  public/              Local icon and 1200×630 PNG social card (plus SVG source)
  tests/               Offline rendering, theme, messaging and boundary tests
  package*.json        Website-only dependencies and lockfile
```

Pages and product illustrations are React Server Components. Only the theme
selector and mobile menu need client components. Illustrations use original HTML/CSS
and fictional practice content, explicitly labelled as illustrations rather than
captured product screenshots. They do not simulate an operational learning app.
The existing approved mark is reused; no new final logo is introduced.

`app/globals.css` imports `../../brand/tokens.css` directly. This is the only shared
source dependency: no desktop React/Tauri code, backend module or private configuration
is imported. System font stacks need no runtime font download. Tailwind scans this
website directory; the root ESLint configuration excludes it so each project uses
its own rules/dependencies. Root Vite watcher exclusions are unchanged.

## Local development

Use the canonical checkout; do not copy the project. Node.js 24 was used for validation.
From PowerShell:

```powershell
cd D:\solveguide-ai\website
$env:NEXT_TELEMETRY_DISABLED='1'
$env:TEMP='D:\solveguide-ai\.cache\tmp'
$env:TMP=$env:TEMP
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. This does not start the desktop or FastAPI.
The local `.npmrc` keeps npm cache/logs under `D:\solveguide-ai\.cache\npm`.
Next output stays in `website/.next`; both dependency/build folders are ignored.
Stop a foreground server with Ctrl+C before starting another on port 3000.

Production preview:

```powershell
npm.cmd run build
npm.cmd run start
```

Validation:

```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

Webpack is explicitly selected for consistent shared-CSS resolution in development
and production. No monorepo tooling or root dependency changes are required.
The checked-in website lockfile pins dependencies separately from the desktop.
ESLint 9 is required by several installed Next lint plugins; its upstream
deprecation warning is known. Do not force ESLint 10 past incompatible peer ranges.
The optional unrs-resolver installation script may be blocked by npm's local script
policy; successful lint validation does not require relaxing that policy.

## Theme, accessibility and performance

Charcoal/white foundations use mint/green selectively. Light mode uses darker green
foregrounds and off-white surfaces from the shared semantic roles. The independent
website preference key is `solveguide-website-theme`; it has no authentication data
and does not change desktop preferences. A pre-paint bootstrap resolves Light/Dark/
System before rendering, with storage failure fallback. The hydrated selector has
stable server markup and System listens for OS appearance changes.

Semantic landmarks, one page h1, a skip link, visible focus rings, native select/
details controls, Escape menu dismissal, descriptive illustration labels, responsive
reflow, reduced-motion and forced-colour rules are included. Without JavaScript,
content/navigation still work; the non-operational theme selector is hidden.
Entrance motion and CSS scroll motion are restrained, with no animation library.
No stock photography or third-party runtime asset service is used.

## SEO configuration

No environment variable or secret is required for local preview. The optional,
server/build-only `SITE_URL` must be the verified public HTTPS origin (no path,
credentials, query or fragment). Example configuration is in `.env.example`.
Do not use a fabricated production domain or configure desktop/backend secrets here.

Without `SITE_URL`, pages and robots discourage indexing, sitemap is empty and
metadata uses a localhost preview base. Before a real public production build, set
the actual verified origin to generate canonical URLs, Open Graph URLs and sitemap.
Leave it unset for private previews. All pages have descriptive metadata and the
local PNG social image; social-platform rendering still needs deployment-time review.

## Vercel deployment preparation — do not deploy during this milestone

When deployment is separately authorized:

1. Use a dedicated Vercel **Next.js** project with Root Directory **`website`**.
2. Enable **Include source files outside of the Root Directory in the Build Step**
   so `../brand/tokens.css` is available. See the
   [official monorepo FAQ](https://vercel.com/docs/monorepos/monorepo-faq).
3. Use the website lockfile and install command `npm ci`; build with `npm run build`.
   Keep Next.js output defaults. `next.config.ts` permits tracing shared source from
   the parent repository; it does not import or deploy the desktop/backend.
4. Use a supported Node version compatible with the package engines and verify
   against the locally tested Node 24 environment.
5. Configure `SITE_URL` for the verified production origin, and disable Next CLI
   telemetry with `NEXT_TELEMETRY_DISABLED=1`. No API, Google or database keys belong
   in this Vercel project. Keep real `.env` files ignored and out of source uploads.
6. Run the validation commands and review all five pages in dark/light/System at
   375, 768, 1024, 1440 and 1920px, including mobile menu, keyboard focus, reduced
   motion, social previews, robots and sitemap before publishing.

Vercel deployment has not been performed or verified. The Windows release remains
Coming Soon until a signed installer and independently verified release URL exist.
Adding that release is separate work; never link development binaries here.

## Product messaging boundaries

Capture, Read Question and Get Suggested Answer are explicit desktop actions.
General ignores documents; Context Guided uses selected evidence with labelled
general reasoning; Materials Only can abstain. Questions/answers/captures remain
ephemeral in SolveGuide, while explicitly added library documents and their derived
index data persist. Hosted document indexing/grounded reasoning transmit text after
consent. Provider retention guarantees, certifications and legal claims are not made.
Screen-share privacy uses supported Windows capture exclusion; it is not guaranteed
invisibility. No Live Question Monitor, automatic detection, automatic answers,
floating panels or Session Preparation are presented as available capabilities.

## Milestone 11C validation record

- Website: 11 offline tests, ESLint and strict TypeScript checks pass. Next.js
  production generation succeeds for all five pages, not-found, robots and sitemap.
- Local production HTTP: all five pages, robots, sitemap and the PNG social card
  respond with HTTP 200. Public download remains a disabled unavailable action.
- Browser: all five pages in dark and light themes at 375, 768, 1024, 1440 and
  1920px passed horizontal-overflow checks (50 combinations). Representative mobile,
  tablet and desktop compositions were inspected. Mobile menu opens and Escape
  closes it with focus restored; keyboard focus has a 2px ring. System resolves to
  the OS and persists after reload. No browser warnings/errors were recorded.
- Shared dark/light foreground roles meet the tested 4.5:1 body-text and 7:1
  primary-action contrast thresholds. JSX accessibility lint also passes.
- Existing desktop: 120 tests and production build pass. Preservation checks match
  the pre-11C desktop/backend/native diff and all shared brand-file hashes.
- Production dependency audit reports zero known vulnerabilities. ESLint's upstream
  deprecation and npm's optional resolver-script notice remain tooling warnings;
  ESLint 10 is not used because several Next plugins exclude it from peer support.

OS-level reduced-motion/high-contrast rendering, a full screen-reader audit, physical
touch devices, quantitative Lighthouse/Core Web Vitals scores, social-platform link
previews and a real Vercel deployment remain unverified. Reduced-motion/forced-colour
CSS is present and regression-checked; these tests are not complete WCAG certification.
No native capture protection was changed to produce website illustrations or previews.
