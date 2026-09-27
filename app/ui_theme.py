from __future__ import annotations

TOKENS = {
    "surface": "#111317",
    "surface_dim": "#111317",
    "surface_bright": "#37393e",
    "surface_container_lowest": "#0c0e12",
    "surface_container_low": "#1a1c20",
    "surface_container": "#1e2024",
    "surface_container_high": "#282a2e",
    "surface_container_highest": "#333539",
    "on_surface": "#e2e2e8",
    "on_surface_variant": "#bacac1",
    "outline": "#85948c",
    "outline_variant": "#3c4a43",
    "surface_tint": "#2fe0aa",
    "primary": "#44edb7",
    "on_primary": "#003828",
    "primary_container": "#00d09c",
    "on_primary_container": "#00374d",
    "secondary": "#7bd0ff",
    "on_secondary": "#00354a",
    "secondary_container": "#00a6e0",
    "tertiary": "#ffc98a",
    "on_tertiary": "#472a00",
    "tertiary_container": "#fda417",
    "error": "#ffb4ab",
    "on_error": "#690005",
    "error_container": "#93000a",
    "font_family": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "radius_sm": "0.25rem",
    "radius": "0.5rem",
    "radius_md": "0.75rem",
    "radius_lg": "1rem",
    "radius_full": "9999px",
    "space_xs": "0.25rem",
    "space_sm": "0.5rem",
    "space_md": "0.75rem",
    "space_lg": "1rem",
    "space_xl": "1.5rem",
    "gutter": "1.5rem",
    "gutter_mobile": "1rem",
    "max_width": "840px",
    "shadow_card": "0 2px 8px rgba(0, 0, 0, 0.4)",
    "focus_ring": "0 0 0 3px rgba(0, 208, 156, 0.18)",
    "border_hairline": "#282D37",
}

type_scale = {
    "headline_lg": "700 24px/32px Inter, sans-serif",
    "headline_md": "600 18px/26px Inter, sans-serif",
    "headline_sm": "600 15px/22px Inter, sans-serif",
    "body_lg": "500 15px/24px Inter, sans-serif",
    "body_md": "400 15px/24px Inter, sans-serif",
    "body_sm": "400 14px/20px Inter, sans-serif",
    "label_lg": "500 13px/18px Inter, sans-serif",
    "label_md": "600 12px/16px Inter, sans-serif",
    "label_sm": "700 11px/16px Inter, sans-serif",
}


def _vars() -> str:
    rows = []
    for key, value in TOKENS.items():
        css_name = key.replace("_", "-")
        rows.append(f"  --{css_name}: {value};")
    return "\n".join(rows)


def build_css() -> str:
    t = TOKENS
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@100..900&display=swap');

:root {{
{_vars()}
  --label-sm-tracking: 0.05em;
  --label-md-tracking: 0.025em;
}}

html, body, [class*="css"], .stApp {{
  font-family: var(--font-family);
}}

.stApp {{
  background: var(--surface);
  color: var(--on-surface);
}}

.block-container {{
  max-width: var(--max-width);
  padding-top: var(--gutter);
  padding-bottom: 6rem;
  padding-left: var(--gutter-mobile);
  padding-right: var(--gutter-mobile);
}}

@media (min-width: 640px) {{
  .block-container {{ padding-left: var(--gutter); padding-right: var(--gutter); }}
}}

h1, h2, h3, h4, p, span, div, label, li {{
  font-family: var(--font-family);
}}

.gfa-root {{ display: flex; flex-direction: column; gap: var(--space-lg); }}

.gfa-html * {{ box-sizing: border-box; }}

.gfa-html p {{ margin: 0; }}

.gfa-compliance {{
  display: flex; align-items: center; gap: var(--space-sm);
  padding: var(--space-sm); border-radius: var(--radius-md);
  background: var(--surface-container-high);
  border: 1px solid var(--border-hairline);
  color: var(--on-surface-variant);
  font: 700 11px/16px var(--font-family);
  letter-spacing: var(--label-sm-tracking);
  text-transform: uppercase;
}}
.gfa-compliance .gfa-shield {{ color: var(--primary-container); font-size: 16px; }}
.gfa-compliance strong {{ color: var(--on-surface); font-weight: 700; }}

