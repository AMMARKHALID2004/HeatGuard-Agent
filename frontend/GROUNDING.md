# HeatGuard Agent — 7 Grounded Visual Directions

**Product**: HeatGuard Agent — Autonomous heat-risk agent for outdoor construction work. FortyGuard hyperlocal temperature + fixed climate-zone thresholds → PROCEED / MODIFY / RESCHEDULE decision.

**Audience**: Construction site supervisor/foreman. On-site (tablet/phone) or site office (desktop). Pre-shift go/no-go decision. High-stakes, time-pressured, glanceable.

**Mode**: Operate — scanability, authority, field legibility outrank expression.

---

## Direction 1 — Industrial SCADA / HMI Control Panel
**Resonance**: ★★★★★ This IS the supervisor's daily visual world. They read machine status from color-coded panels where green=run, amber=caution, red=stop. The decision map is a status panel.

**System Grammar**:
- Palette: Near-black panel ground (#05080C), high-contrast status colors (proceed blue-gray #5BA4E0, modify ember #E87A1E, reschedule crimson #C0392B), wire-thin grid lines (#1A2533)
- Type: Monospace for all readings (JetBrains Mono), IBM Plex Sans for labels, Space Grotesk only for the decision word
- Topology: Fixed grid layout — map quadrant, decision quadrant, threshold legend, history log. No floating cards.
- Controls: Segmented time selector as physical toggle switches. Evaluate as a momentary industrial button.
- States: Live pulsing indicator when polling. Decision locks with audible/visual confirmation.

**Web Leverage**: CSS Grid with named areas matching panel zones. `prefers-reduced-motion` kills pulse but keeps color lock.

**First Viewport**: Full-screen panel. Top: site identity + timezone. Left 60%: map with AOI ring in decision color. Right 40%: decision badge (hero scale) + thresholds as labeled LED strips. Bottom: history as status log.

---

## Direction 2 — Construction Site Safety Signage / OSHA Board
**Resonance**: ★★★★★ The physical signs they walk past daily. Red/amber/green internalized. Bold, readable at 10m. No ambiguity.

**System Grammar**:
- Palette: Safety sign white/black ground, OSHA red (#C0392B), orange (#E87A1E), blue (#5BA4E0), safety green (not used — avoid confusion with PROCEED), high-vis yellow accent only for active element
- Type: Heavy sans headlines (Space Grotesk Bold), IBM Plex Sans for body. All caps for section headers. Stencil/industrial feel.
- Topology: Single vertical stack — site banner, decision panel (full width), threshold legend as color bars, map, history as incident log.
- Controls: Large touch targets. Time selector as color-coded pills matching decision palette.
- States: Decision panel flashes once on change (like a strobe). Loading = rotating amber beacon.

**Web Leverage**: Viewport-height sections. `intersection-observer` triggers scroll-reveal for threshold bars.

**First Viewport**: Site banner (yellow top bar). Decision panel dominates — full-width colored band with decision word at display-xl. Threshold legend as three horizontal bars (blue/amber/red) with temp ranges. Map below fold.

---

## Direction 3 — Industrial Temperature Gauge / Pyrometer Face
**Resonance**: ★★★★☆ Directly embodies the core measurement. Supervisors read analog dials on equipment. The "red line" = threshold. Needle position = decision.

**System Grammar**:
- Palette: Gauge black face (#05080C), white tick marks, colored arcs for zones (blue 0-30°C, amber 30-33°C, red 33°C+), ember needle, white numerals
- Type: JetBrains Mono for all numerals (tabular). Space Grotesk for decision word at center. IBM Plex Sans for labels.
- Topology: Radial gauge as hero (left on desktop, top on mobile). Decision word at gauge center. Thresholds as colored arcs on gauge face. Map + history as secondary panels.
- Controls: Time selector rotates the "target time" marker on gauge. Evaluate = "READ" button.
- States: Needle animates to position (smooth sweep). Gauge face tint shifts with risk level.

**Web Leverage**: SVG gauge with CSS custom properties for needle angle. `motion-reduce` = instant snap.

**First Viewport**: Large radial gauge (60vh). Needle at peak temperature. Colored arcs show thresholds. Decision word at center in Space Grotesk. Site + time below gauge. Map + history stacked right/below.

---

## Direction 4 — Aviation / Marine Instrument Panel
**Resonance**: ★★★★☆ Proven in life-critical glance reading. Red-line limits, high-contrast, night-vision compatible. "Mission Control" branding fits.

**System Grammar**:
- Palette: Aviation instrument black (#05080C), phosphor green/amber/red for status, white/gray for scales. Subtle grid. No decorative color.
- Type: Monospace for all data (JetBrains Mono). Space Grotesk for decision. IBM Plex Sans minimal.
- Topology: Instrument cluster layout. Primary flight display style: attitude indicator → map. Decision as "FLAPS" / "GEAR" style annunciator panel.
- Controls: Rotary-style time selector (click/tap increments). Evaluate as guarded switch.
- States: Annunciator panel: steady = decided, flash = new decision, dim = stale. Map dims during poll.

**Web Leverage**: CSS Grid with asymmetric columns. `prefers-color-scheme` locked dark. SVG for instrument graphics.

**First Viewport**: Two-column instrument panel. Left: map as moving-map display with AOI ring. Right: annunciator stack — decision (large), thresholds (strip), temps (digital readout), history (fault log style).

---

## Direction 5 — Tactical Field Display / Mission Planning
**Resonance**: ★★★★☆ "Mission Control" is the product metaphor. Decision-focused hierarchy. Information density for rapid go/no-go. Night-operation palette.

**System Grammar**:
- Palette: Tactical dark (#05080C), mission-critical red/amber/blue, intel gray for secondary. Single accent (ember) for primary action.
- Type: Space Grotesk for decision + headings (variable weight = confidence). JetBrains Mono for coords/temps/time. IBM Plex Sans for prose.
- Topology: Map-centric (full width/height). Decision card slides over map as overlay (like a mission brief). Thresholds in collapsible sidebar. History as mission log.
- Controls: Time selector as mission timeline scrubber. Evaluate = "EXECUTE" button (ember, full-width on mobile).
- States: Map tint = risk level. Decision overlay appears with slide-up + flap animation. Loading = radar sweep on map.

**Web Leverage**: Leaflet map as canvas. Overlay with `position: fixed` on mobile, sidebar on desktop. Framer Motion for slide/flap.

**First Viewport**: Full-screen map. AOI ring in decision color. Decision overlay bottom sheet (mobile) / right panel (desktop) — hero badge, recommendation, reasoning. Thresholds in collapsible drawer.

---

## Direction 6 — Surveyor's Field Book / Engineer's Notebook
**Resonance**: ★★★☆☆ The tactile artifact of on-site work. Grid paper, handwritten authority, rugged utility. Trust through craft.

**System Grammar**:
- Palette: Paper warm-dark (#0B121A), graphite gray text (#8B99A9), blue/amber/red ballpoint for decisions, grid lines (#1A2533).
- Type: Space Grotesk for headings (like hand-printed caps). IBM Plex Sans for body. JetBrains Mono for measurements. Slight typewriter imperfection.
- Topology: Two-page spread. Left: map with grid overlay. Right: decision entry with ruled lines. Thresholds as marginalia. History as previous pages.
- Controls: Time selector as page-tabs. Evaluate = "LOG ENTRY" button.
- States: New entry animates like ink drying. Decision color bleeds into margin.

**Web Leverage**: CSS Grid with grid-line background. `::before` ruled lines. Print stylesheet = actual field book.

**First Viewport**: Spread layout. Left page: map on grid paper. Right page: decision entry — date/time header, decision word large, recommendation in ruled lines, reasoning below. Thresholds in right margin.

---

## Direction 7 — Meteorological Radar / Weather Station Display
**Resonance**: ★★★☆☆ The data source world. Isolines, color ramps, time-series. But risks being data-heavy vs decision-focused.

**System Grammar**:
- Palette: Radar dark, temperature color ramp (blue→amber→red), white isolines, grid.
- Type: Monospace for data. Space Grotesk for alerts. IBM Plex Sans for labels.
- Topology: Map dominates with temperature overlay. Decision as weather warning polygon. Thresholds as isotherm lines. History as timeline.
- Controls: Time slider as animation scrubber. Evaluate = "UPDATE FORECAST".
- States: Map animates temperature progression. Decision flashes like weather alert.

**Web Leverage**: Canvas/WebGL for temperature raster. Leaflet for base. Time-series chart for history.

**First Viewport**: Full-screen temperature raster map. AOI highlighted. Decision as warning banner top. Thresholds as isotherm legend. History as timeline bottom.

---

## Assignment

**ASSIGNED INDEX: 5** — Tactical Field Display / Mission Planning

This direction wins because:
1. **"Mission Control" is already the product metaphor** (per DESIGN.md) — this direction owns it literally
2. **Map-centric** — the AOI is the primary spatial reference; supervisors think in locations
3. **Overlay decision card** — keeps the call visible without losing map context; mobile-first
4. **Timeline scrubber** — natural for "Now / +3h / +6h / +12h" as mission time points
5. **Radar sweep loading** — honest about the async FortyGuard poll, uses the map as the progress surface
6. **Variable-weight decision word** — Space Grotesk weight tracks confidence (already in DESIGN.md)
7. **Cross-surface reach** — the mission brief / overlay pattern extends to multi-site dashboard, alert detail, historical review

**Honest Risk**: Most similar to current implementation (map + decision card). The differentiation is in commitment: full-screen map, overlay not side-by-side, tactical density, radar-sweep loading, mission vocabulary. Must not drift into "dashboard with map."

---

## Challengers — Fused & Weighed

### Challenger 1: Broadcast Teletext Magazine
**Fusion**: 40×24 character grid, block-mosaic map, fixed palette (8 colors). Decision = page header.
**Verdict**: **DECLINED** — Too abstract. Construction supervisors don't read teletext. Loses on audience ID (foreign form) and product clarity (decision buried in grid).
**Donation**: **Rigid grid discipline** — the 40-column rhythm becomes the spacing scale's horizontal anchor. The "page address" concept → deep-linkable evaluation states.

### Challenger 2: Struck Cathode Gauze (Operate-B)
**Fusion**: All states present as ghosts; active struck forward in glow. Decision = the one lit numeral.
**Verdict**: **COMPETITIVE** — Holds product clarity (single glowing decision), loses audience ID (too alien). The "all options visible" ghost layer is powerful for threshold transparency.
**Donation**: **Ghost thresholds** — show all three risk bands as dim arcs/bands always; active one struck bright. Currently only active band is prominent. Raise: threshold legend always shows all three, current risk glows.

### Challenger 3: Sneaker Archive Box Stack
**Fusion**: Stacked cards as boxes. Pull one → decision. Colorway chip = risk level.
**Verdict**: **DECLINED** — Wrong metaphor. Boxes = storage, not decision. Loses both axes.
**Donation**: **Tactile card slide** — history entries as stacked boxes, selected slides half-out. Already partially in HistoryList. Raise: make the slide interaction deliberate, not just highlight.

### Challenger 4: Iridescent Cloud Edge
**Fusion**: Narrow color fringe at map edge = threshold. Droplet distribution = temperature variance.
**Verdict**: **DECLINED** — Too poetic. Loses authority. Construction supervisors need certainty, not diffraction.
**Donation**: **Color fringe on map** — AOI ring already does this. Raise: make the ring a true gradient fringe (blue→amber→red) showing spatial variance, not solid color.

### Challenger 5: Game Boy Four-Shade Field
**Fusion**: 4 greens, 160×144 grid, pixel font. Decision = blinking cursor line.
**Verdict**: **DECLINED** — Nostalgic, not authoritative. Loses audience ID hard.
**Donation**: **Four-tone discipline** — limit palette to 4 values per role. Already close (bg, surface, border, text + 3 decision colors). Raise: enforce strictly, audit for palette creep.

### Challenger 6: Creator Hardware Desk Instrument
**Fusion**: Bone/putty keys on gunmetal. One safety-orange action key. Knob for continuous control.
**Verdict**: **COMPETITIVE** — Holds audience ID (physical controls), loses product clarity (too skeuomorphic). The "one orange key" = Evaluate button is strong.
**Donation**: **Single action key** — Evaluate button as the only ember element on idle screen. Currently it is. Raise: make it physically distinct (deeper shadow, key-travel motion, guard).

---

## Raised Direction 5 — Tactical Field Display (with donations)

**THESIS**: The map is the mission. The decision is the briefing. Every element serves the go/no/go call.

**OWN-WORLD**:
- Palette: Tactical ink (#05080C), panel (#0B121A), intel border (#1A2533), ember action (#E87A1E), proceed blue-gray (#5BA4E0), modify ember, reschedule crimson (#C0392B). Ghost thresholds (all three always visible, active glows).
- Type: Space Grotesk Variable (decision weight = confidence), JetBrains Mono (all data), IBM Plex Sans (prose).
- Components: Map as canvas. Overlay briefing card. Timeline scrubber. Guarded execute button. Radar sweep loader. Ghost threshold bars.
- Motion: Radar sweep (polling). Briefing slide-up + flap. Timeline scrub. Threshold glow pulse.

**STORY**: Supervisor opens app → sees site on map → scrubs mission time → hits EXECUTE → radar sweeps → briefing slides up with the call → reads recommendation → if RESCHEDULE, crew alerted automatically.

**FIRST VIEWPORT**: Full-screen map (CARTO dark). AOI ring with gradient fringe (donation from Challenger 4). Top bar: site name + site time (PDT). Bottom sheet (mobile) / right panel (desktop): decision badge hero, recommendation, reasoning. Collapsible drawer: ghost threshold bars (donation from Challenger 2) — all three bands dim, active glows. Timeline scrubber at sheet handle / panel top. EXECUTE button ember, guarded (donation from Challenger 6).

**FORM**: Direction 5 (Tactical Field Display), assigned index 5, seed key `d6cf670d`.

**FINISH**: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.