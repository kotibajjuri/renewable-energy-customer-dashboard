"""Client-side project economics for a utility-scale solar project."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import numpy_financial as npf


@dataclass
class ProjectInputs:
    system_size_kw: float = 5.0
    capacity_factor: float = 0.24
    degradation_annual: float = 0.005
    install_cost_per_w: float = 1.05
    om_per_kw_year: float = 15.0
    electricity_rate_per_kwh: float = 0.09
    revenue_escalation: float = 0.02
    om_escalation: float = 0.02
    debt_pct: float = 0.65
    interest_rate: float = 0.07
    term_years: int = 18
    itc_pct: float = 0.30
    project_life_years: int = 25
    discount_rate: float = 0.08


@dataclass
class ScenarioBundle:
    name: str
    inputs: ProjectInputs


def _annual_kwh(year_idx: int, inp: ProjectInputs) -> float:
    """year_idx 1-based."""
    deg = (1.0 - inp.degradation_annual) ** (year_idx - 1)
    return inp.system_size_kw * 8760.0 * inp.capacity_factor * deg


def run_model(inp: ProjectInputs) -> dict:
    """
    Returns annual series and headline metrics.
    All calculations are local (no server).
    """
    life = inp.project_life_years
    capex = inp.system_size_kw * 1000.0 * inp.install_cost_per_w
    itc_cash = capex * inp.itc_pct
    debt_principal = capex * inp.debt_pct
    equity_upfront = capex - itc_cash - debt_principal

    # Debt service (standard amortizing loan)
    if debt_principal > 0 and inp.term_years > 0:
        annual_debt = -npf.pmt(inp.interest_rate, inp.term_years, debt_principal)
    else:
        annual_debt = 0.0

    rev = []
    om = []
    kwh = []
    noi = []
    equity_cf = []

    for t in range(1, life + 1):
        kwh_t = _annual_kwh(t, inp)
        esc_r = (1.0 + inp.revenue_escalation) ** (t - 1)
        esc_o = (1.0 + inp.om_escalation) ** (t - 1)
        rev_t = kwh_t * inp.electricity_rate_per_kwh * esc_r
        om_t = inp.om_per_kw_year * inp.system_size_kw * esc_o
        noi_t = rev_t - om_t
        debt_t = annual_debt if t <= inp.term_years else 0.0
        eq_t = noi_t - debt_t

        kwh.append(kwh_t)
        rev.append(rev_t)
        om.append(om_t)
        noi.append(noi_t)
        equity_cf.append(eq_t)

    # Equity outflow at project close (t=0); operating cash to equity in years 1..N
    eq_arr = np.array([-equity_upfront] + equity_cf, dtype=float)
    try:
        irr = float(npf.irr(eq_arr))
    except (ValueError, FloatingPointError):
        irr = float("nan")

    disc_eq = np.array([(1.0 + inp.discount_rate) ** -t for t in range(0, life + 1)])
    npv = float(np.sum(eq_arr * disc_eq))

    disc = np.array([(1.0 + inp.discount_rate) ** -t for t in range(1, life + 1)])
    cum = np.cumsum(eq_arr)
    payback = None
    for i, c in enumerate(cum):
        if c >= 0:
            payback = i + 1
            break

    total_kwh_life = float(np.sum(kwh))
    total_cost_net = capex - itc_cash
    # Simple LCOE: (net capex + PV of O&M) / PV of generation, same discount
    pv_om = float(np.sum(np.array(om) * disc))
    pv_kwh = float(np.sum(np.array(kwh) * disc))
    lcoe = (total_cost_net + pv_om) / pv_kwh if pv_kwh > 0 else float("nan")

    return {
        "capex": capex,
        "itc_cash": itc_cash,
        "equity_upfront": equity_upfront,
        "debt_principal": debt_principal,
        "annual_energy_year1": kwh[0],
        "total_energy_life_mwh": total_kwh_life / 1000.0,
        "annual_revenue": rev,
        "annual_om": om,
        "annual_noi": noi,
        "equity_cash_flows": eq_arr.tolist(),
        "irr": irr,
        "npv": npv,
        "payback_years": payback,
        "lcoe_per_kwh": lcoe,
        "years": list(range(1, life + 1)),
    }


def scenario_presets(base: ProjectInputs) -> dict[str, ProjectInputs]:
    """Base, optimistic, conservative scenarios."""
    opt = replace(
        base,
        capacity_factor=min(0.32, base.capacity_factor * 1.12),
        electricity_rate_per_kwh=base.electricity_rate_per_kwh * 1.08,
        install_cost_per_w=base.install_cost_per_w * 0.95,
    )
    cons = replace(
        base,
        capacity_factor=max(0.18, base.capacity_factor * 0.88),
        electricity_rate_per_kwh=base.electricity_rate_per_kwh * 0.92,
        install_cost_per_w=base.install_cost_per_w * 1.08,
    )
    return {"Base": base, "Optimistic": opt, "Conservative": cons}