.gfa-nav {{
  display: flex; gap: var(--space-xs); overflow-x: auto;
  padding-bottom: var(--space-xs); scrollbar-width: none;
}}
.gfa-nav::-webkit-scrollbar {{ display: none; }}

.gfa-pill {{
  flex: 0 0 auto; padding: 6px var(--space-md); border-radius: var(--radius-full);
  font: 600 12px/16px var(--font-family);
  letter-spacing: var(--label-md-tracking);
  background: var(--surface-container);
  border: 1px solid var(--border-hairline);
  color: var(--on-surface-variant); cursor: pointer;
  transition: background .15s ease, border-color .15s ease, color .15s ease;
}}
.gfa-pill:hover {{ background: var(--surface-container-highest); }}
.gfa-pill[aria-pressed="true"] {{
  background: #0b2921; border-color: var(--primary-container); color: var(--primary-container);
}}

.gfa-turn {{ display: flex; flex-direction: column; gap: var(--space-sm); width: 100%; }}
.gfa-turn-user {{ align-items: flex-end; }}
.gfa-turn-bot {{ align-items: flex-start; }}

.gfa-bubble {{
  max-width: 85%; padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-lg); background: var(--surface-container-highest);
  color: var(--on-surface); font: 400 15px/24px var(--font-family);
}}
.gfa-turn-user .gfa-bubble {{ border-bottom-right-radius: var(--radius-sm); }}
.gfa-turn-bot .gfa-bubble {{ border-top-left-radius: var(--radius-sm); }}

.gfa-stamp {{ padding: 0 var(--space-xs); color: var(--outline); font: 700 11px/16px var(--font-family); }}

.gfa-card {{
  width: 100%; display: flex; flex-direction: column; gap: var(--space-md);
  padding: var(--space-md); border-radius: var(--radius-lg);
  background: var(--surface-container);
  border: 1px solid var(--border-hairline);
  box-shadow: var(--shadow_card);
}}

.gfa-card-head {{ display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); flex-wrap: wrap; }}
.gfa-card-title {{ display: flex; align-items: center; gap: var(--space-xs); }}
.gfa-dot {{ width: 8px; height: 8px; border-radius: var(--radius-full); background: var(--primary-container); flex: 0 0 auto; }}
.gfa-dot-secondary {{ background: var(--secondary); }}
.gfa-scheme {{ font: 600 12px/16px var(--font-family); letter-spacing: var(--label-md-tracking); text-transform: uppercase; color: var(--primary-container); }}
.gfa-scheme-secondary {{ color: var(--secondary); }}
.gfa-chip-note {{ padding: 2px var(--space-xs); border-radius: var(--radius-sm); background: var(--surface-container-low); color: var(--on-surface-variant); font: 700 11px/16px var(--font-family); }}

.gfa-answer {{ color: var(--on-surface); font: 400 15px/24px var(--font-family); }}
.gfa-answer b {{ color: var(--primary-container); font-weight: 600; }}

.gfa-metrics {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-xs); padding: var(--space-sm); border-radius: var(--radius-md); background: var(--surface-container-lowest); }}
.gfa-metric {{ display: flex; flex-direction: column; gap: 2px; padding: var(--space-xs); border-radius: var(--radius); background: var(--surface-container-low); }}
.gfa-metric-label {{ color: var(--outline); font: 700 11px/16px var(--font-family); letter-spacing: var(--label-sm-tracking); text-transform: uppercase; }}
.gfa-metric-value {{ color: var(--on-surface); font: 600 15px/22px var(--font-family); font-variant-numeric: tabular-nums; }}
.gfa-metric-sub {{ color: var(--on-surface-variant); font: 400 11px/16px var(--font-family); }}

