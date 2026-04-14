"""
U.S. Renewable Energy Investment Dashboard — Tier 1 (Streamlit).
Run from repo root: streamlit run streamlit_app.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

# Allow `from src...` when running via Streamlit from the repo root
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from openai import APIConnectionError, APIStatusError, AzureOpenAI, AuthenticationError, OpenAI, RateLimitError

from src import config
from src.data.state_centroids import STATE_CENTROIDS, STATE_NAMES
from src.services import economics, market_data

# Cost guards for assistant calls (higher limits so dashboard numeric Q&A fits in context + reply)
MAX_CHAT_HISTORY_FOR_API = 10  # last N turns only
MAX_CTX_CHARS = 10000
MAX_COMPLETION_TOKENS = 5000

# --- Page ---
st.set_page_config(
    page_title="Renewable Energy Investment Dashboard",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _init_session() -> None:
    if "market_snapshot" not in st.session_state:
        st.session_state.market_snapshot = None
    if "selected_state_id" not in st.session_state:
        st.session_state.selected_state_id = "CA"
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "base_inputs" not in st.session_state:
        st.session_state.base_inputs = economics.ProjectInputs()
    if "calc_inputs" not in st.session_state:
        st.session_state.calc_inputs = economics.ProjectInputs()
    if "active_scenario" not in st.session_state:
        st.session_state.active_scenario = "Base"
    if "last_econ_results" not in st.session_state:
        st.session_state.last_econ_results = None


def _ensure_snapshot():
    if st.session_state.market_snapshot is None:
        st.session_state.market_snapshot = _cached_snapshot()


@st.cache_data(ttl=3600, show_spinner="Loading market data…")
def _cached_snapshot():
    return market_data.build_snapshot()


def _extract_assistant_text(choice) -> str:
    """Best-effort text extraction across possible SDK response shapes."""
    msg = getattr(choice, "message", None)
    if msg is None:
        return ""

    content = getattr(msg, "content", None)
    if isinstance(content, str):
        txt = content.strip()
        if txt:
            return txt

    # Some SDK/model variants may return content as structured parts.
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                t = item.get("text") or item.get("content")
                if isinstance(t, str):
                    parts.append(t)
        txt = "\n".join([p.strip() for p in parts if p and p.strip()]).strip()
        if txt:
            return txt

    refusal = getattr(msg, "refusal", None)
    if isinstance(refusal, str) and refusal.strip():
        return f"Model refusal: {refusal.strip()}"

    return ""


_init_session()
_ensure_snapshot()

if st.session_state.get("last_econ_results") is None:
    presets = economics.scenario_presets(st.session_state.base_inputs)
    inp = presets.get(st.session_state.active_scenario, presets["Base"])
    st.session_state.calc_inputs = inp
    st.session_state.last_econ_results = economics.run_model(inp)

snap = st.session_state.market_snapshot

# --- Title + Refresh ---
_title_col, _btn_col = st.columns([4, 1])
with _title_col:
    st.title("U.S. Renewable Energy Investment Dashboard")
with _btn_col:
    st.write("")  # vertical alignment nudge
    if st.button("Refresh market data", type="primary", use_container_width=True):
        _cached_snapshot.clear()
        st.session_state.market_snapshot = None
        st.rerun()

if snap and snap.errors:
    for e in snap.errors:
        st.warning(e)
st.caption(
    "Live market data, solar investment modeling, and AI research support for renewable energy decisions."
)

tab1, tab2, tab3, tab4 = st.tabs(
    ["Market Overview", "Project Economics", "Research AI Assistant", "Geography"]
)

# ----- Tab 1: Market Overview -----
with tab1:
    st.subheader("Market Overview")
    if snap and snap.errors and not snap.ok:
        st.info("Add API keys in `.env` or hosting secrets to load live figures.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        p = snap.retail_price_latest if snap else None
        st.metric(
            "U.S. avg retail price (latest)",
            f"${p:.4f}/kWh" if p is not None else "—",
            help="EIA series ELEC.PRICE.US-ALL.M (normalized to $/kWh)",
        )
    with c2:
        sg = snap.solar_yoy_growth if snap else None
        st.metric(
            "Solar net gen. YoY (approx.)",
            f"{sg:.1f}%" if sg is not None else "—",
            help="From EIA monthly solar generation series (YoY vs 12 months prior)",
        )
    with c3:
        wg = snap.wind_yoy_growth if snap else None
        st.metric(
            "Wind net gen. YoY (approx.)",
            f"{wg:.1f}%" if wg is not None else "—",
            help="From EIA monthly wind generation series",
        )
    with c4:
        ff = snap.fed_funds_latest if snap else None
        st.metric(
            "Fed funds rate (latest)",
            f"{ff:.2f}%" if ff is not None else "—",
            help="FRED series FEDFUNDS",
        )

    # Cross-tab: calculator outputs
    st.divider()
    st.markdown("**Linked from Project Economics** (updates when you run the calculator)")
    lr = st.session_state.last_econ_results
    cc1, cc2 = st.columns(2)
    with cc1:
        if lr and lr.get("lcoe_per_kwh") is not None and not math.isnan(lr["lcoe_per_kwh"]):
            st.metric("Sample project LCOE (current inputs)", f"${lr['lcoe_per_kwh']:.4f}/kWh")
        else:
            st.metric("Sample project LCOE (current inputs)", "—")
    with cc2:
        if lr and lr.get("irr") is not None and not math.isnan(lr["irr"]):
            st.metric("Sample project equity IRR (current inputs)", f"{lr['irr']*100:.2f}%")
        else:
            st.metric("Sample project equity IRR (current inputs)", "—")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Retail electricity price (U.S. average)**")
        if snap and snap.retail_price_series:
            df = pd.DataFrame(snap.retail_price_series, columns=["period", "price"])
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["period"],
                    y=df["price"],
                    mode="lines",
                    name="$/kWh",
                )
            )
            fig.update_layout(
                height=360,
                margin=dict(l=10, r=10, t=30, b=10),
                yaxis_title="USD/kWh",
                xaxis_title="Period",
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No EIA retail price series loaded.")

    with col_b:
        st.markdown("**Solar vs wind net generation (monthly)**")
        if snap and (snap.solar_gen_series or snap.wind_gen_series):
            fig2 = go.Figure()
            if snap.solar_gen_series:
                ds = pd.DataFrame(snap.solar_gen_series, columns=["period", "mwh"])
                fig2.add_trace(
                    go.Scatter(
                        x=ds["period"],
                        y=ds["mwh"],
                        name="Solar (thousand MWh)",
                        mode="lines",
                    )
                )
            if snap.wind_gen_series:
                dw = pd.DataFrame(snap.wind_gen_series, columns=["period", "mwh"])
                fig2.add_trace(
                    go.Scatter(
                        x=dw["period"],
                        y=dw["mwh"],
                        name="Wind (thousand MWh)",
                        mode="lines",
                    )
                )
            fig2.update_layout(
                height=360,
                margin=dict(l=10, r=10, t=30, b=10),
                yaxis_title="Thousand MWh",
            )
            st.plotly_chart(fig2, width="stretch")
        else:
            st.info("No EIA generation series loaded.")

# ----- Tab 2: Project Economics -----
with tab2:
    st.subheader("Project Economics (solar)")
    st.caption(
        "All metrics are computed in your browser session — inputs recalculate instantly. "
        "Edits apply to the **Base** case; Optimistic / Conservative are derived from Base."
    )

    base = st.session_state.base_inputs
    scenario = st.radio(
        "Scenario",
        options=["Base", "Optimistic", "Conservative"],
        horizontal=True,
        key="scenario_radio",
    )
    st.session_state.active_scenario = scenario

    ci1, ci2 = st.columns(2)
    with ci1:
        base.system_size_kw = st.number_input(
            "System size (kW)",
            min_value=1.0,
            max_value=500_000.0,
            value=float(base.system_size_kw),
            step=10.0,
        )
        base.capacity_factor = st.slider(
            "Capacity factor", 0.10, 0.45, float(base.capacity_factor), 0.01
        )
        base.degradation_annual = st.number_input(
            "Annual degradation", 0.0, 0.02, float(base.degradation_annual), 0.001
        )
        base.install_cost_per_w = st.number_input(
            "Installation cost ($/W)", 0.5, 3.0, float(base.install_cost_per_w), 0.05
        )
        base.om_per_kw_year = st.number_input(
            "O&M ($/kW-yr)", 0.0, 80.0, float(base.om_per_kw_year), 1.0
        )
    with ci2:
        base.electricity_rate_per_kwh = st.number_input(
            "Electricity selling rate ($/kWh)",
            0.01,
            0.35,
            float(base.electricity_rate_per_kwh),
            0.005,
        )
        if st.button("Apply retail rate from selected state (Geography tab)"):
            sid = st.session_state.selected_state_id
            prices = snap.state_prices if snap else {}
            if sid in prices:
                base.electricity_rate_per_kwh = prices[sid]
                st.success(
                    f"Set Base rate to ${prices[sid]:.4f}/kWh for {STATE_NAMES.get(sid, sid)} ({sid})."
                )
            else:
                st.warning("No EIA retail price for that state — refresh data or pick another state.")

        base.revenue_escalation = st.number_input(
            "Annual revenue escalation", 0.0, 0.08, float(base.revenue_escalation), 0.005
        )
        base.om_escalation = st.number_input(
            "Annual O&M escalation", 0.0, 0.08, float(base.om_escalation), 0.005
        )
        base.debt_pct = st.slider("Debt fraction of CAPEX", 0.0, 0.85, float(base.debt_pct), 0.01)
        base.interest_rate = st.number_input(
            "Interest rate (annual)", 0.0, 0.20, float(base.interest_rate), 0.005
        )
        base.term_years = st.number_input("Debt term (years)", 1, 30, int(base.term_years), 1)
        base.itc_pct = st.slider("Federal ITC (fraction)", 0.0, 0.50, float(base.itc_pct), 0.01)
        base.discount_rate = st.number_input(
            "Discount rate for NPV/LCOE", 0.03, 0.20, float(base.discount_rate), 0.005
        )

    presets = economics.scenario_presets(base)
    inp = presets[scenario]
    st.session_state.calc_inputs = inp

    res = economics.run_model(inp)
    st.session_state.last_econ_results = res

    o1, o2, o3, o4 = st.columns(4)
    with o1:
        st.metric("Total project CAPEX", f"${res['capex']:,.0f}")
    with o2:
        st.metric("Year 1 production (MWh)", f"{res['annual_energy_year1']/1000:,.1f}")
    with o3:
        irr = res["irr"]
        st.metric(
            "Equity IRR",
            f"{irr*100:.2f}%" if irr == irr else "—",
        )
    with o4:
        st.metric("NPV (equity, discounted)", f"${res['npv']:,.0f}")

    st.caption(
        f"Payback (simple cumulative equity): {res['payback_years']} years"
        if res["payback_years"]
        else "Payback: not reached in project life (under these assumptions)"
    )
    st.caption(
        f"LCOE (simplified, unlevered cost / discounted gen): ${res['lcoe_per_kwh']:.4f}/kWh"
        if res.get("lcoe_per_kwh") == res.get("lcoe_per_kwh")
        else ""
    )

    cf = pd.DataFrame(
        {
            "Year": res["years"],
            "Revenue": res["annual_revenue"],
            "O&M": res["annual_om"],
            "NOI": res["annual_noi"],
        }
    )
    fig_cf = go.Figure()
    fig_cf.add_trace(go.Bar(x=cf["Year"], y=cf["Revenue"], name="Revenue"))
    fig_cf.add_trace(go.Bar(x=cf["Year"], y=[-x for x in cf["O&M"]], name="O&M (negative)"))
    fig_cf.update_layout(barmode="relative", height=400, title="Annual revenue vs O&M")
    st.plotly_chart(fig_cf, width="stretch")

# ----- Tab 3: Research AI Assistant -----
with tab3:
    st.subheader("Research AI Assistant")

    dash_ctx = ""
    if snap:
        sid = st.session_state.selected_state_id
        sname = STATE_NAMES.get(sid, sid)
        dash_ctx = market_data.dashboard_context_block(snap, sid, sname)
    api_ctx = market_data.snapshot_to_prompt_block(snap) if snap else ""
    calc = st.session_state.calc_inputs
    calc_block = (
        f"## PROJECT ECONOMICS (scenario: {st.session_state.active_scenario})\n"
        f"- System size: **{calc.system_size_kw} kW**; capacity factor: **{calc.capacity_factor:.2%}**; "
        f"selling rate: **${calc.electricity_rate_per_kwh:.4f}/kWh**; ITC: **{calc.itc_pct:.0%}**; "
        f"debt: **{calc.debt_pct:.0%}** at **{calc.interest_rate:.2%}** for **{calc.term_years}** years; "
        f"install **${calc.install_cost_per_w:.2f}/W**; O&M **${calc.om_per_kw_year:.1f}/kW-yr**; "
        f"discount rate (NPV/LCOE): **{calc.discount_rate:.2%}**.\n"
    )
    if st.session_state.last_econ_results:
        r0 = st.session_state.last_econ_results
        irr_s = (
            f"{r0['irr']*100:.2f}%"
            if r0.get("irr") is not None and math.isfinite(r0["irr"])
            else "n/a"
        )
        lc = r0.get("lcoe_per_kwh")
        lc_s = f"{lc:.4f}" if lc is not None and isinstance(lc, (int, float)) and math.isfinite(lc) else "n/a"
        pb = r0.get("payback_years")
        pb_s = f"{pb} years" if pb else "not reached in model horizon"
        calc_block += (
            f"- **Last model run outputs** (what the Project Economics tab shows): "
            f"CAPEX **${r0['capex']:,.0f}**; year-1 energy **{r0['annual_energy_year1']/1000:,.1f} MWh**; "
            f"equity IRR **{irr_s}**; NPV **${r0['npv']:,.0f}**; LCOE **${lc_s}/kWh**; payback **{pb_s}**.\n"
        )
    else:
        calc_block += (
            "- **Last model run:** not yet computed — open **Project Economics** so metrics calculate, then ask again.\n"
        )

    combined_ctx = f"{dash_ctx}\n\n{api_ctx}\n\n{calc_block}"
    if len(combined_ctx) > MAX_CTX_CHARS:
        combined_ctx = combined_ctx[:MAX_CTX_CHARS] + "\n\n_(Context truncated — ask a focused question.)_"

    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if not config.OPENAI_API_KEY:
        st.warning(
            "Set `OPENAI_API_KEY` in the environment to enable the assistant. "
            "Never commit API keys to the repository."
        )
    else:
        prompt = st.chat_input("Ask about renewables, policy, or this dashboard's numbers…")
        if prompt:
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            system = (
                "You are an analyst assistant for a live Streamlit dashboard about U.S. renewable energy. "
                "The user may ask about numbers **shown on their screen** (Market Overview, Geography, Project Economics). "
                "For those questions, you MUST use the **DASHBOARD_CONTEXT** and **PROJECT ECONOMICS** sections below — "
                "quote the exact figures and units (e.g. $/kWh, %, MWh, $). "
                "Do NOT say you lack dashboard data if those sections contain the answer. "
                "For general industry questions without dashboard numbers, you may use your knowledge but must not invent "
                "specific current statistics; say to check EIA/FRED if needed. "
                "Cite **EIA** and **FRED** by name when using API-sourced figures. Do not fabricate URLs. "
                "Keep answers clear and concise."
            )
            recent_history = st.session_state.chat_messages[-MAX_CHAT_HISTORY_FOR_API:]
            messages_api = [{"role": "system", "content": system + "\n\n" + combined_ctx}] + [
                {"role": m["role"], "content": m["content"]} for m in recent_history
            ]

            if config.OPENAI_BASE_URL and ".openai.azure.com" in config.OPENAI_BASE_URL:
                client = AzureOpenAI(
                    azure_endpoint=config.OPENAI_BASE_URL.split("/openai")[0],
                    api_key=config.OPENAI_API_KEY,
                    api_version=config.OPENAI_API_VERSION,
                )
            else:
                client = OpenAI(
                    api_key=config.OPENAI_API_KEY,
                    **({"base_url": config.OPENAI_BASE_URL} if config.OPENAI_BASE_URL else {}),
                )
            try:
                create_kwargs = dict(
                    model=config.OPENAI_MODEL,
                    messages=messages_api,
                    max_completion_tokens=MAX_COMPLETION_TOKENS,
                )
                if not config.OPENAI_MODEL.startswith(("o1", "o3", "gpt-5")):
                    create_kwargs["temperature"] = 0.4
                resp = client.chat.completions.create(**create_kwargs)
                text = _extract_assistant_text(resp.choices[0])
                if not text:
                    finish = getattr(resp.choices[0], "finish_reason", None)
                    text = (
                        "I did not receive a text response from the model. "
                        f"(finish_reason={finish}) Please retry with a shorter question."
                    )
                st.session_state.chat_messages.append({"role": "assistant", "content": text})
                with st.chat_message("assistant"):
                    st.markdown(text)
            except AuthenticationError:
                msg = (
                    "OpenAI authentication failed. Please verify `OPENAI_API_KEY` in `.env` "
                    "and restart the app."
                )
                st.session_state.chat_messages.append({"role": "assistant", "content": msg})
                with st.chat_message("assistant"):
                    st.markdown(msg)
            except RateLimitError:
                msg = "OpenAI quota/rate limit reached (429). Check your API billing/quota and try again."
                st.session_state.chat_messages.append({"role": "assistant", "content": msg})
                with st.chat_message("assistant"):
                    st.markdown(msg)
            except APIConnectionError:
                msg = "Unable to reach OpenAI right now. Please check your network and retry."
                st.session_state.chat_messages.append({"role": "assistant", "content": msg})
                with st.chat_message("assistant"):
                    st.markdown(msg)
            except APIStatusError as e:
                msg = f"OpenAI request failed with status {e.status_code}. Please retry in a moment."
                st.session_state.chat_messages.append({"role": "assistant", "content": msg})
                with st.chat_message("assistant"):
                    st.markdown(msg)
            except Exception:
                msg = "The assistant hit an unexpected error. Please retry; if it continues, restart the app."
                st.session_state.chat_messages.append({"role": "assistant", "content": msg})
                with st.chat_message("assistant"):
                    st.markdown(msg)

    if st.button("Clear conversation"):
        st.session_state.chat_messages = []
        st.rerun()

# ----- Tab 4: Geography -----
with tab4:
    st.subheader("Geographic view — retail price by state")
    st.caption(
        "Markers use EIA state average retail price (all sectors, latest available month in batch). "
        "Selecting a state updates **session state** for the Project Economics tab."
    )

    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        folium = None
        st_folium = None

    prices = snap.state_prices if snap else {}
    if not prices:
        st.info("Load data with an EIA key and click **Refresh market data** to plot states.")
    elif folium is None:
        st.error("Install folium and streamlit-folium (see requirements.txt).")
    else:
        vals = list(prices.values())
        vmin, vmax = min(vals), max(vals)
        span = max(vmax - vmin, 1e-9)

        def color_for(p: float) -> str:
            t = (p - vmin) / span
            # green (low) -> red (high)
            r = int(255 * t)
            g = int(255 * (1 - t))
            return f"#{r:02x}{g:02x}40"

        m = folium.Map(location=[39.5, -98.35], zoom_start=4, tiles="CartoDB positron")
        for sid, price in prices.items():
            if sid not in STATE_CENTROIDS:
                continue
            lat, lon = STATE_CENTROIDS[sid]
            folium.CircleMarker(
                location=[lat, lon],
                radius=8 + 12 * (price - vmin) / span,
                color=color_for(price),
                fill=True,
                fill_opacity=0.75,
                popup=f"{STATE_NAMES.get(sid, sid)} ({sid}): ${price:.4f}/kWh",
            ).add_to(m)

        folium.LayerControl().add_to(m)
        if st_folium:
            st_folium(m, width=None, height=480, returned_objects=[])

        options = sorted(prices.keys(), key=lambda s: STATE_NAMES.get(s, s))
        idx = options.index(st.session_state.selected_state_id) if st.session_state.selected_state_id in options else 0
        choice = st.selectbox(
            "Selected state (feeds Project Economics)",
            options=options,
            index=idx,
            format_func=lambda s: f"{STATE_NAMES.get(s, s)} ({s}) — ${prices[s]:.4f}/kWh",
        )
        st.session_state.selected_state_id = choice

        st.markdown(
            "**Overlay:** circle size and color encode relative average retail price — "
            "compare regions at a glance. Click markers for exact values."
        )

st.divider()
st.markdown(
    "<div style='text-align:center; width:100%;'>"
    "Complete Streamlit folder for a ready-to-share U.S. renewables dashboard"
    "</div>",
    unsafe_allow_html=True,
)
