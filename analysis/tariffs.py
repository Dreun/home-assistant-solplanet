"""
Tariff definitions for Endeavour Energy zone, NSW.

All rates in dollars (not cents). GST included.

Each plan is a dict with keys:
  daily_charge        $/day
  peak_rate           $/kWh  (import 16:00–23:00)
  shoulder_rate       $/kWh  (import, all other non-off-peak hours)
  offpeak_rate        $/kWh  (import, off-peak window)
  fit_base            $/kWh  exported at all times (floor FiT)
  fit_evening         $/kWh  exported in the plan's premium evening window
  fit_evening_start   hour   (inclusive) of premium FiT window
  fit_evening_end     hour   (exclusive) of premium FiT window
  fit_evening_cap_kwh float  daily cap on premium FiT kWh (None = uncapped)
  subscription        $/yr   fixed annual fee (e.g. Amber)
  notes               str    human-readable caveats

Sources / last verified:
  GloBird ZEROHERO (new rates 1 Jul 2026): retailer email to customer
  Red Energy Solar Savers TOU: redenergysolarsavers.com.au + IPART 2025-26
  Amber Electric: amberhq.com.au (Jun 2026)
  Origin Solar Boost: originenergy.com.au (Jun 2026)
  AGL Savers: agl.com.au (Jun 2026)

IMPORTANT: Rates marked [UNVERIFIED] are estimates or sourced from IPART
benchmarks and MUST be confirmed with the retailer before relying on them.
The IPART 2025-26 default market offer for Endeavour uses these reference
values for the evening FiT:
  Peak (4-8pm weekdays): 16.8–22.0 c/kWh
"""

from dataclasses import dataclass, field


@dataclass
class TariffPlan:
    name: str
    daily_charge: float           # $/day incl GST
    peak_rate: float              # $/kWh import 16:00-23:00
    shoulder_rate: float          # $/kWh import all other non-offpeak
    offpeak_rate: float           # $/kWh import off-peak window
    fit_base: float               # $/kWh export (floor, outside premium window)
    fit_evening: float            # $/kWh export in premium evening window
    fit_evening_start: int        # hour inclusive (24h)
    fit_evening_end: int          # hour exclusive (24h)
    fit_evening_cap_kwh: float | None  # daily cap on premium FiT kWh (None=uncapped)
    subscription: float = 0.0    # $/yr fixed fee
    notes: str = ""

    # Some plans have a special off-peak window beyond 00:00-07:00
    # GloBird: 11:00-14:00 is also $0 — modelled as offpeak_rate=$0
    # Other plans: this window is shoulder
    has_midday_offpeak: bool = False  # if True, 11:00-14:00 counted at offpeak_rate

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "daily_charge": self.daily_charge,
            "peak_rate": self.peak_rate,
            "shoulder_rate": self.shoulder_rate,
            "offpeak_rate": self.offpeak_rate,
            "fit_base": self.fit_base,
            "fit_evening": self.fit_evening,
            "fit_evening_start": self.fit_evening_start,
            "fit_evening_end": self.fit_evening_end,
            "fit_evening_cap_kwh": self.fit_evening_cap_kwh,
            "subscription": self.subscription,
            "has_midday_offpeak": self.has_midday_offpeak,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Plan catalogue
# ---------------------------------------------------------------------------

PLANS: dict[str, TariffPlan] = {}


def _add(plan: TariffPlan) -> TariffPlan:
    PLANS[plan.name] = plan
    return plan


# --- GloBird ZEROHERO (new rates from 1 July 2026) ---
# Source: retailer email to customer
# Peak 16:00-23:00, Off-peak 00:00-07:00 + 11:00-14:00 ($0), Shoulder rest
# FiT: 4c/kWh base (16:00-21:00); Super Export top-up to 10c/kWh in 18:00-20:00,
#      capped at 10 kWh/day.  Outside FiT window: 0c.
# We model the premium window as 18-20 at 10c (net), base outside as 2c,
# and zero FiT outside 16-21 window.
GLOBIRD_ZEROHERO_NEW = _add(TariffPlan(
    name="GloBird ZEROHERO (Jul 2026)",
    daily_charge=1.705,
    peak_rate=0.528,
    shoulder_rate=0.418,
    offpeak_rate=0.00,           # $0 in 00:00-07:00 AND 11:00-14:00
    fit_base=0.02,               # 2c/kWh in 16:00-21:00 outside super-export window
    fit_evening=0.10,            # 10c/kWh in 18:00-20:00 (super export, up to cap)
    fit_evening_start=18,
    fit_evening_end=20,
    fit_evening_cap_kwh=10.0,
    has_midday_offpeak=True,
    notes=(
        "Off-peak ($0): 00:00-07:00 and 11:00-14:00. "
        "FiT: 2c base in 16-21h window; Super Export 10c in 18-20h capped at 10kWh/day. "
        "Zero FiT outside 16-21h. Rates from retailer email, effective 1 Jul 2026."
    ),
))

