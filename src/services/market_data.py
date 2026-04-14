"""Aggregate EIA + FRED into a market snapshot for UI and AI context."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from src import config
from src.api import eia_client, fred_client


@dataclass
class MarketSnapshot:
    ok: bool
    errors: list[str] = field(default_factory=list)
    retail_price_series: list[tuple[str, float | None]] = field(default_factory=list)
    retail_price_latest: float | None = None
    retail_period: str | None = None
    solar_gen_series: list[tuple[str, float | None]] = field(default_factory=list)
    wind_gen_series: list[tuple[str, float | None]] = field(default_factory=list)
    solar_yoy_growth: float | None = None
    wind_yoy_growth: float | None = None
    fed_funds_latest: float | None = None
    fed_funds_period: str | None = None
    state_prices: dict[str, float] = field(default_factory=dict)


def _yoy_growth(obs: list[tuple[str, float | None]], months: int = 12) -> float | None:
    vals = [v for _, v in obs if v is not None]
    if len(vals) < months + 1:
        return None
    recent = vals[0]
    prior = vals[months]
    if prior == 0:
        return None
    return (recent - prior) / prior * 100.0


def build_snapshot() -> MarketSnapshot:
    err: list[str] = []
    snap = MarketSnapshot(ok=False, errors=err)

    if not config.EIA_API_KEY:
        err.append("EIA_API_KEY is not set — add it to use live EIA data.")

    if not config.FRED_API_KEY:
        err.append("FRED_API_KEY is not set — federal funds rate will be unavailable.")

    # --- fire all API calls in parallel ---
    def _fetch_retail():
        return eia_client.fetch_series(
            eia_client.SERIES_RETAIL_PRICE_US, normalize_cents_to_usd=True
        )

    def _fetch_solar():
        return eia_client.fetch_series(eia_client.SERIES_SOLAR_GEN)

    def _fetch_wind():
        return eia_client.fetch_series(eia_client.SERIES_WIND_GEN)

    def _fetch_fred():
        if not config.FRED_API_KEY:
            return None
        return fred_client.fetch_observations(fred_client.FRED_SERIES_FEDFUNDS)

    def _fetch_state_prices():
        return eia_client.fetch_state_retail_prices_latest()

    futures_map = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures_map["retail"] = pool.submit(_fetch_retail)
        futures_map["solar"] = pool.submit(_fetch_solar)
        futures_map["wind"] = pool.submit(_fetch_wind)
        futures_map["fred"] = pool.submit(_fetch_fred)
        futures_map["states"] = pool.submit(_fetch_state_prices)
        results = {name: f.result() for name, f in futures_map.items()}

    # --- unpack results ---
    price = results["retail"]
    if price and price.observations:
        snap.retail_price_series = list(reversed(price.observations))
        latest = next((v for _, v in price.observations if v is not None), None)
        snap.retail_price_latest = latest
        snap.retail_period = price.observations[0][0] if price.observations else None
    elif config.EIA_API_KEY:
        err.append("Could not load EIA retail price series.")

    solar = results["solar"]
    if solar and solar.observations:
        snap.solar_gen_series = list(reversed(solar.observations))
        snap.solar_yoy_growth = _yoy_growth(solar.observations)

    wind = results["wind"]
    if wind and wind.observations:
        snap.wind_gen_series = list(reversed(wind.observations))
        snap.wind_yoy_growth = _yoy_growth(wind.observations)

    ff = results["fred"]
    if ff and ff.observations:
        for d, v in ff.observations:
            if v is not None:
                snap.fed_funds_latest = v
                snap.fed_funds_period = d
                break
    elif config.FRED_API_KEY:
        err.append("Could not load FRED federal funds series.")

    sp = results["states"]
    if sp:
        snap.state_prices = sp

    snap.ok = bool(
        snap.retail_price_latest is not None
        or snap.solar_gen_series
        or snap.state_prices
    )
    return snap


def snapshot_to_prompt_block(s: MarketSnapshot) -> str:
    """Compact text for AI grounding."""
    lines = ["## Verified market data (from public APIs)"]
    if s.retail_price_latest is not None and s.retail_period:
        lines.append(
            f"- U.S. average retail electricity price: ${s.retail_price_latest:.4f}/kWh (EIA, period {s.retail_period})."
        )
    if s.solar_yoy_growth is not None:
        lines.append(
            f"- Solar net generation YoY (approx., monthly series): {s.solar_yoy_growth:.2f}%."
        )
    if s.wind_yoy_growth is not None:
        lines.append(
            f"- Wind net generation YoY (approx., monthly series): {s.wind_yoy_growth:.2f}%."
        )
    if s.fed_funds_latest is not None and s.fed_funds_period:
        lines.append(
            f"- Effective federal funds rate (FRED {fred_client.FRED_SERIES_FEDFUNDS}): {s.fed_funds_latest:.2f}% as of {s.fed_funds_period}."
        )
    lines.append(
        "- Sources: U.S. EIA Open Data (electricity retail and generation series), FRED (macro rates)."
    )
    return "\n".join(lines)


def dashboard_context_block(
    s: MarketSnapshot,
    selected_state_id: str,
    state_name: str,
) -> str:
    """
    Single block the model must use for 'this dashboard', 'my app', and on-screen numbers.
    """
    lines: list[str] = [
        "## DASHBOARD_CONTEXT (authoritative — use these exact values when the user asks about this app or on-screen numbers)",
        "### Market Overview tab (latest loaded snapshot)",
    ]
    if s.retail_price_latest is not None and s.retail_period:
        lines.append(
            f"- U.S. average retail electricity price shown on dashboard: **${s.retail_price_latest:.4f}/kWh** (as of EIA period {s.retail_period})."
        )
    else:
        lines.append("- U.S. average retail price: not loaded (refresh market data or check EIA key).")
    if s.solar_yoy_growth is not None:
        lines.append(f"- Solar generation YoY (approx.): **{s.solar_yoy_growth:.2f}%**.")
    if s.wind_yoy_growth is not None:
        lines.append(f"- Wind generation YoY (approx.): **{s.wind_yoy_growth:.2f}%**.")
    if s.fed_funds_latest is not None and s.fed_funds_period:
        lines.append(
            f"- Fed funds rate (FRED): **{s.fed_funds_latest:.2f}%** (as of {s.fed_funds_period})."
        )

    lines.append("### Geography tab (selected state)")
    lines.append(f"- Selected state code: **{selected_state_id}** ({state_name}).")
    if s.state_prices and selected_state_id in s.state_prices:
        lines.append(
            f"- EIA average retail price for this state (all sectors, latest in batch): **${s.state_prices[selected_state_id]:.4f}/kWh**."
        )
    else:
        lines.append("- State retail price for selection: not available until data loads.")

    lines.append(
        "When the user asks 'what does the dashboard show', 'what is my retail price', or similar, "
        "quote numbers from this block and the PROJECT ECONOMICS block below."
    )
    return "\n".join(lines)
