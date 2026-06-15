"""
NSW Electricity Plan Comparison — net annual cost ranking.
Endeavour Energy zone, postcode 2763, solar + battery household.

Run:  python analysis/run_analysis.py <path-to-csv>

Rate sources:
  GloBird ZEROHERO Jul 2026: retailer email to customer (CONFIRMED)
  WATTever Endeavour comparison page, fetched 12–15 Jun 2026 (pre-Jul-1 rates)
  Solar Sharer plans: WATTever free-plans page (current market offers)
  AGL Solar Savers FiT: AGL website (8c/10kWh, 4c after)
  Red Energy evening FiT: IPART 2025-26 benchmark (UNVERIFIED with retailer)
  Momentum/1st Energy/Sumo FiT: estimated ~5c — UNVERIFIED

IMPORTANT — Solar Sharer Offer (from 1 July 2026):
  All major NSW retailers must offer free 11am-2pm electricity (up to 24 kWh/day)
  to smart-meter customers.  This eliminates GloBird's unique midday advantage.
  Plans marked [+SS] model the hypothetical case where a retailer combines their
  market-offer rates with the Solar Sharer free window.  These may or may not
  actually exist as a single product — confirm with each retailer.

Rate caution:
  WATTever rates are pre-1-Jul-2026.  Endeavour network costs rise ~11% from
  Jul 2026 but the DMO benchmark falls 3.4-3.8%, so net effect on retail prices
  is mixed.  GloBird rates are confirmed Jul-2026.  All others are indicative.
"""

import sys
from pathlib import Path
from dataclasses import dataclass, field
from parse_endeavour_export import load_endeavour_csv, monthly_summary, hourly_export_profile, DayBuckets


# ---------------------------------------------------------------------------
# Tariff definitions  (all $ incl. GST)
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    name: str
    daily_charge: float        # $/day
    peak_rate: float           # $/kWh  import 16-23h (or plan peak window)
    shoulder_rate: float       # $/kWh  import shoulder (7am-4pm + 11pm-midnight)
    offpeak_night_rate: float  # $/kWh  import 00-07h (standard night off-peak)
    offpeak_midday_rate: float # $/kWh  import 11-14h (free on SS plans, else shoulder)
    # FiT — GloBird-style super-export
    fit_super_export: float    # $/kWh  in 18-20h super-export window
    fit_super_export_cap: float | None  # daily kWh cap on super-export
    fit_evening: float         # $/kWh  rest of GloBird FiT window (16-21h non 18-20)
    # FiT — Red-style premium window
    fit_red_premium: float     # $/kWh  in 16-20h premium window
    # Base FiT
    fit_base: float            # $/kWh  all other export
    subscription: float        # $/yr
    has_solar_sharer: bool = False   # True = 11-14h is free (24 kWh/day cap)
    verified: bool = True
    notes: str = ""


PLANS: list[Plan] = []

def _add(p: Plan) -> Plan:
    PLANS.append(p)
    return p


# ==========================================================================
# GROUP 1 — PLANS WITH FREE 11am-2pm WINDOW (Solar Sharer or equivalent)
# ==========================================================================

# --- GloBird ZEROHERO (new rates from 1 July 2026) ---
# Source: retailer email. CONFIRMED.
# Daily $1.705; peak (4-11pm) 52.8c; shoulder 41.8c; off-peak night+midday $0.
# FiT: super-export 18-20h 10c (cap 10kWh/day); 2c rest of 16-21h; 0c outside.
_add(Plan(
    name="GloBird ZEROHERO (Jul 2026) ★confirmed",
    daily_charge=1.705,
    peak_rate=0.528,
    shoulder_rate=0.418,
    offpeak_night_rate=0.000,
    offpeak_midday_rate=0.000,
    fit_super_export=0.10,
    fit_super_export_cap=10.0,
    fit_evening=0.02,
    fit_red_premium=0.0,
    fit_base=0.00,
    subscription=0.0,
    has_solar_sharer=True,
    verified=True,
    notes="Retailer email eff. 1 Jul 2026. $0 night (00-07h) AND midday (11-14h). "
          "Super Export: 10c in 18-20h, capped 10kWh/day. 2c in 16-21h otherwise.",
))

