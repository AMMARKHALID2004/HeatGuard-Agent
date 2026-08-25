# HeatGuard Agent — Visual Design System

## Mode
**Operate** — this is a decision tool used by construction supervisors on-site before shifts. Scanability, authority, and field legibility outrank expression.

## Brand Position
Name: HeatGuard Agent. Voice: precise, authoritative, calm — a tool that makes the call so the human doesn't have to guess. No marketing fluff.

## Color Palette (Dark Theme)

### Base
- **Background (deep ink)**: `#05080C` / `oklch(0.08 0.02 240)` — near-black with subtle blue undertone
- **Surface (panel)**: `#0B121A` / `oklch(0.12 0.02 240)` — elevated panels
- **Surface-hover**: `#111A26` / `oklch(0.16 0.02 240)`
- **Border**: `#1A2533` / `oklch(0.22 0.03 240)`
- **Border-strong**: `#243346` / `oklch(0.28 0.04 240)`

### Text
- **Text-primary**: `#F0F3F7` / `oklch(0.94 0.01 240)` — near-white, not pure
- **Text-secondary**: `#8B99A9` / `oklch(0.65 0.02 240)`
- **Text-muted**: `#5A6A7A` / `oklch(0.48 0.03 240)`

### Accent — Ember (Decision Authority)
- **Ember-500 (primary)**: `#E87A1E` / `oklch(0.62 0.18 55)` — the "amber event marker"
- **Ember-400 (lighter)**: `#F09640` / `oklch(0.72 0.16 55)`
- **Ember-600 (darker)**: `#D06618` / `oklch(0.54 0.17 55)`
- **Ember-glow**: `rgba(232, 122, 30, 0.35)` — for focus rings, subtle glows

### Decision Colors (semantic, derived from risk)
- **PROCEED (cool blue-gray)**: `#5BA4E0` / `oklch(0.68 0.12 250)` — authoritative, not "success green"
- **PROCEED-surface**: `rgba(91, 164, 224, 0.12)`
- **PROCEED-border**: `rgba(91, 164, 224, 0.35)`
- **MODIFY (ember)**: `#E87A1E` / `oklch(0.62 0.18 55)` — the amber accent
- **MODIFY-surface**: `rgba(232, 122, 30, 0.12)`
- **MODIFY-border**: `rgba(232, 122, 30, 0.35)`
- **RESCHEDULE (deep crimson)**: `#C0392B` / `oklch(0.52 0.22 25)` — authoritative alarm, not bright red
- **RESCHEDULE-surface**: `rgba(192, 57, 43, 0.12)`
- **RESCHEDULE-border**: `rgba(192, 57, 43, 0.35)`

### Map
- **CARTO dark tiles** — unchanged
- **AOI ring**: decision-color at 2px, fill at 15% opacity
- **Threshold legend dots**: use decision colors

## Typography Stack

### Display Font — **Space Grotesk Variable** (wght 300-700)
- Used for: Decision badge (hero scale), page title, major numbers (peak/avg temp)
- Load via `@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300..700&display=swap')`
- Variable weight axis: decision word weight tracks confidence (Regular→Medium→SemiBold→Bold)

### UI Sans — **IBM Plex Sans** (400, 500, 600)
- Used for: All labels, body copy, recommendation, reasoning, UI text
- Load via `@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap')`
- Excellent legibility at small sizes, distinctive but not decorative

### Monospace — **JetBrains Mono Variable** (wght 400-700)
- Used for: Temperature readouts, coordinates, timestamps, code-like data
- Load via `@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400..700&display=swap')`
- Tabular numerals (`font-variant-numeric: tabular-nums`)

### Scale (fluid, clamp-based)
- **Display-xl** (decision badge): `clamp(3rem, 8vw, 5.5rem)` / line-height 1.05
- **Display-lg** (page title): `clamp(1.75rem, 4vw, 2.5rem)` / line-height 1.15
- **Display-md** (temp numbers): `clamp(1.75rem, 3.5vw, 2.25rem)` / line-height 1.1
- **Heading-sm** (section labels): `0.7rem` uppercase, tracking-widest (0.15em)
- **Body-lg** (recommendation): `1rem` / line-height 1.6
- **Body** (reasoning): `0.9375rem` / line-height 1.65
- **Label** (UI labels): `0.75rem` / line-height 1.5
- **Caption** (metadata): `0.7rem` / line-height 1.5
- **Mono-sm** (temps small): `0.875rem` tabular-nums

## Spacing Scale (generous, field-ready)
Base unit: 4px. Scale uses 1.5x rhythm for vertical, 1.25x for horizontal.

| Token | Value | Use |
|-------|-------|-----|
| space-1 | 4px | Tight inline gaps |
| space-2 | 6px | Icon-text, badge gaps |
| space-3 | 8px | Card padding (small) |
| space-4 | 12px | Standard card padding |
| space-5 | 16px | Section gaps, panel gaps |
| space-6 | 24px | Major section separation |
| space-7 | 36px | Page-level vertical rhythm |
| space-8 | 48px | Hero gaps |
| space-9 | 72px | Full-bleed section gaps |

