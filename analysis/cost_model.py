"""
Parameterised electricity cost model.

Usage:
    from cost_model import model_plan, annualise
    from tariffs import PLANS
    from nem12_parser import load_csv, DailyBuckets

    buckets = load_csv("meter_data.csv")
    result = model_plan(buckets, PLANS["GloBird ZEROHERO (Jul 2026)"])
    print(result)
"""

from __future__ import annotations

from dataclasses import dataclass
from nem12_parser import DailyBuckets, classify_tou, is_evening_export_window
from tariffs import TariffPlan


@dataclass
class PlanResult:
    plan_name: str
    data_days: int              # actual days of meter data
    annualised_days: int = 365  # days to project over (default 365)

    # Raw totals from meter data (annualised)
    import_peak_kwh: float = 0.0
    import_shoulder_kwh: float = 0.0
    import_offpeak_kwh: float = 0.0
    import_total_kwh: float = 0.0

    export_total_kwh: float = 0.0
    export_evening_kwh: float = 0.0        # within plan's evening FiT window
    export_evening_capped_kwh: float = 0.0 # after applying daily cap
    export_fit_window_kwh: float = 0.0     # within plan's FiT window (non-evening)

    # Cost components (annualised, $)
    cost_daily: float = 0.0
    cost_import_peak: float = 0.0
    cost_import_shoulder: float = 0.0
    cost_import_offpeak: float = 0.0
    cost_import_total: float = 0.0

    earnings_fit_evening: float = 0.0
    earnings_fit_base: float = 0.0
    earnings_fit_total: float = 0.0

    cost_subscription: float = 0.0
    net_annual_cost: float = 0.0

    notes: str = ""

    def __str__(self) -> str:
        sep = "-" * 60
        lines = [
            sep,
            f"  {self.plan_name}",
            sep,
            f"  Data: {self.data_days} days → annualised to {self.annualised_days} days",
            "",
            "  IMPORT",
            f"    Peak      ({self._pct(self.import_peak_kwh):>5.1f}%): "
            f"{self.import_peak_kwh:>7.0f} kWh  @ variable  = ${self.cost_import_peak:>7.2f}",
            f"    Shoulder  ({self._pct(self.import_shoulder_kwh):>5.1f}%): "
            f"{self.import_shoulder_kwh:>7.0f} kWh  @ variable  = ${self.cost_import_shoulder:>7.2f}",
            f"    Off-peak  ({self._pct(self.import_offpeak_kwh):>5.1f}%): "
            f"{self.import_offpeak_kwh:>7.0f} kWh  @ variable  = ${self.cost_import_offpeak:>7.2f}",
            f"    TOTAL                {self.import_total_kwh:>7.0f} kWh             = ${self.cost_import_total:>7.2f}",
            "",
            "  EXPORT",
            f"    Evening window        {self.export_evening_kwh:>7.0f} kWh (after cap: "
            f"{self.export_evening_capped_kwh:>5.0f} kWh)  = -${self.earnings_fit_evening:>6.2f}",
            f"    Other FiT window      {self.export_fit_window_kwh:>7.0f} kWh"
            f"                          = -${self.earnings_fit_base:>6.2f}",
            f"    TOTAL FiT earnings    {self.export_total_kwh:>7.0f} kWh             = -${self.earnings_fit_total:>6.2f}",
            "",
            "  FIXED",
            f"    Daily supply charge: ${self.cost_daily:>7.2f}/yr",
            f"    Subscription:        ${self.cost_subscription:>7.2f}/yr",
            "",
            f"  NET ANNUAL COST:  ${self.net_annual_cost:>8.2f}",
        ]
        if self.notes:
            lines.append(f"\n  Note: {self.notes}")
        lines.append(sep)
        return "\n".join(lines)

    def _pct(self, kwh: float) -> float:
        return 100 * kwh / self.import_total_kwh if self.import_total_kwh else 0.0


# ---------------------------------------------------------------------------
# Core modelling function
# ---------------------------------------------------------------------------