# --- GloBird ZEROHERO (old / current pre-Jul-2026 rates) ---
# For reference: shows the repricing impact.
# Supply 203.5c, peak (4-11pm) 52.8c, off-peak (incl. midday) 30.8c.
# Old FiT was 15c/15kWh in 6-9pm; now cut to 10c/10kWh in 6-8pm.
# Modelling old FiT as 15c super-export, 15kWh cap, 0c otherwise.
_add(Plan(
    name="GloBird ZEROHERO (current, pre-Jul)",
    daily_charge=2.035,
    peak_rate=0.528,
    shoulder_rate=0.308,
    offpeak_night_rate=0.000,
    offpeak_midday_rate=0.000,
    fit_super_export=0.15,
    fit_super_export_cap=15.0,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.00,
    subscription=0.0,
    has_solar_sharer=True,
    verified=True,
    notes="Pre-Jul-2026 rates from WATTever (Jun 2026). Supply 203.5c. Old FiT 15c/15kWh 18-21h."
          " Compare to new Jul-2026 plan to see repricing impact.",
))

# --- GloBird Four4Free (Endeavour, WATTever Jun 2026) ---
# Free window 10am-2pm (wider than ZEROHERO).  No solar FiT.
# Single non-free rate 37.45c, supply 148.31c.
_add(Plan(
    name="GloBird Four4Free",
    daily_charge=1.4831,
    peak_rate=0.3745,
    shoulder_rate=0.3745,
    offpeak_night_rate=0.3745,
    offpeak_midday_rate=0.000,
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.00,
    subscription=0.0,
    has_solar_sharer=True,
    verified=True,
    notes="WATTever Jun 2026. Free 10am-2pm (50kWh cap). Single rate 37.45c all other hours. "
          "Zero FiT — battery owners lose all export earnings.",
))

# --- OVO Energy The Free 3 Plan (Endeavour, WATTever Jun 2026) ---
# Free 11am-2pm.  Single (flat) rate for all other hours.  Low 2.8c FiT.
_add(Plan(
    name="OVO Energy Free 3",
    daily_charge=1.0120,
    peak_rate=0.3641,
    shoulder_rate=0.3641,
    offpeak_night_rate=0.3641,
    offpeak_midday_rate=0.000,
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.028,
    subscription=0.0,
    has_solar_sharer=True,
    verified=True,
    notes="WATTever Jun 2026. Free 11am-2pm. Flat 36.41c all other hours. FiT 2.8c.",
))

# --- CovaU SolarMax (Solar Sharer TOU, Endeavour, WATTever Jun 2026) ---
# Free 11am-2pm (24kWh cap — same as user's midday usage).
# TOU: peak+evening 38.53c; overnight (00-07h) 16.5c.
# FiT 5c flat.
_add(Plan(
    name="CovaU SolarMax (Solar Sharer)",
    daily_charge=1.6799,
    peak_rate=0.3853,
    shoulder_rate=0.3853,
    offpeak_night_rate=0.1650,
    offpeak_midday_rate=0.000,
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.050,
    subscription=0.0,
    has_solar_sharer=True,
    verified=True,
    notes="WATTever Jun 2026. Free 11-14h (24kWh/day cap). TOU: 38.53c peak/shoulder, "
          "16.5c off-peak night. FiT 5c flat. Customer uses ~22.7kWh/day midday — just under cap.",
))


# ==========================================================================
# GROUP 2 — STANDARD TOU PLANS (no free midday — midday charged at shoulder rate)
# ==========================================================================
# These plans don't have Solar Sharer.  Modelled at current WATTever rates.
# The 8,286 kWh/yr of midday battery-charging import costs money on these plans.
# UNLESS the customer changes behaviour (stops grid-charging during 11-14h).
# Rates are pre-Jul-2026; expect small changes from 1 July.

# --- AGL Solar Savers TOU ---
# Source: WATTever Jun 2026 (rates) + AGL website (8c FiT).
# TOU: peak 40.45c, shoulder 33.72c, off-peak 26.73c, supply 95.99c.
# FiT: 8c for first 10kWh/day (AGL Solar Savers), 4c after.
# With daily export avg 9.2kWh, almost all export is under the 10kWh cap → ~8c.
_add(Plan(
    name="AGL Solar Savers TOU",
    daily_charge=0.9599,
    peak_rate=0.4045,
    shoulder_rate=0.3372,
    offpeak_night_rate=0.2673,
    offpeak_midday_rate=0.3372,    # midday charged at shoulder rate (no SS)
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.080,                # AGL Solar Savers 8c (all under 10kWh/day cap)
    subscription=0.0,
    has_solar_sharer=False,
    verified=True,
    notes="WATTever Jun 2026 import rates. AGL Solar Savers 8c FiT (first 10kWh/day). "
          "Midday import charged at shoulder rate (no Solar Sharer). "
          "Pre-Jul-2026 rates — confirm with AGL.",
))

