# Handoff: Repuro Suite Landing Page Redesign

## Objective
Redesign the landing page at `repuro-suite.fly.dev/` to look modern and align with Repuro CI. Current page is functional but visually bare — dark background, three plain cards, no logo, no visual identity.

## Current state
**File:** `CLAUDE_REPURO/suite/static/index.html` (single self-contained HTML file, inline CSS, no external dependencies)

Current design:
- Dark background (`#0f2832`), centered column, 480px max-width
- Title "Repuro Suite" in `#0891B2`, subtitle "Internal tools" in slate
- Three link cards (dark teal `#1a3a4a`, 1px border, 10px radius) pointing to `/allex/`, `/deals/`, `/cockpit/`
- Footer: "Repuro Capital Partners" in 11px slate
- Font: Aptos Narrow / Arial fallback
- No logo, no visual hierarchy beyond title + cards, no hover animations beyond border color change

## What it should become
A modern, polished internal tool landing page that:
- Feels like a real product, not a prototype
- Uses Repuro brand colors, logo, and typography correctly
- Has visual weight and hierarchy — the page should feel intentional
- Stays a single HTML file (no build step, no external CSS files)
- Remains fast and lightweight — no heavy frameworks or images beyond the logo

## Repuro CI — design tokens

### Colors
| Role | Hex | Usage |
|------|-----|-------|
| Primary brand | `#0891B2` | Headers, primary actions, brand anchor |
| Accent 1 | `#22D3EE` | Lighter cyan, hover states, gradients |
| Accent 2 | `#8DE8F6` | Light variant, subtle highlights |
| Signal red | `#E11D48` | Alerts only, use sparingly |
| Warning amber | `#EAB308` | Highlights |
| Purple | `#A855F7` | Accent |

### Typography
- **Web/UI:** Arial (not Aptos Narrow — that's Excel-only)
- Size hierarchy: title large + bold, body 13-14px, descriptions smaller

### Logo
- Files at `CLAUDE_COWORK/REPURO/Corporate Identity/`
- For dark backgrounds: use `whitewithname.png` (white icon + "Repuro" wordmark)
- For light backgrounds: use `colorwithname_whitebg.png`
- Never place color logo on similarly saturated background

### Brand voice (reflected in copy)
- "Internal tools" subtitle is fine but could be sharper
- Card descriptions are good — concise, specific, no fluff
- Footer "Repuro Capital Partners" is the formal entity name — keep it

## Architecture constraints
- **Single file:** `suite/static/index.html` — Caddy serves this directory for `/`
- **No build step:** deployed via `fly deploy` from the suite directory
- **Three routes:** `/allex/`, `/deals/`, `/cockpit/` — card hrefs must stay the same
- **Auth is handled by Caddy** (basic auth on allex/deals, bearer on cockpit) — landing page is public-facing within the Fly.io network
- **Logo embedding:** either base64-inline the logo PNG into the HTML, or copy a logo file into `suite/static/` and reference it (file does not exist yet — must be created)

## Design direction ideas (not prescriptive)
- Consider a subtle gradient or glassmorphism on cards
- Could add subtle icons per tool (pipeline, handshake/deals, dashboard)
- A frosted-glass or subtle backdrop effect behind the card area
- Micro-animations on hover (scale, glow, shadow lift)
- The logo should anchor the top — wordmark variant, sized appropriately
- Consider a subtle background pattern or gradient instead of flat dark color
- The three cards could benefit from more visual differentiation (icon, accent color per tool)

## What NOT to do
- Don't add a framework (React, Tailwind CDN, etc.) — vanilla HTML/CSS only
- Don't add navigation or a header bar — this IS the home page, the tools have their own nav
- Don't make it look like a SaaS marketing page — this is an internal tool suite
- Don't add animations that slow perceived load time
- Don't change the card hrefs or the three-tool structure

## Deployment
After editing `suite/static/index.html`:
1. Use `/deploy-suite` skill or manual `fly deploy` from the suite directory
2. Verify at `repuro-suite.fly.dev/`

## Files to read before starting
1. `CLAUDE_REPURO/suite/static/index.html` — the file to redesign
2. `CLAUDE_REPURO/context/repuro-ci.md` — full CI spec
3. `CLAUDE_COWORK/REPURO/Corporate Identity/` — logo files (use `whitewithname.png` for dark bg)
