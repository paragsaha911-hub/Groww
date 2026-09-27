---
name: Groww Fund Facts Assistant
colors:
  surface: '#111317'
  surface-dim: '#111317'
  surface-bright: '#37393e'
  surface-container-lowest: '#0c0e12'
  surface-container-low: '#1a1c20'
  surface-container: '#1e2024'
  surface-container-high: '#282a2e'
  surface-container-highest: '#333539'
  on-surface: '#e2e2e8'
  on-surface-variant: '#bacac1'
  inverse-surface: '#e2e2e8'
  inverse-on-surface: '#2f3035'
  outline: '#85948c'
  outline-variant: '#3c4a43'
  surface-tint: '#2fe0aa'
  primary: '#44edb7'
  on-primary: '#003828'
  primary-container: '#00d09c'
  on-primary-container: '#00533c'
  inverse-primary: '#006c4f'
  secondary: '#7bd0ff'
  on-secondary: '#00354a'
  secondary-container: '#00a6e0'
  on-secondary-container: '#00374d'
  tertiary: '#ffc98a'
  on-tertiary: '#472a00'
  tertiary-container: '#fda417'
  on-tertiary-container: '#673f00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#59fdc5'
  primary-fixed-dim: '#2fe0aa'
  on-primary-fixed: '#002116'
  on-primary-fixed-variant: '#00513b'
  secondary-fixed: '#c4e7ff'
  secondary-fixed-dim: '#7bd0ff'
  on-secondary-fixed: '#001e2c'
  on-secondary-fixed-variant: '#004c69'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#111317'
  on-background: '#e2e2e8'
  surface-variant: '#333539'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 22px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '500'
    lineHeight: 24px
    letterSpacing: '0'
  body-md:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: '0'
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: '0'
  label-lg:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.025em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 1.5rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system establishes an authoritative, compliance-governed AI assistant delivering factual data on HDFC Mutual Fund schemes. Grounded in a modern fintech ethos, it avoids gamification, retail speculation, or aggressive trading graphics in favor of neutral, statutory compliance and focused institutional calm.

The visual style blends **Minimalism** with subtle **Tonal Layering**:
- Deep obsidian and charcoal surfaces (`#0F1115`, `#16191F`, `#1E222B`) eliminate ocular fatigue and provide strong contrast for reading tabular disclosures and citations.
- The signature Groww emerald green (`#00D09C`) is preserved strictly as a functional action driver, active selection indicator, and official citation anchor—never as an indicator of speculative stock return or market gain.
- Red/green sentiment metaphors are omitted entirely. Quantitative metrics remain visually neutral and matter-of-fact.
- Structural hairline borders (`#282D37`) frame information without clutter, reinforcing a dependable, audit-ready atmosphere.

## Colors

The palette operates in strict dark mode, anchored by deep charcoal foundations and restrained accents.

### Color Roles & Guidelines

- **Primary (`#00D09C`)**: The core signature brand color. Reserved exclusively for primary interactive buttons, active tab states, citation pill highlights, and verification checks. It must never be paired with red to communicate portfolio return semantics.
- **Secondary (`#38BDF8`)**: Secondary information anchor. Used for secondary mirror sources (e.g., fallback portal data requiring verification on `hdfcfund.com`) and non-critical informative links.
- **Tertiary (`#F59E0B`)**: Muted warning amber. Exclusively reserved for advice refusal cards, regulatory disclaimers, and guardrail notifications when queries veer into speculative advisory territory.
- **Neutral Canvas & Surfaces (`#0F1115`, `#16191F`, `#1E222B`, `#12151B`)**:
  - `#0F1115` provides the deep obsidian root canvas.
  - `#16191F` creates primary card bodies and chat response containers.
  - `#1E222B` lifts interactive components, dropdowns, and button hovers.
  - `#12151B` sinks input text fields and recessed metric tables.
- **Borders & Dividers**:
  - `#282D37` serves as the universal hairline boundary (1px) for cards, tabs, and input states.
  - `#3B4352` is invoked for subtle hover elevations and active element outlines.
  - `#20242D` provides internal separation rules within cards and source lists.
- **Typography Colors**:
  - High-contrast crisp off-white (`#F1F3F7`) for generated answers, headers, and values.
  - Cool slate (`#9CA3AF`) for meta labels, categories, and placeholders.
  - Muted slate (`#64748B`) for tertiary details and timestamps.

## Typography

The typography hierarchy uses **Inter** across all display, body, and label roles to maximize legibility and maintain neutral clarity.

- **Tabular Numerals**: All numerical figures, dates, and fund metrics (such as expense ratios, lock-in terms, and minimum SIP amounts) must enforce `font-variant-numeric: tabular-nums` to guarantee aligned columns in comparative grids.
- **Generated Answer Constraints**: Standard conversational answers render using `body-md` (15px, 24px line height) and should stay concise (≤ 3 sentences per factual reply) to avoid reading fatigue on dark backgrounds.
- **Compliance Ribbon**: Uses `label-sm` with uppercase styling and expanded tracking (+0.05em) to differentiate regulatory disclaimers from primary conversational copy.