.gfa-foot {{ display: flex; flex-direction: column; gap: var(--space-xs); padding: var(--space-sm); border-radius: var(--radius-md); background: var(--surface-container-low); border-top: 1px solid #20242d; }}
.gfa-fresh {{ display: flex; align-items: center; gap: 6px; color: var(--on-surface-variant); font: 400 11px/16px var(--font-family); }}
.gfa-source {{ display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); padding: 6px var(--space-sm); border-radius: var(--radius); background: var(--surface-container-high); color: var(--primary-container); text-decoration: none; }}
.gfa-source:hover {{ background: var(--surface-container-highest); }}
.gfa-source span {{ font: 600 12px/16px var(--font-family); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

.gfa-refusal {{ width: 100%; display: flex; flex-direction: column; gap: var(--space-md); padding: var(--space-md); border-radius: var(--radius-lg); background: #1F1A12; border: 1px solid #5C3E14; }}
.gfa-pii {{ background: #2B1617; border: 1px solid #63282B; }}
.gfa-pii .gfa-tag {{ color: #F87171; }}
.gfa-tag {{ display: inline-flex; align-items: center; gap: var(--space-xs); align-self: flex-start; padding: var(--space-xs) var(--space-sm); border-radius: var(--radius-full); background: rgba(253, 164, 23, 0.18); color: var(--tertiary); font: 700 11px/16px var(--font-family); letter-spacing: var(--label-sm-tracking); text-transform: uppercase; }}
.gfa-tag-error {{ background: rgba(255, 180, 171, 0.16); color: var(--error); }}

.gfa-callout {{ display: flex; align-items: flex-start; gap: var(--space-sm); padding: var(--space-sm); border-radius: var(--radius-md); background: var(--surface-container-lowest); color: var(--on-surface-variant); font: 400 11px/16px var(--font-family); }}

.gfa-actions {{ display: flex; align-items: center; gap: var(--space-xs); flex-wrap: wrap; padding-top: 2px; }}
.gfa-action {{ display: inline-flex; align-items: center; gap: 4px; padding: 4px var(--space-sm); border-radius: var(--radius-full); background: var(--surface-container-high); border: 1px solid var(--border-hairline); color: var(--on-surface); font: 600 12px/16px var(--font-family); }}

.gfa-scheme-card {{ display: flex; flex-direction: column; gap: var(--space-sm); padding: var(--space-md); border-radius: var(--radius-lg); background: var(--surface-container-low); border: 1px solid var(--border-hairline); box-shadow: var(--shadow_card); }}
.gfa-scheme-top {{ display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-sm); }}
.gfa-tags {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 4px; }}
.gfa-tag-cat {{ padding: 2px 8px; border-radius: var(--radius-sm); background: var(--surface-container-highest); color: var(--on-surface-variant); font: 700 11px/16px var(--font-family); letter-spacing: var(--label-sm-tracking); text-transform: uppercase; }}
.gfa-tag-risk {{ display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: var(--radius-full); background: rgba(253, 164, 23, 0.18); color: var(--tertiary); font: 700 11px/16px var(--font-family); }}
.gfa-tag-risk-high {{ background: rgba(0, 166, 224, 0.18); color: var(--secondary); }}
.gfa-tag-lock {{ background: rgba(253, 164, 23, 0.18); color: var(--tertiary); }}
.gfa-risk-cap {{ color: var(--outline); font: 700 11px/16px var(--font-family); text-transform: uppercase; letter-spacing: var(--label-sm-tracking); }}

.gfa-scheme-meta {{ display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); padding: 2px 4px; color: var(--outline); font: 400 11px/16px var(--font-family); flex-wrap: wrap; }}
.gfa-scheme-meta strong {{ color: var(--on-surface); font-weight: 600; }}
.gfa-scheme-meta .gfa-lock {{ color: var(--tertiary); font-weight: 600; }}

.gfa-card-foot {{ display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); padding-top: var(--space-sm); margin-top: 4px; border-top: 1px solid rgba(60, 74, 67, 0.3); }}
.gfa-link {{ display: inline-flex; align-items: center; gap: 4px; color: var(--primary-container); text-decoration: none; font: 600 12px/16px var(--font-family); }}
.gfa-link-quiet {{ color: var(--on-surface-variant); font: 400 11px/16px var(--font-family); }}

.gfa-panel {{ display: flex; flex-direction: column; gap: var(--space-md); padding: var(--space-lg); border-radius: var(--radius-lg); background: var(--surface-container); border: 1px solid var(--border-hairline); }}
.gfa-panel-head {{ display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); flex-wrap: wrap; }}
.gfa-panel-title {{ display: flex; align-items: center; gap: var(--space-xs); color: var(--on-surface); font: 600 15px/22px var(--font-family); }}
.gfa-panel-sub {{ color: var(--on-surface-variant); font: 400 14px/20px var(--font-family); }}

.gfa-list {{ display: flex; flex-direction: column; gap: var(--space-sm); }}
.gfa-list-item {{ display: flex; align-items: flex-start; gap: var(--space-sm); padding: var(--space-sm); border-radius: var(--radius); background: var(--surface-container-low); color: var(--on-surface); font: 400 14px/20px var(--font-family); }}
.gfa-list-item b {{ font-weight: 600; }}
.gfa-list-item .gfa-ico {{ flex: 0 0 auto; font-size: 16px; }}
.gfa-ico-ok {{ color: var(--primary-container); }}
.gfa-ico-no {{ color: var(--error); }}
.gfa-ico-warn {{ color: var(--tertiary); }}
.gfa-ico-info {{ color: var(--secondary); }}

.gfa-scope-row {{ display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); padding: var(--space-sm); border-radius: var(--radius); background: var(--surface-container-low); }}
.gfa-scope-name {{ display: flex; align-items: center; gap: var(--space-sm); min-width: 0; color: var(--on-surface); font: 500 13px/18px var(--font-family); }}
.gfa-scope-num {{ display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; flex: 0 0 auto; border-radius: var(--radius-full); background: var(--surface-container-highest); color: var(--primary-container); font: 700 11px/16px var(--font-family); }}
.gfa-scope-tag {{ flex: 0 0 auto; padding: 2px 8px; border-radius: var(--radius-sm); background: var(--surface-container-high); color: var(--on-surface-variant); font: 700 11px/16px var(--font-family); }}

.gfa-verdict {{ display: flex; align-items: flex-start; gap: var(--space-sm); padding: var(--space-md); border-radius: var(--radius); background: var(--surface-container); }}
.gfa-verdict-ico {{ display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; flex: 0 0 auto; border-radius: var(--radius-full); font-size: 14px; }}
.gfa-verdict-ok {{ background: rgba(0, 208, 156, 0.18); color: var(--primary-container); }}
.gfa-verdict-blocked {{ background: rgba(253, 164, 23, 0.18); color: var(--tertiary); }}
.gfa-verdict-query {{ color: var(--on-surface); font: 600 12px/16px var(--font-family); overflow-wrap: anywhere; }}
.gfa-verdict-body {{ margin-top: 4px; color: var(--on-surface-variant); font: 400 14px/20px var(--font-family); }}
.gfa-verdict-body b {{ font-weight: 600; }}

.gfa-empty {{ display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--space-sm); padding: var(--space-xl); border-radius: var(--radius-lg); background: var(--surface-container-low); text-align: center; }}
.gfa-empty-title {{ color: var(--on-surface); font: 600 15px/22px var(--font-family); }}
.gfa-empty-body {{ color: var(--outline); font: 400 14px/20px var(--font-family); }}

.gfa-counter {{ display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); padding: 0 4px; color: var(--outline); font: 700 11px/16px var(--font-family); letter-spacing: var(--label-sm-tracking); text-transform: uppercase; }}
.gfa-live {{ display: inline-flex; align-items: center; gap: 4px; color: var(--primary-container); }}
.gfa-live-dot {{ width: 6px; height: 6px; border-radius: var(--radius-full); background: var(--primary-container); }}

.gfa-input-row {{ display: flex; align-items: center; gap: var(--space-xs); padding: 4px; border-radius: var(--radius-full); background: var(--surface-container); border: 1px solid var(--border-hairline); }}
.gfa-input-row textarea, .gfa-input-row input {{ flex: 1; background: transparent; border: none; color: var(--on-surface); font: 400 14px/20px var(--font-family); outline: none; resize: none; }}
.gfa-input-row textarea::placeholder, .gfa-input-row input::placeholder {{ color: var(--outline); }}

.gfa-footnote {{ color: var(--outline); text-align: center; font: 700 11px/16px var(--font-family); letter-spacing: var(--label-sm-tracking); text-transform: uppercase; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

.gfa-legal {{ display: flex; align-items: flex-start; gap: var(--space-sm); padding: var(--space-lg); border-radius: var(--radius-lg); background: var(--surface-container-lowest); border: 1px solid var(--border-hairline); }}
.gfa-legal-body {{ color: var(--outline-variant); font: 400 14px/20px var(--font-family); }}
.gfa-legal-head {{ display: flex; align-items: center; gap: var(--space-xs); color: var(--tertiary); font: 700 11px/16px var(--font-family); letter-spacing: var(--label-sm-tracking); text-transform: uppercase; }}
.gfa-legal-meta {{ display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); padding-top: var(--space-xs); color: var(--outline); font: 700 11px/16px var(--font-family); }}

.gfa-banner {{ display: flex; align-items: center; gap: var(--space-xs); align-self: flex-start; padding: var(--space-xs) var(--space-sm); border-radius: var(--radius-full); background: var(--surface-container-high); color: var(--primary-container); font: 700 11px/16px var(--font-family); letter-spacing: var(--label-sm-tracking); text-transform: uppercase; }}

.gfa-title {{ color: var(--on-surface); font: 700 24px/32px var(--font-family); letter-spacing: -0.02em; }}
.gfa-lede {{ color: var(--on-surface-variant); font: 400 15px/24px var(--font-family); }}
.gfa-search {{ display: flex; align-items: center; gap: var(--space-xs); padding: var(--space-sm) var(--space-md); border-radius: var(--radius); background: var(--surface-container-low); border: 1px solid var(--border-hairline); color: var(--on-surface); font: 400 14px/20px var(--font-family); }}
.gfa-search input {{ flex: 1; background: transparent; border: none; color: var(--on-surface); outline: none; font: inherit; }}
.gfa-search input::placeholder {{ color: var(--outline); }}

/* Streamlit >= 1.60 builds the tab bar on react-aria, not baseweb.
   Real nodes: [data-testid="stTabs"] > [role="tablist"] > [data-testid="stTab"],
   with the active indicator as .react-aria-SelectionIndicator inside the active tab. */
.stTabs [role="tablist"] {{
  display: flex; align-items: stretch; justify-content: flex-start;
  gap: var(--space-md); flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden;
  border-bottom: 1px solid var(--border-hairline); scrollbar-width: none;
}}
.stTabs [role="tablist"]::-webkit-scrollbar {{ display: none; }}

.stTabs [data-testid="stTab"] {{
  position: relative; display: flex; align-items: center; justify-content: center;
  flex: 0 0 auto; margin: 0; border: 0; border-radius: 0; background: transparent;
  padding: var(--space-sm) 0; white-space: nowrap; cursor: pointer;
  color: var(--on-surface-variant); font: 600 12px/16px var(--font-family);
  transition: color 120ms ease;
}}
.stTabs [data-testid="stTab"] p {{ margin: 0; white-space: nowrap; font: inherit; }}
.stTabs [data-testid="stTab"] > div {{ flex: 0 0 auto; }}
.stTabs [data-testid="stTab"]:hover {{ color: var(--on-surface); }}
.stTabs [data-testid="stTab"]:focus-visible {{
  outline: none; box-shadow: var(--focus-ring); border-radius: var(--radius-sm); color: var(--on-surface);
}}
.stTabs [data-testid="stTab"][aria-selected="true"] {{
  color: var(--primary-container); background: transparent;
}}

/* Underline is sized by the tab's own box (left/right 0) so it always tracks the
   label width. Never set an explicit width or a fixed left offset here. */
.stTabs .react-aria-SelectionIndicator {{
  background: var(--primary-container); height: 2px; bottom: 0; left: 0; right: 0;
  border-radius: var(--radius-full); box-shadow: 0 0 8px rgba(0, 208, 156, 0.45);
}}

[data-testid="stAppViewContainer"] {{ background: var(--surface); color: var(--on-surface); }}
[data-testid="stHeader"] {{ background: transparent; color: var(--on-surface); }}
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"], [data-testid="stMain"] {{ background: var(--surface); }}
[data-testid="stSidebarUserContent"] {{ background: var(--surface-container-lowest); }}
section[data-testid="stSidebar"] {{ background: var(--surface-container-lowest); border-right: 1px solid var(--border-hairline); }}

.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button {{
  background: var(--surface-container-high); color: var(--on-surface);
  border: 1px solid var(--border-hairline); border-radius: var(--radius-full);
  font: 600 12px/16px var(--font-family); transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}}
.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {{
  background: var(--surface-container-highest); border-color: var(--outline-variant); color: var(--on-surface);
}}
.stButton > button:active,
.stDownloadButton > button:active,
.stFormSubmitButton > button:active {{
  background: var(--surface-container-highest); border-color: var(--outline-variant); color: var(--on-surface);
}}
.stButton > button:focus,
.stButton > button:focus-visible {{
  outline: none; box-shadow: var(--focus-ring); border-color: var(--primary-container); color: var(--on-surface);
}}
.stButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"] {{
  background: var(--primary-container); color: var(--on-primary);
  border: 1px solid var(--primary-container);
}}
.stButton > button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primary"]:focus:not(:active) {{
  background: #00b98a; color: var(--on-primary); border-color: #00b98a;
}}
.stButton > button[kind="primary"]:active,
button[data-testid="stBaseButton-primary"]:active {{
  background: #00a179; color: var(--on-primary); border-color: #00a179;
}}
.stButton > button[kind="primary"]:focus-visible {{
  box-shadow: var(--focus-ring); background: var(--primary-container); color: var(--on-primary);
}}
.stButton > button:disabled {{
  background: var(--surface-container-high); color: var(--outline); border-color: var(--border-hairline); opacity: 1;
}}