Container max-width: `72rem` (1152px) — generous for map + decision side-by-side.

## Depth / Elevation (subtle, not layered)
- **Level 0 (base)**: No shadow, surface color only
- **Level 1 (card)**: `0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px var(--border)`
- **Level 2 (elevated)**: `0 4px 12px rgba(0,0,0,0.5), 0 0 0 1px var(--border-strong)`
- **Level 3 (dropdown/modal)**: `0 12px 32px rgba(0,0,0,0.6), 0 0 0 1px var(--border-strong)`

No colored glows except decision badge (ember/blue/crimson subtle ring) and focus states.

## Decision Badge — The Hero Element
The PROCEED/MODIFY/RESCHEDULE word is the single most important pixel on the page.
- **Size**: `display-xl` (clamp 3rem–5.5rem)
- **Font**: Space Grotesk Variable
- **Weight**: Variable — 400 (Regular) for LOW confidence, 600 (SemiBold) for MEDIUM, 700 (Bold) for HIGH. Or map to risk level: LOW=400, MEDIUM=600, HIGH=700.
- **Color**: Decision color (blue-gray / ember / crimson)
- **Background**: Decision-surface + 1px decision-border
- **Padding**: `space-5` horizontal, `space-4` vertical
- **Border-radius**: `0.75rem` (12px) — pill-ish but not fully round
- **Subtle glow**: `0 0 24px decision-glow` (very subtle, only on HIGH/RESCHEDULE)
- **Animation**: On change, split-flap style character cascade (300ms stagger) — the call is unmissable

## Components

### SearchLocation
- Input: surface background, border, ember focus ring
- Dropdown: Level 2 elevation, backdrop-blur, max-h-72
- Suggestion items: zone preview line in text-muted
- Selected highlight: surface-hover + ember left border (2px)

### Time Window Selector
- Segmented control: surface background, border
- Active: decision-surface + decision-border + decision-text
- Inactive: surface + border + text-secondary
- Site time display: mono-sm, text-muted, right-aligned

### Evaluate Button
- Full-width on mobile, auto on desktop
- Background: ember (primary action color)
- Text: text-primary, font-medium
- Hover: ember-400
- Active: ember-600
- Disabled: 40% opacity, no hover
- Loading: ember + spinner, text "Evaluating…"

### AoiMap
- Full-height card (matches decision card height on desktop)
- CARTO dark tiles, no additional chrome
- AOI ring: 2px decision-color, 15% fill
- Threshold legend: bottom-left overlay, semi-transparent surface
- Coordinates: mono-sm, text-muted, collapsible

### DecisionCard
- **Full-width on mobile, 1fr on desktop (matches map height)**
- Hero decision badge at top, spanning full width
- Climate zone badge: inline, ember-text on ember-surface
- Temperatures: side-by-side, display-md, mono, tabular-nums
- Recommendation: body-lg, text-primary
- Reasoning: body, text-secondary
- Metadata footer: caption, text-muted

### HistoryList
- Compact rows, hover → surface-hover
- Decision dot + word (label size) + timestamp + location (truncated)
- Peak temp: mono-sm, right-aligned
- Selected: surface-hover + ember left border (2px)

### MockBanner (dev only)
- Fixed bottom bar, surface + border-strong
- Ember accent, "Mock mode" label
- Hidden entirely in production builds (dead code elimination)

## Motion
- **Decision badge change**: split-flap cascade, 300ms, stagger 20ms/char
- **Card appear**: fade + slide up 8px, 250ms cubic-bezier(0.2, 0.8, 0.2, 1)
- **Map retint**: 200ms color transition
- **Dropdown open**: fade + scale(0.98→1), 150ms
- **Focus ring**: 150ms ease-out
- **Respect `prefers-reduced-motion`**: disable all except decision badge (instant swap)

## Accessibility
- WCAG 2.1 AA minimum
- All interactive: 3px focus ring (ember), visible in both light/dark (we're dark-only)
- Color never sole carrier: decision badge has icon (dot), text, weight, color
- Temperature null state: shows "—" with explanatory note
- Keyboard: full nav, Skip to main content
- Screen reader: live region on decision change, aria-labels on icon-only buttons

## Production Build
- `USE_MOCK_DATA` / `NEXT_PUBLIC_USE_MOCK_DATA` → `MockBanner` and mock scenarios **completely eliminated** via Next.js `env` inlining + tree-shaking
- `isMockMode()` check becomes constant `false` → dead code elimination removes entire mock module
- No mock code in production bundle

## Implementation Notes
- All design tokens in `globals.css` under `@theme` (Tailwind v4)
- Fonts loaded via `next/font/google` with `display: swap` and preload
- Components remain in `components/`, page in `app/page.tsx`
- `MockBanner` wrapped in `{isMockMode() && ...}` — Next.js eliminates at build time when env is empty
- No shadcn/ui dependency — custom components built on Tailwind primitives