# --- AGL Solar Savers TOU + Solar Sharer [HYPOTHETICAL] ---
# If AGL offers Solar Sharer combined with Solar Savers FiT as a market offer.
# NOT confirmed — requires retailer verification.
_add(Plan(
    name="AGL Solar Savers TOU + Solar Sharer [HYPOTHETICAL]",
    daily_charge=0.9599,
    peak_rate=0.4045,
    shoulder_rate=0.3372,
    offpeak_night_rate=0.2673,
    offpeak_midday_rate=0.000,     # Solar Sharer: midday free
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.080,
    subscription=0.0,
    has_solar_sharer=True,
    verified=False,
    notes="HYPOTHETICAL: AGL Solar Savers TOU rates + Solar Sharer free midday combined. "
          "As of Jun 2026, NOT confirmed as a single market offer product. "
          "Verify with AGL whether Solar Sharer + Solar Savers FiT is available as one plan.",
))

# --- Red Energy TOU (seasonal solar FiT, 20c evening) [UNVERIFIED] ---
# Import: WATTever Jun 2026 (peak 53.58c, shoulder/off-peak 30.78c, supply 92.29c)
# FiT: IPART 2025-26 Endeavour evening benchmark 16.9-19.9c — modelled at 20c
# Red Energy structure: FiT window 16-20h; base 4c outside.
# [UNVERIFIED] — rates and FiT window not confirmed with Red Energy.
_add(Plan(
    name="Red Energy TOU (20c evening FiT) [UNVERIFIED]",
    daily_charge=0.9229,
    peak_rate=0.5358,
    shoulder_rate=0.3078,
    offpeak_night_rate=0.3078,
    offpeak_midday_rate=0.3078,    # midday charged (no SS)
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.20,          # evening premium 16-20h [UNVERIFIED]
    fit_base=0.04,
    subscription=0.0,
    has_solar_sharer=False,
    verified=False,
    notes="[UNVERIFIED] Import rates WATTever Jun 2026. Evening FiT 20c (16-20h) from "
          "IPART 2025-26 Endeavour benchmark upper range. IPART 2026-27 benchmark: 16.9-19.9c. "
          "Red Energy website blocked — MUST confirm rate, window and any daily/annual cap.",
))

# --- Red Energy TOU + Solar Sharer [HYPOTHETICAL, UNVERIFIED] ---
_add(Plan(
    name="Red Energy TOU + Solar Sharer 20c [HYPOTHETICAL, UNVERIFIED]",
    daily_charge=0.9229,
    peak_rate=0.5358,
    shoulder_rate=0.3078,
    offpeak_night_rate=0.3078,
    offpeak_midday_rate=0.000,     # Solar Sharer: free midday
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.20,
    fit_base=0.04,
    subscription=0.0,
    has_solar_sharer=True,
    verified=False,
    notes="HYPOTHETICAL + UNVERIFIED. Red Energy import rates + Solar Sharer free midday "
          "+ 20c evening FiT. None of these three components confirmed as a combined offer. "
          "If this plan existed it would be the best case scenario.",
))

# --- Momentum Energy TOU ---
# Best import rates in Endeavour zone per WATTever: 31.90c peak, 26.62c shoulder.
# FiT: estimated 5c [UNVERIFIED].
_add(Plan(
    name="Momentum Energy TOU [FiT unverified]",
    daily_charge=1.6874,
    peak_rate=0.3190,
    shoulder_rate=0.2662,
    offpeak_night_rate=0.2101,
    offpeak_midday_rate=0.2662,
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.05,                 # [UNVERIFIED — check with Momentum]
    subscription=0.0,
    has_solar_sharer=False,
    verified=False,
    notes="WATTever Jun 2026 import rates. FiT estimated at 5c — UNVERIFIED. "
          "High daily supply charge ($615/yr) partially offsets cheap usage rates.",
))

