"""
NSW Electricity Plan Comparison — net annual cost ranking.

Run:  python analysis/run_analysis.py <path-to-csv>

The CSV must be an Endeavour Energy MeterDataReport export containing at
minimum E1 (import) and B1 (export) stream sections.
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from parse_endeavour_export import load_endeavour_csv, monthly_summary, hourly_export_profile, DayBuckets

# ---------------------------------------------------------------------------
# Tariff definitions  (all $ incl. GST)
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    name: str
    daily_charge: float      # $/day
    peak_rate: float         # $/kWh  import 16-23h
    shoulder_rate: float     # $/kWh  import shoulder
    offpeak_night_rate: float  # $/kWh  import 00-07h
    offpeak_midday_rate: float # $/kWh  import 11-14h (GloBird $0; others = shoulder)
    # FiT structure
    fit_super_export: float  # $/kWh  in super-export window  (GloBird 18-20h, capped)
    fit_super_export_cap: float | None  # daily kWh cap on super-export FiT
    fit_evening: float       # $/kWh  rest of FiT window after super-export  (GloBird 16-21h non 18-20)
    fit_red_premium: float   # $/kWh  Red 16-20h premium
    fit_base: float          # $/kWh  any export outside above windows (floor)
    subscription: float      # $/yr
    notes: str = ""
    verified: bool = True    # False = rates estimated, not confirmed with retailer


PLANS = [
    # ------------------------------------------------------------------
    # GloBird ZEROHERO — new rates from 1 July 2026 (source: retailer email)
    # TOU: peak 16-23h, off-peak 00-07h + 11-14h ($0 both), shoulder rest
    # FiT: 2c/kWh in 16-21h window; Super Export 10c in 18-20h, cap 10 kWh/day
    # ------------------------------------------------------------------
    Plan(
        name="GloBird ZEROHERO (Jul 2026)",
        daily_charge=1.705,
        peak_rate=0.528,
        shoulder_rate=0.418,
        offpeak_night_rate=0.000,
        offpeak_midday_rate=0.000,
        fit_super_export=0.10,
        fit_super_export_cap=10.0,
        fit_evening=0.02,          # 16-21h outside 18-20h super-export window
        fit_red_premium=0.0,       # not applicable
        fit_base=0.00,             # zero outside 16-21h window
        subscription=0.0,
        notes="Rates from retailer email eff. 1 Jul 2026. $0 off-peak: 00-07h and 11-14h.",
        verified=True,
    ),

    # ------------------------------------------------------------------
    # Red Energy Solar Savers TOU — Endeavour zone
    # [UNVERIFIED] — IPART 2025-26 DMO benchmark + Red marketing material
    # TOU: peak 16-21h, shoulder 07-16h + 21-22h, off-peak 22-07h
    # FiT: premium 16-20h (~20c), base outside (~5c)
    # ------------------------------------------------------------------
    Plan(
        name="Red Energy Solar Savers TOU [UNVERIFIED]",
        daily_charge=1.21,
        peak_rate=0.545,
        shoulder_rate=0.375,
        offpeak_night_rate=0.195,  # 22:00-07:00 on Red's structure
        offpeak_midday_rate=0.375,  # Red has no midday off-peak → shoulder
        fit_super_export=0.0,
        fit_super_export_cap=None,
        fit_evening=0.0,
        fit_red_premium=0.20,      # 16-20h premium FiT [UNVERIFIED — confirm with Red]
        fit_base=0.05,             # outside 16-20h
        subscription=0.0,
        notes=(
            "[UNVERIFIED] IPART 2025-26 evening FiT Endeavour benchmark: 16.8-22c. "
            "Red advertises 'up to 20c' — modelled at 20c here. MUST confirm rate and "
            "whether a daily/annual cap applies. Import TOU structure estimated."
        ),
        verified=False,
    ),

    # ------------------------------------------------------------------
    # Red Energy Solar Savers TOU — CONSERVATIVE (16c evening FiT)
    # Same plan, lower-end IPART benchmark for sensitivity
    # ------------------------------------------------------------------
    Plan(
        name="Red Energy Solar Savers TOU 16c [UNVERIFIED]",
        daily_charge=1.21,
        peak_rate=0.545,
        shoulder_rate=0.375,
        offpeak_night_rate=0.195,
        offpeak_midday_rate=0.375,
        fit_super_export=0.0,
        fit_super_export_cap=None,
        fit_evening=0.0,
        fit_red_premium=0.16,      # lower-end IPART benchmark
        fit_base=0.05,
        subscription=0.0,
        notes="[UNVERIFIED] Same as above but at 16c evening FiT (IPART lower bound).",
        verified=False,
    ),

    # ------------------------------------------------------------------
    # Amber Electric — wholesale pass-through + $180/yr subscription
    # [UNVERIFIED] — 2025 NSW annual average spot price proxy
    # Spot price is highly variable; this is a proxy, not a forecast.
    # ------------------------------------------------------------------
    Plan(
        name="Amber Electric (2025 avg proxy) [UNVERIFIED]",
        daily_charge=0.938,        # network + metering (no retail margin in daily)
        peak_rate=0.380,           # [PROXY] ~38c avg all-in incl. network + Amber margin
        shoulder_rate=0.260,       # [PROXY] ~26c avg shoulder
        offpeak_night_rate=0.180,  # [PROXY] ~18c avg off-peak
        offpeak_midday_rate=0.180, # [PROXY] same as off-peak
        fit_super_export=0.0,
        fit_super_export_cap=None,
        fit_evening=0.0,
        fit_red_premium=0.0,
        fit_base=0.075,            # [PROXY] avg export price incl. LGC
        subscription=180.0,        # $15/mo
        notes=(
            "[UNVERIFIED] 2025 NSW NEM annual avg wholesale proxy. "
            "Amber can be 30-50% cheaper or more expensive depending on year/season. "
            "Peak prices can spike >$15/kWh; check Amber's app for actual bill estimates."
        ),
        verified=False,
    ),

    # ------------------------------------------------------------------
    # Origin Solar Boost TOU — Endeavour zone [UNVERIFIED]
    # ------------------------------------------------------------------
    Plan(
        name="Origin Solar Boost TOU [UNVERIFIED]",
        daily_charge=1.32,
        peak_rate=0.565,
        shoulder_rate=0.395,
        offpeak_night_rate=0.195,
        offpeak_midday_rate=0.395,
        fit_super_export=0.0,
        fit_super_export_cap=None,
        fit_evening=0.0,
        fit_red_premium=0.0,
        fit_base=0.14,             # [UNVERIFIED] Origin Endeavour evening FiT estimate
        subscription=0.0,
        notes="[UNVERIFIED] Estimated from Origin Energy website Jun 2026.",
        verified=False,
    ),

    # ------------------------------------------------------------------
    # AGL Savers TOU — Endeavour zone [UNVERIFIED]
    # ------------------------------------------------------------------
    Plan(
        name="AGL Savers TOU [UNVERIFIED]",
        daily_charge=1.28,
        peak_rate=0.558,
        shoulder_rate=0.390,
        offpeak_night_rate=0.185,
        offpeak_midday_rate=0.390,
        fit_super_export=0.0,
        fit_super_export_cap=None,
        fit_evening=0.0,
        fit_red_premium=0.0,
        fit_base=0.12,             # [UNVERIFIED]
        subscription=0.0,
        notes="[UNVERIFIED] Estimated from AGL website Jun 2026.",
        verified=False,
    ),
]

# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------

@dataclass
class Result:
    plan: Plan
    data_days: int
    scale: float  # data_days → 365

    import_peak_kwh: float
    import_shoulder_kwh: float
    import_offpeak_night_kwh: float
    import_offpeak_midday_kwh: float
    import_total_kwh: float

    export_total_kwh: float
    export_super_export_kwh: float          # before cap
    export_super_export_capped_kwh: float   # after cap
    export_evening_non_super_kwh: float     # GloBird 16-21 minus 18-20
    export_red_premium_kwh: float
    export_base_kwh: float                  # outside any FiT window

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

    ip = is_ = ion = iom = 0.0
    et = ess = ese_capped = 0.0
    e_evening_non_super = 0.0
    e_red = 0.0

    for b in buckets.values():
        ip  += b.import_peak
        is_ += b.import_shoulder
        ion += b.import_offpeak_night
        iom += b.import_offpeak_midday
        et  += b.export_total
        ess += b.export_super_export

        # Apply daily cap to super-export
        cap = plan.fit_super_export_cap
        if cap is not None:
            ese_capped += min(b.export_super_export, cap)
        else:
            ese_capped += b.export_super_export

        # GloBird evening window outside super-export (16-21h minus 18-20h)
        e_evening_non_super += b.export_fit_globird - b.export_super_export

        e_red += b.export_red_premium

    # Scale to target_days
    ip  *= scale
    is_ *= scale
    ion *= scale
    iom *= scale
    et  *= scale
    ess *= scale
    ese_capped *= scale
    e_evening_non_super *= scale
    e_red *= scale

    it = ip + is_ + ion + iom

    # Export not in any plan-specific FiT window → earns fit_base
    e_base = et - ese_capped - e_evening_non_super  # for GloBird
    # For non-GloBird plans: all export earns fit_red_premium (in 16-20h) or fit_base
    # We'll compute earnings separately per plan type

    # --- Costs ---
    c_daily = plan.daily_charge * target_days
    c_peak = ip * plan.peak_rate
    c_shoulder = is_ * plan.shoulder_rate
    c_offpeak_night = ion * plan.offpeak_night_rate
    c_offpeak_midday = iom * plan.offpeak_midday_rate

    # --- Earnings ---
    if plan.fit_super_export > 0:
        # GloBird-style: super-export + evening remainder + base (zero)
        earn_super = ese_capped * plan.fit_super_export
        earn_evening = e_evening_non_super * plan.fit_evening
        earn_red = 0.0
        # Overflow from super-export cap earns evening rate
        overflow = (ess - ese_capped) * plan.fit_evening
        earn_base = (et - ese_capped - e_evening_non_super) * plan.fit_base + overflow
    elif plan.fit_red_premium > 0:
        # Red-style: premium in 16-20h, base elsewhere
        earn_super = 0.0
        earn_evening = 0.0
        earn_red = e_red * plan.fit_red_premium
        earn_base = (et - e_red) * plan.fit_base
    else:
        # Flat FiT for all export (Amber, Origin, AGL)
        earn_super = 0.0
        earn_evening = 0.0
        earn_red = 0.0
        earn_base = et * plan.fit_base

    earn_total = earn_super + earn_evening + earn_red + earn_base
    c_sub = plan.subscription

    net = c_daily + c_peak + c_shoulder + c_offpeak_night + c_offpeak_midday - earn_total + c_sub

    return Result(
        plan=plan, data_days=data_days, scale=scale,
        import_peak_kwh=ip, import_shoulder_kwh=is_,
        import_offpeak_night_kwh=ion, import_offpeak_midday_kwh=iom, import_total_kwh=it,
        export_total_kwh=et, export_super_export_kwh=ess,
        export_super_export_capped_kwh=ese_capped,
        export_evening_non_super_kwh=e_evening_non_super,
        export_red_premium_kwh=e_red, export_base_kwh=et - ess - e_evening_non_super,
        cost_daily=c_daily, cost_peak=c_peak, cost_shoulder=c_shoulder,
        cost_offpeak_night=c_offpeak_night, cost_offpeak_midday=c_offpeak_midday,
        earn_super_export=earn_super, earn_evening=earn_evening,
        earn_red_premium=earn_red, earn_base=earn_base, earn_total=earn_total,
        cost_subscription=c_sub, net_annual_cost=net,
    )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def fmt_kwh(v: float) -> str:
    return f"{v:>8,.0f} kWh"

def fmt_dollar(v: float) -> str:
    return f"${v:>8,.2f}"

def pct(part: float, total: float) -> str:
    return f"{100*part/total:5.1f}%" if total else "   n/a"


def print_summary(r: Result, baseline_cost: float | None = None):
    p = r.plan
    print(f"\n{'='*68}")
    print(f"  {p.name}")
    print(f"{'='*68}")
    if not p.verified:
        print("  *** RATES UNVERIFIED — confirm with retailer before switching ***")
    print(f"  Data: {r.data_days} days, scaled to 365 days")
    print()

    it = r.import_total_kwh
    print(f"  IMPORT  ({it:,.0f} kWh/yr)")
    print(f"    Peak       16-23h  {fmt_kwh(r.import_peak_kwh)}  ({pct(r.import_peak_kwh,it)}) @ {p.peak_rate*100:.1f}c  = {fmt_dollar(r.cost_peak)}")
    print(f"    Shoulder           {fmt_kwh(r.import_shoulder_kwh)}  ({pct(r.import_shoulder_kwh,it)}) @ {p.shoulder_rate*100:.1f}c  = {fmt_dollar(r.cost_shoulder)}")
    print(f"    Off-peak 00-07h    {fmt_kwh(r.import_offpeak_night_kwh)}  ({pct(r.import_offpeak_night_kwh,it)}) @ {p.offpeak_night_rate*100:.1f}c  = {fmt_dollar(r.cost_offpeak_night)}")
    print(f"    Off-pk midday 11-14h {fmt_kwh(r.import_offpeak_midday_kwh)}  ({pct(r.import_offpeak_midday_kwh,it)}) @ {p.offpeak_midday_rate*100:.1f}c  = {fmt_dollar(r.cost_offpeak_midday)}")
    print(f"    TOTAL IMPORT CHARGES                                    {fmt_dollar(r.cost_peak+r.cost_shoulder+r.cost_offpeak_night+r.cost_offpeak_midday)}")
    print()

    print(f"  EXPORT  ({r.export_total_kwh:,.0f} kWh/yr total)")
    if p.fit_super_export > 0:
        overflow_kwh = r.export_super_export_kwh - r.export_super_export_capped_kwh
        truly_outside = r.export_total_kwh - r.export_super_export_kwh - r.export_evening_non_super_kwh
        print(f"    Super Export 18-20h  {fmt_kwh(r.export_super_export_kwh)} raw")
        print(f"                         {fmt_kwh(r.export_super_export_capped_kwh)} after {p.fit_super_export_cap} kWh/day cap  @ {p.fit_super_export*100:.0f}c = {fmt_dollar(r.earn_super_export)}")
        print(f"    Evening 16-21h (rest)  {fmt_kwh(r.export_evening_non_super_kwh + overflow_kwh)}  (incl. {overflow_kwh:.0f} kWh cap overflow) @ {p.fit_evening*100:.0f}c = {fmt_dollar(r.earn_evening + r.earn_base)}")
        print(f"    Outside FiT window   {fmt_kwh(truly_outside)}               @ {p.fit_base*100:.0f}c = $0.00")
    elif p.fit_red_premium > 0:
        print(f"    Premium 16-20h       {fmt_kwh(r.export_red_premium_kwh)}               @ {p.fit_red_premium*100:.0f}c = {fmt_dollar(r.earn_red_premium)}")
        print(f"    Base (other)         {fmt_kwh(r.export_total_kwh - r.export_red_premium_kwh)}               @ {p.fit_base*100:.0f}c = {fmt_dollar(r.earn_base)}")
    else:
        print(f"    All export (flat FiT) {fmt_kwh(r.export_total_kwh)}              @ {p.fit_base*100:.0f}c = {fmt_dollar(r.earn_base)}")
    print(f"    TOTAL FiT EARNINGS                                      {fmt_dollar(r.earn_total)}")
    print()

    print(f"  FIXED CHARGES")
    print(f"    Daily supply {p.daily_charge*100:.1f}c/day × 365                       {fmt_dollar(r.cost_daily)}")
    if r.cost_subscription:
        print(f"    Annual subscription                                     {fmt_dollar(r.cost_subscription)}")
    print()

    delta = ""
    if baseline_cost is not None and baseline_cost != r.net_annual_cost:
        diff = r.net_annual_cost - baseline_cost
        sign = "+" if diff >= 0 else ""
        delta = f"  ({sign}{diff:,.2f} vs baseline)"
    print(f"  *** NET ANNUAL COST:  {fmt_dollar(r.net_annual_cost)} ***{delta}")
    if p.notes:
        print(f"\n  Note: {p.notes}")


def print_ranked_table(results: list[Result]):
    ranked = sorted(results, key=lambda r: r.net_annual_cost)
    baseline = ranked[0].net_annual_cost if ranked else 0.0

    print(f"\n{'='*68}")
    print("  RANKED NET ANNUAL COST (lowest first)")
    print(f"{'='*68}")
    print(f"  {'Plan':<42}  {'Net cost':>10}  {'vs cheapest':>12}")
    print(f"  {'-'*42}  {'-'*10}  {'-'*12}")
    for i, r in enumerate(ranked):
        diff = r.net_annual_cost - baseline
        flag = " [UNVERIFIED]" if not r.plan.verified else ""
        name = r.plan.name.replace(" [UNVERIFIED]", "").replace(" (Jul 2026)", "")[:42]
        print(f"  {i+1}. {name:<40}  {fmt_dollar(r.net_annual_cost)}  +{fmt_dollar(diff)}")

    print(f"{'='*68}")


def print_data_summary(buckets: dict[str, DayBuckets], months: dict):
    days = len(buckets)
    total_import = sum(b.import_peak + b.import_shoulder + b.import_offpeak_night + b.import_offpeak_midday for b in buckets.values())
    total_export = sum(b.export_total for b in buckets.values())
    total_super  = sum(b.export_super_export for b in buckets.values())
    total_red    = sum(b.export_red_premium for b in buckets.values())

    print(f"\n{'='*68}")
    print(f"  METER DATA SUMMARY  ({days} days)")
    print(f"{'='*68}")
    print(f"  Annualised import:  {total_import*365/days:>8,.0f} kWh/yr  ({total_import/days:.1f} kWh/day avg)")
    print(f"  Annualised export:  {total_export*365/days:>8,.0f} kWh/yr  ({total_export/days:.1f} kWh/day avg)")
    print()

    # Import by TOU (annualised)
    scale = 365 / days
    ip  = sum(b.import_peak for b in buckets.values()) * scale
    ish = sum(b.import_shoulder for b in buckets.values()) * scale
    ion = sum(b.import_offpeak_night for b in buckets.values()) * scale
    iom = sum(b.import_offpeak_midday for b in buckets.values()) * scale
    it  = ip + ish + ion + iom

    print(f"  Import breakdown (annualised):")
    print(f"    Peak 16-23h:          {ip:>7,.0f} kWh  ({100*ip/it:.1f}%)")
    print(f"    Shoulder:             {ish:>7,.0f} kWh  ({100*ish/it:.1f}%)")
    print(f"    Off-peak 00-07h:      {ion:>7,.0f} kWh  ({100*ion/it:.1f}%)")
    print(f"    Off-peak midday 11-14h:{iom:>7,.0f} kWh  ({100*iom/it:.1f}%)")
    print()

    # Export sub-windows (annualised)
    et   = total_export * scale
    ess  = total_super  * scale
    ered = total_red    * scale
    print(f"  Export breakdown (annualised):")
    print(f"    Total:                {et:>7,.0f} kWh")
    print(f"    In Super Export 18-20h:{ess:>6,.0f} kWh  ({100*ess/et:.1f}% of export)")
    print(f"    In Red premium 16-20h: {ered:>6,.0f} kWh  ({100*ered/et:.1f}% of export)")
    print()

    # Monthly breakdown
    print(f"  Monthly import/export (kWh, actual days in data):")
    print(f"  {'Month':<8}  {'Days':>4}  {'Import':>7}  {'Peak':>6}  {'Shoulder':>8}  {'OP-night':>8}  {'OP-mid':>6}  {'Export':>7}  {'SuperExp':>8}")
    print(f"  {'-'*8}  {'-'*4}  {'-'*7}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*6}  {'-'*7}  {'-'*8}")
    for ym, m in months.items():
        print(f"  {ym}  {m['days']:>4}  "
              f"{m['import_total']:>7.0f}  "
              f"{m['import_peak']:>6.0f}  "
              f"{m['import_shoulder']:>8.0f}  "
              f"{m['import_offpeak_night']:>8.0f}  "
              f"{m['import_offpeak_midday']:>6.0f}  "
              f"{m['export_total']:>7.0f}  "
              f"{m['export_super_export']:>8.0f}")


def print_export_profile(profile: dict[int, float], days: int):
    total = sum(profile.values())
    print(f"\n{'='*68}")
    print("  EXPORT HOURLY PROFILE (all days combined, kWh per hour)")
    print("  Confirms battery-discharge signature: peak should be 18-20h")
    print(f"{'='*68}")
    for h in range(24):
        kwh = profile.get(h, 0.0)
        bar = "█" * int(kwh / total * 200)
        print(f"  {h:02d}h: {kwh:>8,.1f} kWh  {bar}")
    evening = sum(profile.get(h, 0) for h in range(18, 20))
    other   = total - evening
    print(f"\n  18-20h share: {100*evening/total:.1f}% of all export — "
          f"{'battery-discharge signature confirmed ✓' if evening/total > 0.30 else 'check — may not be battery-dominated'}")


def print_sensitivity(buckets, baseline_plan, results):
    """
    Sensitivity: how much does the GloBird result change per c/kWh
    change in shoulder rate and daily charge?
    """
    b_result = next((r for r in results if r.plan.name == baseline_plan.name), None)
    if not b_result:
        return

    import copy
    print(f"\n{'='*68}")
    print("  SENSITIVITY ANALYSIS — GloBird ZEROHERO (Jul 2026)")
    print(f"{'='*68}")

    print("\n  (a) Shoulder rate sensitivity (all other rates fixed):")
    print(f"  {'Shoulder rate':>14}  {'Net annual cost':>16}  {'vs base':>10}")
    for sc in [0.35, 0.38, 0.40, 0.418, 0.43, 0.45, 0.47]:
        p2 = copy.copy(baseline_plan)
        p2.shoulder_rate = sc
        r2 = model(buckets, p2)
        diff = r2.net_annual_cost - b_result.net_annual_cost
        print(f"  {sc*100:>12.1f}c  {fmt_dollar(r2.net_annual_cost)}  {'+' if diff>=0 else ''}{fmt_dollar(diff)}")

    print("\n  (b) Daily supply charge sensitivity:")
    print(f"  {'Daily charge':>14}  {'Net annual cost':>16}  {'vs base':>10}")
    for dc in [0.90, 1.10, 1.21, 1.50, 1.705, 1.80, 2.00]:
        p2 = copy.copy(baseline_plan)
        p2.daily_charge = dc
        r2 = model(buckets, p2)
        diff = r2.net_annual_cost - b_result.net_annual_cost
        print(f"  {dc*100:>12.1f}c  {fmt_dollar(r2.net_annual_cost)}  {'+' if diff>=0 else ''}{fmt_dollar(diff)}")

    print("\n  (c) Red evening FiT sensitivity (all other Red rates fixed):")
    red_plan = next((p for p in PLANS if "Red" in p.name and "16c" not in p.name and "UNVERIFIED" in p.name), None)
    if red_plan:
        print(f"  {'Evening FiT':>14}  {'Net annual cost':>16}  {'vs GloBird base':>16}")
        for fit in [0.10, 0.14, 0.16, 0.18, 0.20, 0.22, 0.25]:
            p2 = copy.copy(red_plan)
            p2.fit_red_premium = fit
            r2 = model(buckets, p2)
            diff = r2.net_annual_cost - b_result.net_annual_cost
            print(f"  {fit*100:>12.1f}c  {fmt_dollar(r2.net_annual_cost)}  {'+' if diff>=0 else ''}{fmt_dollar(diff)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_analysis.py <path-to-MeterDataReport.csv>")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    print(f"\nLoading {csv_path.name} ...")
    buckets = load_endeavour_csv(csv_path)
    months  = monthly_summary(buckets)
    profile = hourly_export_profile(csv_path)

    print_data_summary(buckets, months)
    print_export_profile(profile, len(buckets))

    # Model all plans
    results = [model(buckets, p) for p in PLANS]

    # Print ranked table first
    print_ranked_table(results)

    # Print detail for each plan
    baseline_cost = min(r.net_annual_cost for r in results)
    for r in sorted(results, key=lambda r: r.net_annual_cost):
        print_summary(r, baseline_cost=baseline_cost)

    # Sensitivity analysis around GloBird (our current plan)
    globird = PLANS[0]
    print_sensitivity(buckets, globird, results)

    print("\n\nDone.\n")


if __name__ == "__main__":
    main()
