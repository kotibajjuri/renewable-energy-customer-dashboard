# Planning Document

> Complete this document **before writing any code**. This is part of the evaluation.
> Your intent here will be compared against what you actually built in `docs/architecture.md`.

---

## Tech Stack

**Framework / Language:** Python + Streamlit

> Why did you choose this stack?
<li>Python is well suited to numeric modeling and public data integration, and it keeps the implementation simple.</li>
<li>Streamlit makes it fast to build an interactive dashboard with tabs, charts, and stateful UI without a complex frontend stack.</li>
<li>The project needs live data, calculations, mapping, and an AI chat interface, and Streamlit supports all of those through Python libraries.</li>

**Key Libraries:**
<li>Pandas / NumPy: data cleaning, calculations, scenario modeling</li>
<li>Plotly: interactive time series, bar charts, and financial visualizations</li>
<li>Requests: public API calls to EIA, FRED, NREL, or similar</li>
<li>Folium / Streamlit-Leaflet: interactive geographic visualizations</li>
<li>OpenAI: conversational AI research assistant with context grounding</li>

**AI Provider:** OpenAI GPT-4 (via API)

> Which AI provider are you using and why?

OpenAI is the provider of choice because it offers a reliable conversational model with strong prompt engineering support and easy Python integration. I will use it for the Research Assistant tab, feeding it current market data and project inputs so responses are grounded in live data rather than only training knowledge.

---

## Phases & Priorities

> How are you breaking the time before the April 12 deadline into phases? What are you building first and why?

| Phase | Target Dates | Goals |
|-------|-------------|-------|
| 1 | Apr 7 - Apr 8 | Set up the app shell, API clients, and Market Overview tab. Confirm data sources and fetch at least one live metric from EIA/FRED. Build the initial map layout and state handling. |
| 2 | Apr 9 - Apr 10 | Build the Project Economics Calculator with editable inputs, financial outputs, scenario support, and responsive charts. Wire the map and market data to support a location-aware workflow. |
| 3 | Apr 11 - Apr 12 | Add the AI Research Assistant with data-context injection, complete the Geographic Visualization, polish UI, test edge cases, deploy the app, and write docs/reflection. |

I am building the Market Overview and data ingestion first because the rest of the dashboard depends on having verified live numbers and API connectivity in place.

---

## What I'll Cut If Time Is Short

> Be honest. What's the first thing you'd drop, and what's the last?

- First to drop: advanced export/report generation (PDF/PowerPoint/Excel).
- Next to drop: a second project type or a full wind project calculator. I will focus on one reliable renewable case (solar) rather than support both solar and wind.
- Last to drop: the core Research Assistant or the map interactivity. If absolutely necessary, I will keep the AI Q&A minimal but still grounded with at least one contextual data source.

---

## Open Questions / Risks

> Any uncertainties or technical risks you've identified upfront?

- API availability and rate limits for EIA/NREL/FRED. I need to verify access quickly and fall back to a second public source if one API is unavailable.
- Deployment environment variables for API keys. I must avoid committing keys and make sure the platform supports secure secret injection.
- AI prompt design and data grounding. The most important risk is ensuring the research assistant answers based on current data instead of hallucinating.
- Time risk around the map layer. Interactive geographic overlays can take extra time, so I will keep the map simple and data-driven first.