# --- Momentum TOU + Solar Sharer [HYPOTHETICAL] ---
_add(Plan(
    name="Momentum TOU + Solar Sharer [HYPOTHETICAL]",
    daily_charge=1.6874,
    peak_rate=0.3190,
    shoulder_rate=0.2662,
    offpeak_night_rate=0.2101,
    offpeak_midday_rate=0.000,
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.05,
    subscription=0.0,
    has_solar_sharer=True,
    verified=False,
    notes="HYPOTHETICAL: Momentum TOU rates + Solar Sharer free midday. FiT 5c [UNVERIFIED].",
))

# --- 1st Energy TOU ---
# WATTever Jun 2026: peak 38.02c, shoulder/off-peak 27.46c, supply 99.26c.
# FiT: estimated 5c [UNVERIFIED].
_add(Plan(
    name="1st Energy TOU [FiT unverified]",
    daily_charge=0.9926,
    peak_rate=0.3802,
    shoulder_rate=0.2746,
    offpeak_night_rate=0.2746,
    offpeak_midday_rate=0.2746,
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.05,
    subscription=0.0,
    has_solar_sharer=False,
    verified=False,
    notes="WATTever Jun 2026. Low supply 99.26c. FiT estimated 5c [UNVERIFIED]. "
          "Confirm 1st Energy's solar FiT before switching.",
))

# --- 1st Energy TOU + Solar Sharer [HYPOTHETICAL] ---
_add(Plan(
    name="1st Energy TOU + Solar Sharer [HYPOTHETICAL]",
    daily_charge=0.9926,
    peak_rate=0.3802,
    shoulder_rate=0.2746,
    offpeak_night_rate=0.2746,
    offpeak_midday_rate=0.000,
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.05,
    subscription=0.0,
    has_solar_sharer=True,
    verified=False,
    notes="HYPOTHETICAL: 1st Energy TOU + Solar Sharer free midday. FiT 5c [UNVERIFIED].",
))

# --- Sumo TOU ---
_add(Plan(
    name="Sumo TOU [FiT unverified]",
    daily_charge=1.2252,
    peak_rate=0.3509,
    shoulder_rate=0.2980,
    offpeak_night_rate=0.2800,
    offpeak_midday_rate=0.2980,
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.05,
    subscription=0.0,
    has_solar_sharer=False,
    verified=False,
    notes="WATTever Jun 2026. FiT estimated 5c [UNVERIFIED].",
))

# --- Amber Electric (wholesale proxy) ---
# $25/month subscription = $300/yr.  Import at wholesale spot + network + Amber fee.
# WATTever shows Amber flat rate 28.38c/kWh for Endeavour (includes Amber margin).
# Endeavour Two-Way Tariff: bonus FiT 4-8pm on weekdays — seasonal 11c (Nov-Mar),
# 3.27c (Apr-Oct). Modelling as annual avg ~7c in peak window.
# Actual costs are highly variable — wholesale can spike to $15+/kWh.
_add(Plan(
    name="Amber Electric (wholesale proxy) [UNVERIFIED]",
    daily_charge=1.911,            # WATTever supply charge (may include fees)
    peak_rate=0.2838,              # WATTever Endeavour flat rate (wholesale avg)
    shoulder_rate=0.2838,
    offpeak_night_rate=0.2838,
    offpeak_midday_rate=0.2838,
    fit_super_export=0.0,
    fit_super_export_cap=None,
    fit_evening=0.0,
    fit_red_premium=0.0,
    fit_base=0.07,                 # Endeavour Two-Way avg FiT (seasonal: 11c summer, 3.27c winter)
    subscription=300.0,            # $25/month
    has_solar_sharer=False,
    verified=False,
    notes="[UNVERIFIED PROXY] Wholesale-linked pricing — highly variable. "
          "28.38c is WATTever average; actual ranges widely. "
          "Endeavour Two-Way FiT: 11c/kWh (Nov-Mar), 3.27c/kWh (Apr-Oct) during 4-8pm. "
          "Modelled as 7c avg. Subscription $25/month. Very risky in high-spot-price periods.",
))


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------

@dataclass
class Result:
    plan: Plan
    data_days: int
    scale: float

    import_peak_kwh: float
    import_shoulder_kwh: float
    import_offpeak_night_kwh: float
    import_offpeak_midday_kwh: float
    import_total_kwh: float

    export_total_kwh: float
    export_super_export_kwh: float
    export_super_export_capped_kwh: float
    export_evening_non_super_kwh: float
    export_red_premium_kwh: float

    cost_daily: float
    cost_peak: float
    cost_shoulder: float
    cost_offpeak_night: float
    cost_offpeak_midday: float

    earn_super_export: float
    earn_evening: float
    earn_red_premium: float
    earn_base: float
    earn_total: float

    cost_subscription: float
    net_annual_cost: float