def model_plan(
    daily_buckets: dict[str, DailyBuckets],
    plan: TariffPlan,
    annualised_days: int = 365,
) -> PlanResult:
    """
    Compute net annual cost for a tariff plan against the provided meter data.

    The meter data covers `data_days` days; all costs are scaled to
    `annualised_days` (default 365).

    Critical modelling decisions:
    - GloBird's 11:00-14:00 $0 window is already baked into the parser's
      TOU classification (marked 'offpeak').  For plans without this window,
      that energy is re-classified as shoulder downstream using
      plan.has_midday_offpeak flag.
    - The evening FiT cap (e.g. GloBird 10 kWh/day) is applied per-day.
    - Export outside all FiT windows earns $0 (no floor FiT assumed unless
      explicitly set in fit_base and a FiT window is defined).
    """
    data_days = len(daily_buckets)
    if data_days == 0:
        raise ValueError("No daily buckets to model")

    scale = annualised_days / data_days

    r = PlanResult(
        plan_name=plan.name,
        data_days=data_days,
        annualised_days=annualised_days,
        notes=plan.notes,
    )

    for day, b in daily_buckets.items():
        # --- Import ---
        peak = b.import_peak
        shoulder = b.import_shoulder
        offpeak = b.import_offpeak

        # Re-classify midday offpeak as shoulder if plan doesn't have that window
        if not plan.has_midday_offpeak:
            # We can't perfectly split 11-14h from 00-7h here because they're
            # aggregated.  We need the raw per-interval re-classification.
            # For plans without midday offpeak, we use the `_shoulder_with_midday`
            # field if it exists, else treat offpeak as unknown.
            # Actually: the parser classifies 11-14h as 'offpeak' for all plans,
            # so plans without that window need re-classification.
            # We handle this by storing a separate midday_kwh in buckets.
            midday = getattr(b, "import_midday_kwh", 0.0)
            offpeak_night = offpeak - midday
            shoulder = shoulder + midday
            offpeak = offpeak_night

        r.import_peak_kwh += peak
        r.import_shoulder_kwh += shoulder
        r.import_offpeak_kwh += offpeak

        # --- Export ---
        r.export_total_kwh += b.export_total
        r.export_evening_kwh += b.export_evening

        # Apply daily cap on premium FiT
        if plan.fit_evening_cap_kwh is not None:
            capped_evening = min(b.export_evening, plan.fit_evening_cap_kwh)
        else:
            capped_evening = b.export_evening
        r.export_evening_capped_kwh += capped_evening

        # FiT window export that's NOT in the evening sub-window
        # (earns fit_base rate)
        fit_non_evening = b.export_fit_window - b.export_evening
        r.export_fit_window_kwh += fit_non_evening

    # Scale to annual
    r.import_peak_kwh *= scale
    r.import_shoulder_kwh *= scale
    r.import_offpeak_kwh *= scale
    r.export_total_kwh *= scale
    r.export_evening_kwh *= scale
    r.export_evening_capped_kwh *= scale
    r.export_fit_window_kwh *= scale

    r.import_total_kwh = r.import_peak_kwh + r.import_shoulder_kwh + r.import_offpeak_kwh

    # --- Compute costs ---
    r.cost_daily = plan.daily_charge * annualised_days
    r.cost_import_peak = r.import_peak_kwh * plan.peak_rate
    r.cost_import_shoulder = r.import_shoulder_kwh * plan.shoulder_rate
    r.cost_import_offpeak = r.import_offpeak_kwh * plan.offpeak_rate
    r.cost_import_total = r.cost_import_peak + r.cost_import_shoulder + r.cost_import_offpeak

    # Evening premium FiT
    r.earnings_fit_evening = r.export_evening_capped_kwh * plan.fit_evening

    # Non-evening FiT window: uncapped evening overflow + other FiT window
    overflow = r.export_evening_kwh - r.export_evening_capped_kwh
    r.earnings_fit_base = (r.export_fit_window_kwh + overflow) * plan.fit_base

    r.earnings_fit_total = r.earnings_fit_evening + r.earnings_fit_base

    r.cost_subscription = plan.subscription

    r.net_annual_cost = (
        r.cost_daily
        + r.cost_import_total
        - r.earnings_fit_total
        + r.cost_subscription
    )

    return r


# ---------------------------------------------------------------------------
# Sensitivity analysis
# ---------------------------------------------------------------------------

def sensitivity_table(
    daily_buckets: dict[str, DailyBuckets],
    plan: TariffPlan,
    param: str,
    values: list[float],
    annualised_days: int = 365,
) -> list[tuple[float, float]]:
    """
    Vary a single tariff parameter and return (param_value, net_annual_cost) pairs.

    param: attribute name on TariffPlan, e.g. 'shoulder_rate', 'daily_charge'
    """
    from copy import copy
    results = []
    for v in values:
        p = copy(plan)
        setattr(p, param, v)
        r = model_plan(daily_buckets, p, annualised_days)
        results.append((v, r.net_annual_cost))
    return results