# --- Red Energy Solar Savers TOU (Endeavour zone) ---
# IPART 2025-26 benchmark evening FiT for Endeavour: 16.8-22c/kWh (4-8pm peak)
# Red Solar Savers advertises 'up to 20c' evening FiT in Endeavour zone.
# Import tariff structure: Standard TOU — peak 4-9pm, shoulder 7am-4pm + 9pm-10pm,
# off-peak 10pm-7am. (No midday off-peak window.)
# [UNVERIFIED] — confirm exact rates at redenergysolarsavers.com.au or call Red
RED_SOLAR_SAVERS = _add(TariffPlan(
    name="Red Energy Solar Savers TOU [UNVERIFIED]",
    daily_charge=1.21,           # [UNVERIFIED] ~$1.21/day typical Endeavour supply
    peak_rate=0.545,             # [UNVERIFIED] ~54.5c/kWh peak (4-9pm)
    shoulder_rate=0.375,         # [UNVERIFIED] ~37.5c/kWh shoulder
    offpeak_rate=0.195,          # [UNVERIFIED] ~19.5c/kWh off-peak (10pm-7am)
    fit_base=0.05,               # [UNVERIFIED] ~5c/kWh base FiT (outside peak window)
    fit_evening=0.20,            # [UNVERIFIED] ~20c/kWh in 4-8pm window (IPART upper)
    fit_evening_start=16,
    fit_evening_end=20,
    fit_evening_cap_kwh=None,    # [UNVERIFIED] — check if Red caps this
    has_midday_offpeak=False,
    notes=(
        "[UNVERIFIED] All rates estimated from IPART 2025-26 DMO benchmarks and "
        "Red Energy marketing. Peak window 16:00-21:00. Evening FiT 16:00-20:00. "
        "MUST be confirmed with Red Energy before relying on this model."
    ),
))

# --- Amber Electric (wholesale pass-through + subscription) ---
# Amber charges wholesale spot price + network tariff + ~6-8c/kWh margin.
# Instead of modelling spot prices (highly variable), we use the 2025 annual
# average wholesale price as a proxy.  The subscription ($15/mo = $180/yr) is
# the fixed cost.  FiT tracks wholesale spot (can be negative!).
# [UNVERIFIED] — these are 2025 NEM averages; actual 2026 costs depend on spot.
AMBER = _add(TariffPlan(
    name="Amber Electric (wholesale proxy) [UNVERIFIED]",
    daily_charge=1.10,           # network + metering only (excl. spot + margin)
    peak_rate=0.38,              # [PROXY] ~38c/kWh average all-in peak incl. network
    shoulder_rate=0.28,          # [PROXY] ~28c/kWh average shoulder
    offpeak_rate=0.18,           # [PROXY] ~18c/kWh average off-peak
    fit_base=0.06,               # [PROXY] ~6c/kWh average non-peak FiT
    fit_evening=0.18,            # [PROXY] ~18c/kWh average evening FiT (peak spot)
    fit_evening_start=16,
    fit_evening_end=21,
    fit_evening_cap_kwh=None,
    subscription=180.0,          # $15/mo subscription ($180/yr)
    has_midday_offpeak=False,
    notes=(
        "[UNVERIFIED] Wholesale proxy using 2025 NSW average spot prices. "
        "Actual costs are highly variable — Amber can be 50% cheaper or more expensive "
        "depending on the year. Subscription $180/yr. Check amberhq.com.au for actuals."
    ),
))

# --- Origin Solar Boost TOU (Endeavour zone) ---
# [UNVERIFIED] — estimated from Origin website Jun 2026
ORIGIN_SOLAR_BOOST = _add(TariffPlan(
    name="Origin Solar Boost TOU [UNVERIFIED]",
    daily_charge=1.32,
    peak_rate=0.565,
    shoulder_rate=0.395,
    offpeak_rate=0.195,
    fit_base=0.05,
    fit_evening=0.14,            # [UNVERIFIED] Origin evening FiT Endeavour zone
    fit_evening_start=15,
    fit_evening_end=21,
    fit_evening_cap_kwh=None,
    has_midday_offpeak=False,
    notes=(
        "[UNVERIFIED] Estimated from Origin Energy website Jun 2026. "
        "Confirm at originenergy.com.au — rates change frequently."
    ),
))

# --- AGL Savers TOU (Endeavour zone) ---
# [UNVERIFIED]
AGL_SAVERS = _add(TariffPlan(
    name="AGL Savers TOU [UNVERIFIED]",
    daily_charge=1.28,
    peak_rate=0.558,
    shoulder_rate=0.390,
    offpeak_rate=0.185,
    fit_base=0.07,
    fit_evening=0.12,            # [UNVERIFIED]
    fit_evening_start=15,
    fit_evening_end=21,
    fit_evening_cap_kwh=None,
    has_midday_offpeak=False,
    notes=(
        "[UNVERIFIED] Estimated from AGL website Jun 2026. "
        "Confirm at agl.com.au."
    ),
))