def model(buckets: dict[str, DayBuckets], plan: Plan, target_days: int = 365) -> Result:
    data_days = len(buckets)
    scale = target_days / data_days

    ip = ish = ion = iom = 0.0
    et = ess = ese_capped = e_evening_non_super = e_red = 0.0

    for b in buckets.values():
        ip  += b.import_peak
        ish += b.import_shoulder
        ion += b.import_offpeak_night
        iom += b.import_offpeak_midday
        et  += b.export_total
        ess += b.export_super_export

        cap = plan.fit_super_export_cap
        ese_capped += min(b.export_super_export, cap) if cap is not None else b.export_super_export
        e_evening_non_super += b.export_fit_globird - b.export_super_export
        e_red += b.export_red_premium

    ip  *= scale; ish *= scale; ion *= scale; iom *= scale
    et  *= scale; ess *= scale; ese_capped *= scale
    e_evening_non_super *= scale; e_red *= scale

    it = ip + ish + ion + iom

    c_daily = plan.daily_charge * target_days
    c_peak  = ip  * plan.peak_rate
    c_sh    = ish * plan.shoulder_rate
    c_opn   = ion * plan.offpeak_night_rate
    c_opm   = iom * plan.offpeak_midday_rate

    if plan.fit_super_export > 0:
        overflow = ess - ese_capped
        earn_sup  = ese_capped * plan.fit_super_export
        earn_eve  = (e_evening_non_super + overflow) * plan.fit_evening
        earn_red  = 0.0
        earn_base = (et - ese_capped - e_evening_non_super) * plan.fit_base
        # note: overflow already counted in earn_eve; base = truly outside FiT window
    elif plan.fit_red_premium > 0:
        earn_sup  = 0.0; earn_eve = 0.0
        earn_red  = e_red * plan.fit_red_premium
        earn_base = (et - e_red) * plan.fit_base
    else:
        earn_sup  = 0.0; earn_eve = 0.0; earn_red = 0.0
        earn_base = et * plan.fit_base

    earn_total = earn_sup + earn_eve + earn_red + earn_base
    c_sub = plan.subscription
    net = c_daily + c_peak + c_sh + c_opn + c_opm - earn_total + c_sub

    return Result(
        plan=plan, data_days=data_days, scale=scale,
        import_peak_kwh=ip, import_shoulder_kwh=ish,
        import_offpeak_night_kwh=ion, import_offpeak_midday_kwh=iom,
        import_total_kwh=it,
        export_total_kwh=et, export_super_export_kwh=ess,
        export_super_export_capped_kwh=ese_capped,
        export_evening_non_super_kwh=e_evening_non_super,
        export_red_premium_kwh=e_red,
        cost_daily=c_daily, cost_peak=c_peak, cost_shoulder=c_sh,
        cost_offpeak_night=c_opn, cost_offpeak_midday=c_opm,
        earn_super_export=earn_sup, earn_evening=earn_eve,
        earn_red_premium=earn_red, earn_base=earn_base, earn_total=earn_total,
        cost_subscription=c_sub, net_annual_cost=net,
    )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def fmt(v: float) -> str: return f"${v:>8,.2f}"
def fmtk(v: float) -> str: return f"{v:>8,.0f} kWh"
def pct(a, b): return f"{100*a/b:.1f}%" if b else "  n/a"

def flag(p: Plan) -> str:
    markers = []
    if not p.verified: markers.append("⚠ UNVERIFIED")
    if p.has_solar_sharer: markers.append("✓ Solar Sharer")
    return "  [" + " | ".join(markers) + "]" if markers else ""