.stTextInput input, .stChatInput textarea, .stNumberInput input {{
  background: var(--surface-container-lowest) !important; color: var(--on-surface) !important;
  border: 1px solid var(--border-hairline) !important; border-radius: var(--radius) !important;
  font-family: var(--font-family) !important;
}}
.stTextInput input:focus, .stChatInput textarea:focus {{
  border-color: var(--primary-container) !important; box-shadow: var(--focus-ring) !important;
}}
.stTextInput input::placeholder {{ color: var(--outline) !important; }}
[data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
  background: var(--surface-container-lowest) !important; border-color: var(--border-hairline) !important; color: var(--on-surface) !important;
}}
[data-testid="stSelectbox"] svg {{ fill: var(--on-surface-variant) !important; }}
[data-baseweb="popover"] li {{ background: var(--surface-container-high) !important; color: var(--on-surface) !important; }}
[data-baseweb="popover"] li:hover {{ background: var(--surface-container-highest) !important; }}
[data-testid="stToggle"] label p {{ color: var(--on-surface-variant) !important; }}
[data-testid="stSpinner"] i {{ border-top-color: var(--primary-container) !important; }}
a {{ color: var(--primary-container); }}
hr {{ border-color: var(--border-hairline); }}
* {{ scrollbar-color: var(--surface-container-highest) transparent; }}
</style>
"""


def inject(st: object) -> None:
    st.markdown(build_css(), unsafe_allow_html=True)
