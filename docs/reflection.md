# Reflection

## What I Built

### Tabs and Features

**Market Overview**
- Four live headline metrics pulled from public APIs: U.S. average retail electricity price (EIA), solar net generation YoY growth, wind net generation YoY growth, and the effective federal funds rate (FRED).
- Two interactive Plotly time-series charts: U.S. retail electricity price trend and solar vs. wind monthly net generation comparison.
- Cross-tab live metrics displaying the current scenario's LCOE and equity IRR, linked directly from the Project Economics tab without a server round trip.

**Project Economics**
- Full solar project financial model running entirely in the browser session using NumPy and numpy-financial.
- Inputs: system size, capacity factor, annual degradation, installation cost ($/W), O&M ($/kW-yr), electricity selling rate, revenue and O&M escalation rates, debt fraction, interest rate, debt term, federal ITC percentage, and discount rate.
- Three scenarios — Base, Optimistic, Conservative — derived automatically from the Base inputs via `scenario_presets`.
- Headline outputs: total CAPEX, year-1 production (MWh), equity IRR, NPV, LCOE (unlevered, discounted), and simple payback period.
- Annual revenue vs. O&M bar chart (Plotly, relative bar mode).
- "Apply retail rate from selected state" button wired to Geography tab session state.

**Research AI Assistant**
- OpenAI (`gpt-4o-mini`) chat interface with a grounding system prompt that injects live EIA/FRED figures and the active scenario's inputs and last model-run outputs (CAPEX, IRR, NPV, LCOE, payback).
- Cost guards: last 6 turns of history sent to API, context capped at 6,000 characters, completions capped at 512 tokens.
- Graceful error handling for authentication failures, rate limits, connection errors, and unexpected API responses.
- "Clear conversation" button to reset chat history.

**Geography**
- Folium map centered on the continental U.S. with circle markers for every state that has EIA retail price data.
- Marker radius and color encode relative average retail price (green = low, red = high).
- State selector dropdown that sets `selected_state_id` in session state, feeding the Project Economics tab's "Apply retail rate" button.

### Performance Improvements
- All five API calls (EIA retail, solar generation, wind generation, state prices, FRED) now run in parallel via `ThreadPoolExecutor`, reducing load time from ~10 seconds to roughly the latency of the single slowest call.
- `@st.cache_data(ttl=3600)` caches the market snapshot at the app level for one hour, so subsequent page loads and new users get results instantly. The "Refresh market data" button clears the cache on demand.

### What Works
- Full end-to-end flow: live data fetching → financial modeling → AI-grounded chat.
- Cross-tab data sharing via `st.session_state` (Geography → Economics → AI context).
- Graceful degradation when API keys are absent — the dashboard renders with placeholder dashes and informational banners rather than crashing.

### What Doesn't Work / Limitations
- EIA v1 series endpoint is deprecated for some API keys, requiring a v2 fallback with extra request logic.
- State map requires `folium` and `streamlit-folium`; the tab shows an error message if those packages are not installed.

---

## What I'd Do Differently

- **Persistent caching with a database or Redis** — `st.cache_data` is process-local. A Redis layer would let multiple Streamlit workers share one cached snapshot and avoid redundant API calls on cold starts.
- **Background refresh** — Schedule a background thread or cron job to pre-warm the cache before TTL expiry so users never see a slow load.
- **Wind project model** — The economics calculator is solar-only. Adding wind turbine parameters (hub height, rotor diameter, wind speed) and a separate model would make the dashboard more broadly useful.
- **Unit tests for `economics.run_model`** — The financial calculations are untested; adding pytest fixtures with known inputs/outputs would prevent regressions.

---

## AI Tools Used

- **GitHub Copilot (Claude Sonnet 4.6)** — Used throughout the session for:
  - Moving and restructuring UI components (relocating the "Refresh market data" button above the title, then aligning it to the right in a two-column layout).
  - Diagnosing the ~10-second load time and designing the parallel fetch solution using `ThreadPoolExecutor` plus `@st.cache_data`.