def print_ranked_table(results: list[Result], show_groups: bool = True):
    ranked = sorted(results, key=lambda r: r.net_annual_cost)
    cheapest = ranked[0].net_annual_cost

    print(f"\n{'='*76}")
    print("  RANKED NET ANNUAL COST — your actual usage, annualised (lowest first)")
    print(f"{'='*76}")
    print(f"  {'Plan':<50}  {'Net/yr':>8}  {'vs cheapest':>12}")
    print(f"  {'-'*50}  {'-'*8}  {'-'*12}")

    for i, r in enumerate(ranked):
        diff = r.net_annual_cost - cheapest
        ss = " [SS]" if r.plan.has_solar_sharer else ""
        uv = " ⚠" if not r.plan.verified else ""
        name = (r.plan.name
                .replace(" ★confirmed", "")
                .replace(" [UNVERIFIED]", "")
                .replace(" [HYPOTHETICAL]", " [H]")
                .replace(" [HYPOTHETICAL, UNVERIFIED]", " [H⚠]")
                .replace(" [FiT unverified]", "")
               )
        label = f"{name[:44]}{ss}{uv}"
        print(f"  {i+1:>2}. {label:<48}  {fmt(r.net_annual_cost)}  +{fmt(diff)}")

    print(f"\n  [SS]=has free 11am-2pm  [H]=hypothetical combined plan  ⚠=rates unverified")
    print(f"{'='*76}")


def print_detail(r: Result, baseline_cost: float):
    p = r.plan
    print(f"\n{'='*72}")
    label = p.name
    print(f"  {label}")
    print(f"{'='*72}")
    if not p.verified:
        print("  *** RATES UNVERIFIED — do NOT switch without confirming with retailer ***")
    if p.has_solar_sharer:
        print("  *** FREE 11am-2pm (Solar Sharer or equivalent) ***")
    print(f"  Data: {r.data_days} days → annualised 365 days")
    print()

    it = r.import_total_kwh
    print(f"  IMPORT  ({it:,.0f} kWh/yr)")
    mline = "FREE" if p.offpeak_midday_rate == 0 else f"@ {p.offpeak_midday_rate*100:.1f}c"
    print(f"    Peak 16-23h           {fmtk(r.import_peak_kwh)}  ({pct(r.import_peak_kwh,it)}) @ {p.peak_rate*100:.2f}c = {fmt(r.cost_peak)}")
    print(f"    Shoulder              {fmtk(r.import_shoulder_kwh)}  ({pct(r.import_shoulder_kwh,it)}) @ {p.shoulder_rate*100:.2f}c = {fmt(r.cost_shoulder)}")
    print(f"    Off-peak night 00-07h {fmtk(r.import_offpeak_night_kwh)}  ({pct(r.import_offpeak_night_kwh,it)}) @ {p.offpeak_night_rate*100:.2f}c = {fmt(r.cost_offpeak_night)}")
    print(f"    Midday 11-14h {mline:>8} {fmtk(r.import_offpeak_midday_kwh)}  ({pct(r.import_offpeak_midday_kwh,it)}) = {fmt(r.cost_offpeak_midday)}")
    print(f"    TOTAL IMPORT                                                {fmt(r.cost_peak+r.cost_shoulder+r.cost_offpeak_night+r.cost_offpeak_midday)}")

    print()
    print(f"  EXPORT  ({r.export_total_kwh:,.0f} kWh/yr)")
    if p.fit_super_export > 0:
        overflow = r.export_super_export_kwh - r.export_super_export_capped_kwh
        truly_outside = r.export_total_kwh - r.export_super_export_kwh - r.export_evening_non_super_kwh
        print(f"    Super Export 18-20h  {fmtk(r.export_super_export_kwh)} raw")
        print(f"      after {p.fit_super_export_cap:.0f}kWh/day cap: {fmtk(r.export_super_export_capped_kwh)} @ {p.fit_super_export*100:.0f}c = {fmt(r.earn_super_export)}")
        print(f"    Evening 16-21h (incl {overflow:.0f}kWh overflow) {fmtk(r.export_evening_non_super_kwh+overflow)} @ {p.fit_evening*100:.0f}c = {fmt(r.earn_evening)}")
        print(f"    Outside FiT window   {fmtk(truly_outside)} @ 0c = $0.00")
    elif p.fit_red_premium > 0:
        print(f"    Premium 16-20h       {fmtk(r.export_red_premium_kwh)} @ {p.fit_red_premium*100:.0f}c = {fmt(r.earn_red_premium)}")
        print(f"    Other export         {fmtk(r.export_total_kwh-r.export_red_premium_kwh)} @ {p.fit_base*100:.0f}c = {fmt(r.earn_base)}")
    else:
        print(f"    All export (flat FiT) {fmtk(r.export_total_kwh)} @ {p.fit_base*100:.1f}c = {fmt(r.earn_base)}")
    print(f"    TOTAL FiT EARNINGS                                        {fmt(r.earn_total)}")

    print()
    print(f"  FIXED")
    print(f"    Daily supply {p.daily_charge*100:.1f}c/day × 365                          {fmt(r.cost_daily)}")
    if r.cost_subscription:
        print(f"    Subscription                                              {fmt(r.cost_subscription)}")

    diff = r.net_annual_cost - baseline_cost
    sign = "+" if diff >= 0 else ""
    delta = f"  ({sign}${diff:,.2f} vs cheapest)" if abs(diff) > 0.5 else "  ← cheapest"
    print(f"\n  *** NET ANNUAL COST: {fmt(r.net_annual_cost)} ***{delta}")
    if p.notes:
        print(f"\n  Note: {p.notes}")