## Layout & Spacing

This design system uses a centered, single-column fluid layout with a maximum container width of `840px`. This structure keeps user queries, factual outputs, and tabular disclosures within a comfortable reading frame without horizontal scanning fatigue.

### Layout Model
- **Max Container Width**: 840px centered horizontally with fluid side margins.
- **Section Rhythm**: Vertical separation of `1.5rem` (`24px`) between distinct query-response cycles. Sub-elements within answer cards maintain `0.75rem` (`12px`) row gaps.
- **Responsive Adaptations**:
  - **Mobile (< 640px)**: Gutter and canvas margin drop to `1rem` (`16px`). Scheme selector pills switch to horizontal overflow touch scrolling. The chat prompt anchors to the bottom with safe-area bottom padding.
  - **Desktop (≥ 640px)**: Full `1.5rem` (`24px`) padding. Example query chips display in a wrapped multi-row grid.

## Elevation & Depth

Visual depth is achieved primarily through **tonal surface stepping** and **low-contrast hairline outlines**, rather than high-contrast drop shadows:

- **Base Layer (Canvas)**: `#0F1115` serves as the zero-elevation backdrop.
- **Surface Layer (Cards & Panels)**: `#16191F` delineated by a crisp 1px border (`#282D37`).
- **Raised Interactive Layer (Chips, Toolbars, Menus)**: `#1E222B` with hover shifts to `#242935` and border shifts to `#3B4352`.
- **Sunken Elements (Inputs, Metric Blocks)**: `#12151B` recessed beneath card containers to indicate typed entry or structured data grouping.
- **Shadows**: Only subtle ambient occlusion is permitted (`0 2px 8px rgba(0, 0, 0, 0.4)` on answer containers). Glowing shadows, dramatic color-tinted drop shadows, and skeuomorphic bevels are strictly forbidden.
- **Focus Rings**: Focused inputs and primary interactive elements utilize a clean, non-diffuse ring: `0 0 0 3px rgba(0, 208, 156, 0.18)`.

## Shapes

The design system enforces a balanced geometric curvature:
- **Base Components (Inputs, Primary Buttons, Metric Blocks)**: 8px border radius (`0.5rem`).
- **Cards and Dialog Containers**: 12px border radius (`rounded-lg`).
- **Pills and Metadata Badges**: Full roundedness (`9999px`) for citation badges, scheme filtering tabs, freshness timestamps, and prompt chips.

## Components

### Buttons
- **Primary Action**: Solid `#00D09C` background, `#0A0D10` high-contrast bold text, 8px radius, 40px height, 18px horizontal padding. Hover shifts to `#00B789`. Press active state shifts to `#009E75`.
- **Secondary / Ghost**: Transparent fill, 1px solid `#282D37` border, `#F1F3F7` text. On hover, background transitions to `#1E222B` and border to `#3B4352`.
- **Prompt Suggestion Buttons**: `#16191F` background, `#282D37` border, full-pill shape (or 8px radius), with an emerald question mark indicator. Hover turns the outline to `#00D09C`.

### Cards & Chat Containers
- **Factual Answer Card**: `#16191F` background with `#282D37` hairline border, 12px radius, and 20px interior padding (16px on mobile). Anatomy consists of:
  1. Header with scheme badge and optional offline indicator.
  2. Core fact body text (≤ 3 sentences).
  3. Metric highlight grid (tabular data).
  4. Footer separated by a 1px `#20242D` divider containing official citation pills and freshness date stamps.
- **Refusal / Advice Disclaimer Card**: Dark amber container fill (`#1F1A12`) with 1px border (`#5C3E14`), an amber shield icon, and neutral refusal copy indicating non-advisory bounds.
- **PII Guardrail Warning**: Coral-tinted dark card (`#2B1617` fill, `#63282B` border, `#F87171` text) alerting users that identifiers like PAN, Folio, or Aadhaar were redacted.

### Input Fields & Scheme Filters
- **Query Input Bar**: Height 48px, background `#12151B`, border 1px solid `#282D37`, text `#F1F3F7`, placeholder `#64748B`. Focus state transitions border to `#00D09C` with a 3px emerald outline glow. Trailing circular send button (36px × 36px) transitions from disabled state (`#1E222B`) to emerald when populated.
- **Scheme Selector Tabs**: Horizontal pill container. Inactive states use `#16191F` with `#282D37` border and `#9CA3AF` text; active selected state applies `#0B2921` container fill, `#00D09C` border, and `#00D09C` text.

### Citation & Trust Badges
- **Verified AMC Citation Badge**: Pill tag with `#0F2520` background, 1px solid `#175242` border, `#00D09C` text, and a trailing external document icon (12px). Hover state deepens background to `#16382E`.
- **Freshness Timestamp**: `#828B9E` text, calendar glyph, displaying `Last updated from sources: YYYY-MM-DD`.
- **Persistent Compliance Ribbon**: Sits permanently at top/bottom of view. `#16191F` fill, `#282D37` border, 6px radius, uppercase label styling: `FACTS-ONLY. NO INVESTMENT ADVICE.`