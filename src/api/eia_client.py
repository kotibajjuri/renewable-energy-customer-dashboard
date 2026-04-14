"""EIA Open Data API v1 (series) and v2 (retail by state) helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from src import config

logger = logging.getLogger(__name__)

EIA_SERIES_URL = "https://api.eia.gov/series/"
EIA_V2_RETAIL = "https://api.eia.gov/v2/electricity/retail-sales/data/"
EIA_V2_OPER = "https://api.eia.gov/v2/electricity/electric-power-operational-data/data/"


def _usd_per_kwh(raw: float | None) -> float | None:
    """EIA retail series often report cents/kWh; normalize to USD/kWh."""
    if raw is None:
        return None
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return None
    if x > 2.0:
        return x / 100.0
    return x


@dataclass
class SeriesResult:
    series_id: str
    name: str
    units: str
    observations: list[tuple[str, float | None]]  # (period, value)


def _rows_to_series_result(
    series_id: str,
    name: str,
    units: str,
    rows: list[dict[str, Any]],
    value_field: str,
    normalize_cents_to_usd: bool = False,
) -> SeriesResult:
    obs: list[tuple[str, float | None]] = []
    for row in rows:
        period = str(row.get("period", ""))
        raw = row.get(value_field)
        try:
            value = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            value = None
        if normalize_cents_to_usd:
            value = _usd_per_kwh(value)
        obs.append((period, value))
    return SeriesResult(series_id=series_id, name=name, units=units, observations=obs)


def fetch_us_retail_price_monthly(num_rows: int = 240) -> SeriesResult | None:
    """EIA v2 fallback for U.S. average retail electricity price (ALL sectors)."""
    key = config.EIA_API_KEY
    if not key:
        return None
    params: dict[str, Any] = {
        "api_key": key,
        "frequency": "monthly",
        "data[0]": "price",
        "facets[sectorid][]": "ALL",
        "facets[stateid][]": "US",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": num_rows,
    }
    try:
        r = requests.get(EIA_V2_RETAIL, params=params, timeout=30)
        r.raise_for_status()
        rows = (r.json().get("response") or {}).get("data") or []
    except (requests.RequestException, ValueError) as e:
        logger.warning("EIA retail v2 US fetch failed: %s", e)
        return None
    if not rows:
        return None
    return _rows_to_series_result(
        series_id=SERIES_RETAIL_PRICE_US,
        name="U.S. Average Retail Electricity Price (ALL sectors, monthly)",
        units="USD/kWh",
        rows=rows,
        value_field="price",
        normalize_cents_to_usd=True,
    )


def fetch_us_generation_monthly(fueltypeid: str, num_rows: int = 240) -> SeriesResult | None:
    """EIA v2 fallback for U.S. monthly net generation by fuel."""
    key = config.EIA_API_KEY
    if not key:
        return None
    params: dict[str, Any] = {
        "api_key": key,
        "frequency": "monthly",
        "data[0]": "generation",
        "facets[location][]": "US",
        "facets[sectorid][]": "99",  # All sectors
        "facets[fueltypeid][]": fueltypeid,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": num_rows,
    }
    try:
        r = requests.get(EIA_V2_OPER, params=params, timeout=30)
        r.raise_for_status()
        rows = (r.json().get("response") or {}).get("data") or []
    except (requests.RequestException, ValueError) as e:
        logger.warning("EIA operational v2 fetch failed (%s): %s", fueltypeid, e)
        return None
    if not rows:
        return None
    label = "Solar" if fueltypeid in ("SUN", "TSN") else "Wind"
    series_id = SERIES_SOLAR_GEN if label == "Solar" else SERIES_WIND_GEN
    return _rows_to_series_result(
        series_id=series_id,
        name=f"U.S. Net Generation ({label}, monthly)",
        units="thousand MWh",
        rows=rows,
        value_field="generation",
    )


def fetch_series(
    series_id: str, num_rows: int = 240, *, normalize_cents_to_usd: bool = False
) -> SeriesResult | None:
    """Fetch a v1 time series (monthly data)."""
    key = config.EIA_API_KEY
    if not key:
        return None
    params = {"api_key": key, "series_id": series_id}
    try:
        r = requests.get(EIA_SERIES_URL, params=params, timeout=30)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as e:
        # EIA v1 series route may be unavailable for some API keys; known series fall back to v2.
        if isinstance(e, requests.HTTPError) and getattr(e.response, "status_code", None) == 404:
            logger.info("EIA v1 series not available for %s; trying v2 fallback.", series_id)
        else:
            logger.warning("EIA series fetch failed: %s", e)
        if series_id == SERIES_RETAIL_PRICE_US:
            return fetch_us_retail_price_monthly(num_rows=num_rows)
        if series_id == SERIES_SOLAR_GEN:
            return fetch_us_generation_monthly("SUN", num_rows=num_rows)
        if series_id == SERIES_WIND_GEN:
            return fetch_us_generation_monthly("WND", num_rows=num_rows)
        return None

    series_list = payload.get("series") or []
    if not series_list:
        if series_id == SERIES_RETAIL_PRICE_US:
            return fetch_us_retail_price_monthly(num_rows=num_rows)
        if series_id == SERIES_SOLAR_GEN:
            return fetch_us_generation_monthly("SUN", num_rows=num_rows)
        if series_id == SERIES_WIND_GEN:
            return fetch_us_generation_monthly("WND", num_rows=num_rows)
        return None
    s0 = series_list[0]
    raw = s0.get("data") or []
    trimmed = raw[:num_rows]
    obs: list[tuple[str, float | None]] = []
    for row in trimmed:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        period, val = row[0], row[1]
        try:
            fval = float(val) if val is not None else None
        except (TypeError, ValueError):
            fval = None
        if normalize_cents_to_usd:
            fval = _usd_per_kwh(fval)
        obs.append((str(period), fval))
    return SeriesResult(
        series_id=series_id,
        name=s0.get("name", series_id),
        units=s0.get("units", ""),
        observations=obs,
    )


def fetch_state_retail_prices_latest() -> dict[str, float] | None:
    """
    Latest monthly average retail price ($/kWh) by state (all sectors).
    Returns state_id -> price.
    """
    key = config.EIA_API_KEY
    if not key:
        return None
    params: dict[str, Any] = {
        "api_key": key,
        "frequency": "monthly",
        "data[0]": "price",
        "facets[sectorid][]": "ALL",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    try:
        r = requests.get(EIA_V2_RETAIL, params=params, timeout=45)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("EIA retail v2 fetch failed: %s", e)
        return None

    rows = (payload.get("response") or {}).get("data") or []
    latest_by_state: dict[str, tuple[str, float]] = {}
    for row in rows:
        sid = row.get("stateid")
        period = row.get("period")
        price = row.get("price")
        if not sid or price is None:
            continue
        try:
            p = _usd_per_kwh(float(price))
        except (TypeError, ValueError):
            continue
        if p is None:
            continue
        if sid not in latest_by_state:
            latest_by_state[sid] = (str(period), p)
        else:
            cur_p = latest_by_state[sid][0]
            if str(period) > cur_p:
                latest_by_state[sid] = (str(period), p)

    return {k: v[1] for k, v in latest_by_state.items()}


# Common series IDs (monthly, US total)
SERIES_RETAIL_PRICE_US = "ELEC.PRICE.US-ALL.M"
SERIES_SOLAR_GEN = "ELEC.GEN.SUN-99-1.M"  # Net solar generation, thousand MWh
SERIES_WIND_GEN = "ELEC.GEN.WND-99-1.M"  # Net wind generation, thousand MWh