def print_data_summary(buckets, months):
    days = len(buckets)
    scale = 365 / days
    total_import = sum(b.import_peak + b.import_shoulder + b.import_offpeak_night + b.import_offpeak_midday for b in buckets.values())
    total_export = sum(b.export_total for b in buckets.values())

    ip  = sum(b.import_peak for b in buckets.values()) * scale
    ish = sum(b.import_shoulder for b in buckets.values()) * scale
    ion = sum(b.import_offpeak_night for b in buckets.values()) * scale
    iom = sum(b.import_offpeak_midday for b in buckets.values()) * scale
    it  = ip + ish + ion + iom
    et  = total_export * scale
    ess = sum(b.export_super_export for b in buckets.values()) * scale
    ered = sum(b.export_red_premium for b in buckets.values()) * scale

    print(f"\n{'='*72}")
    print(f"  METER DATA SUMMARY  ({days} days: Jan–Jun 2026, annualised)")
    print(f"{'='*72}")
    print(f"  Gross annual import:  {it:>8,.0f} kWh  ({total_import/days:.1f} kWh/day avg)")
    print(f"  Annual export:        {et:>8,.0f} kWh  ({total_export/days:.1f} kWh/day avg)")
    print()
    print(f"  Import by TOU window (annualised):")
    print(f"    Peak 16-23h:              {ip:>6,.0f} kWh  ({100*ip/it:.1f}%)  avg {ip/365:.2f} kWh/day")
    print(f"    Shoulder:               {ish:>6,.0f} kWh  ({100*ish/it:.1f}%)  avg {ish/365:.2f} kWh/day")
    print(f"    Off-peak night 00-07h:  {ion:>6,.0f} kWh  ({100*ion/it:.1f}%)  avg {ion/365:.2f} kWh/day")
    print(f"    Midday 11-14h (batt.):  {iom:>6,.0f} kWh  ({100*iom/it:.1f}%)  avg {iom/365:.2f} kWh/day")
    print(f"    → On GloBird/Solar Sharer plans the 11-14h import costs $0")
    print(f"    → On standard TOU plans it costs {iom*0.30:.0f}–{iom*0.40:.0f}/yr at 30-40c/kWh")
    print()
    print(f"  Export sub-windows (annualised):")
    print(f"    Total:                  {et:>6,.0f} kWh")
    print(f"    Super Export 18-20h:    {ess:>6,.0f} kWh  ({100*ess/et:.1f}%)  avg {ess/365:.2f} kWh/day")
    print(f"    In Red premium 16-20h:  {ered:>6,.0f} kWh  ({100*ered/et:.1f}%)  avg {ered/365:.2f} kWh/day")
    print()
    print(f"  Monthly breakdown (actual kWh in data):")
    print(f"  {'Month':<8}  {'Days':>4}  {'Import':>7}  {'Peak':>5}  {'Shoulder':>8}  {'OPnight':>7}  {'OPmidday':>8}  {'Export':>7}")
    for ym, m in months.items():
        print(f"  {ym}  {m['days']:>4}  {m['import_total']:>7.0f}  "
              f"{m['import_peak']:>5.0f}  {m['import_shoulder']:>8.0f}  "
              f"{m['import_offpeak_night']:>7.0f}  {m['import_offpeak_midday']:>8.0f}  "
              f"{m['export_total']:>7.0f}")


