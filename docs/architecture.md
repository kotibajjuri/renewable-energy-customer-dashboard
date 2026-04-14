# Architecture Overview

This document reflects the current implementation.

---

## Final Tech Stack

- **Python 3** with **Streamlit** for the multi-tab dashboard and session state.
- **Plotly** for time series and financial bar charts.
- **Folium** + **streamlit-folium** for the U.S. state map overlay.
- **Requests** for **EIA Open Data** (v1 series + v2 retail by state) and **FRED** observations.
- **OpenAI** (`gpt-4o-mini`) for the Research Assistant with injected API context.
- **NumPy** + **numpy-financial** for IRR/NPV and project cash flows.
- **`concurrent.futures.ThreadPoolExecutor`** for parallel API fetching.

The planning document mentioned CrewAI; the shipped build uses direct OpenAI chat completions with explicit grounding blocks to keep latency and dependencies lower while still meeting the “grounded AI + citations” requirement.

---

## Folder Structure

```
cdf-renewable-energy-inverstor/
├── streamlit_app.py       # Entry point — run: streamlit run streamlit_app.py
├── requirements.txt
└── src/
    ├── __init__.py
    ├── config.py              # Environment-driven API keys (dotenv)
    ├── api/
    │   ├── __init__.py
    │   ├── eia_client.py      # EIA v1 series + v2 state retail prices
    │   └── fred_client.py     # FRED series observations
    ├── data/
    │   ├── __init__.py
    │   └── state_centroids.py # State center coordinates for map markers
    └── services/
        ├── __init__.py
        ├── economics.py       # Solar project model (IRR, NPV, LCOE, scenarios)
        └── market_data.py     # MarketSnapshot + parallel fetch + AI grounding text
```
---

## Data Loading & Caching

All five external API calls are fired in parallel via `ThreadPoolExecutor(max_workers=5)` inside `market_data.build_snapshot()`:

| Worker | Source | Data |
|--------|--------|------|
| `_fetch_retail` | EIA v1/v2 | U.S. average retail electricity price (monthly series) |
| `_fetch_solar` | EIA v2 operational | U.S. solar net generation (monthly) |
| `_fetch_wind` | EIA v2 operational | U.S. wind net generation (monthly) |
| `_fetch_state_prices` | EIA v2 retail | Latest retail price per state |
| `_fetch_fred` | FRED | Effective federal funds rate |

The result is wrapped in `@st.cache_data(ttl=3600)` in `streamlit_app.py`, so:
- Subsequent page loads and new users share the cached snapshot instantly.
- The cache auto-expires after 1 hour.
- The **Refresh market data** button calls `_cached_snapshot.clear()` to force a fresh fetch on demand.

---

## UI Layout

The "Refresh market data" button sits inline with the page title in a two-column layout (`[4, 1]`), aligned to the top-right. The sidebar is collapsed by default.

```
[ U.S. Renewable Energy Investment Dashboard ]  [ Refresh market data ▶ ]
Live market data, solar investment modeling, and AI research support…

[ Market Overview | Project Economics | Research AI Assistant | Geography ]
```

---

## Cross-Tab Data Flow

1. **Geography → Project Economics** — `st.session_state.selected_state_id` is set from the state selector on the Geography tab. The calculator’s **Apply retail rate from selected state** button copies that state’s latest EIA average retail price (`$/kWh`) into the Base-case selling rate, which then flows into Optimistic/Conservative via `scenario_presets`.

2. **Market Overview ↔ Project Economics** — After each model run, `st.session_state.last_econ_results` stores LCOE and equity IRR. **Market Overview** displays those headline metrics so the “sample project” view stays tied to the calculator without a server round trip.

3. **Project Economics + Market → Research Assistant** — Each completion request prepends a system message containing `snapshot_to_prompt_block(market_snapshot)` (EIA/FRED numbers) and a block describing the active scenario inputs and last run metrics, so answers can reference the same figures the user sees on other tabs.

---

## AI Integration Design

- **Context:** Verified text built from `MarketSnapshot` (EIA retail price, solar/wind YoY from monthly series, FRED federal funds) plus the active calculator parameters and last IRR/NPV/LCOE. Combined context is capped at 6,000 characters.
- **History:** Last 6 turns of `st.session_state.chat_messages` sent per request (cost guard).
- **Completion cap:** `max_completion_tokens=512`.
- **Boundary:** The system prompt instructs the model to use only that context for numeric market claims, to cite EIA/FRED by name, and not to invent URLs.
- **Session:** `st.session_state.chat_messages` holds the conversation until the user clicks **Clear conversation**.

---

## What Changed From the Plan

- **CrewAI** was not used; direct OpenAI calls with structured grounding were sufficient for Tier 1.
- **`src/app.py`** was removed; `streamlit_app.py` at the repo root is the sole entry point.
- **Parallel API fetching** (`ThreadPoolExecutor`) was added to reduce load time from ~10 s (sequential) to ~the latency of the single slowest call.
- **`@st.cache_data(ttl=3600)`** was added so repeated loads and new users skip the network round trip.
- **Refresh button** was moved from the sidebar to inline with the page title (top-right), and the sidebar was collapsed.
- **Deployment** is intended to be Streamlit-friendly (Community Cloud or similar); the README documents env vars and local run.
