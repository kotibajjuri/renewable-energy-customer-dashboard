"""FRED API — economic indicators."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from src import config

logger = logging.getLogger(__name__)

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"


@dataclass
class FredSeries:
    series_id: str
    title: str
    observations: list[tuple[str, float | None]]


def fetch_observations(series_id: str, limit: int = 120) -> FredSeries | None:
    key = config.FRED_API_KEY
    if not key:
        return None
    params = {
        "api_key": key,
        "series_id": series_id,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    try:
        r = requests.get(FRED_OBS_URL, params=params, timeout=30)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("FRED fetch failed: %s", e)
        return None

    obs_raw = payload.get("observations") or []
    obs: list[tuple[str, float | None]] = []
    for o in obs_raw:
        d = o.get("date")
        val = o.get("value")
        if val in (".", None):
            obs.append((str(d), None))
        else:
            try:
                obs.append((str(d), float(val)))
            except (TypeError, ValueError):
                obs.append((str(d), None))
    return FredSeries(series_id=series_id, title=series_id, observations=obs)


# Effective Federal Funds Rate (monthly)
FRED_SERIES_FEDFUNDS = "FEDFUNDS"