def print_solar_sharer_context():
    print(f"\n{'='*72}")
    print("  SOLAR SHARER CONTEXT (effective 1 July 2026)")
    print(f"{'='*72}")
    print("""
  From 1 July 2026, all major NSW retailers must offer the Solar Sharer
  Offer (SSO) to residential smart-meter customers.  The SSO provides:
    • FREE electricity 11am-2pm, up to 24 kWh/day cap
    • Your midday usage averages 22.7 kWh/day — just under the 24 kWh cap

  THIS CHANGES EVERYTHING:
  GloBird's unique $0 midday window — which was saving you ~$3,000/yr vs
  standard TOU plans — is now available from every major retailer.

  Plans marked [SS] already have a free midday window.
  Plans marked [H] are HYPOTHETICAL — they assume a retailer COMBINES their
  Solar Sharer free window with their market-offer TOU rates and FiT.
  This combination may or may not exist as a single product.  CHECK FIRST.

  KEY QUESTION: Does any retailer offer all three together?
    (a) Free 11am-2pm (Solar Sharer)
    (b) Competitive TOU import rates (especially shoulder rate)
    (c) Good evening FiT (16.9-19.9c/kWh IPART 2026-27 Endeavour benchmark)
  If yes → could save $500-1,500+/yr vs GloBird new rates.
""")


def print_sensitivity(buckets, results):
    globird = next((r for r in results if "ZEROHERO (Jul" in r.plan.name), None)
    if not globird:
        return
    base = globird.net_annual_cost

    import copy
    print(f"\n{'='*72}")
    print("  SENSITIVITY — GloBird ZEROHERO (Jul 2026) baseline: how rates move the needle")
    print(f"{'='*72}")

    print(f"\n  (a) Shoulder rate (current 41.8c) — affects 2,787 kWh/yr:")
    for sc in [0.30, 0.35, 0.40, 0.418, 0.45, 0.50]:
        p2 = copy.copy(globird.plan); p2.shoulder_rate = sc
        r2 = model(buckets, p2)
        diff = r2.net_annual_cost - base
        print(f"    {sc*100:.1f}c  →  {fmt(r2.net_annual_cost)}  ({'+'if diff>=0 else ''}{diff:+,.2f})")

    print(f"\n  (b) Daily supply charge (current 170.5c):")
    for dc in [0.923, 1.012, 1.21, 1.483, 1.68, 1.705, 1.911, 2.035]:
        p2 = copy.copy(globird.plan); p2.daily_charge = dc
        r2 = model(buckets, p2)
        diff = r2.net_annual_cost - base
        print(f"    {dc*100:.1f}c/day  →  {fmt(r2.net_annual_cost)}  ({'+'if diff>=0 else ''}{diff:+,.2f})")

    print(f"\n  (c) Super Export FiT (current 10c, 10kWh/day cap):")
    for fit in [0.0, 0.05, 0.10, 0.15, 0.20]:
        p2 = copy.copy(globird.plan); p2.fit_super_export = fit
        r2 = model(buckets, p2)
        diff = r2.net_annual_cost - base
        print(f"    {fit*100:.0f}c  →  {fmt(r2.net_annual_cost)}  ({'+'if diff>=0 else ''}{diff:+,.2f})")

    # What Red evening FiT would tie GloBird (with Solar Sharer applied)?
    red_plan = next((r.plan for r in results if "Red Energy TOU + Solar" in r.plan.name), None)
    if red_plan:
        print(f"\n  (d) Red Energy + Solar Sharer: what evening FiT (16-20h) ties GloBird Jul 2026?")
        for fit in [0.04, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22]:
            p2 = copy.copy(red_plan); p2.fit_red_premium = fit
            r2 = model(buckets, p2)
            diff = r2.net_annual_cost - base
            print(f"    {fit*100:.0f}c  →  {fmt(r2.net_annual_cost)}  ({'+'if diff>=0 else ''}{diff:+,.2f})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_analysis.py <path-to-MeterDataReport.csv>")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"File not found: {csv_path}"); sys.exit(1)

    print(f"\nLoading {csv_path.name} ...")
    buckets = load_endeavour_csv(csv_path)
    months  = monthly_summary(buckets)

    print_data_summary(buckets, months)
    print_solar_sharer_context()

    results = [model(buckets, p) for p in PLANS]
    print_ranked_table(results)

    cheapest = min(r.net_annual_cost for r in results)
    for r in sorted(results, key=lambda r: r.net_annual_cost):
        print_detail(r, cheapest)

    print_sensitivity(buckets, results)
    print("\n\nDone.\n")


if __name__ == "__main__":
    main()
