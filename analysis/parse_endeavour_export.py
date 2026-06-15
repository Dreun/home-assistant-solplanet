"""
Parser for the Endeavour Energy / AusNet portal "MeterDataReport" CSV format.

Structure of the file:
  Row 1:  NMI metadata
  Row 2:  Stream ID (e.g. B1=export, E1=import)
  Row 3:  LOCAL TIME, AEST
  Row 4:  Header: "Date/Time", "0:00", "0:05", ..., "23:55", "Quality", "Total"
  Row 5+: YYYYMMDD, 288 x 5-min kWh values, Quality flag, Daily total

The same 4-row header / N-row data block repeats for each stream (B1, E1, K1, Q1...).
We only extract B1 (grid export) and E1 (grid import).

TOU windows for Endeavour Energy zone (AEST / no DST adjustment needed for billing):
  Peak:      16:00–23:00 every day
  Off-peak:  00:00–07:00  (standard night window)
  GloBird off-peak bonus: 11:00–14:00  ($0 special window)
  Shoulder:  everything else (07:00–11:00, 14:00–16:00, 23:00–00:00)

Export sub-windows captured:
  Evening FiT window (GloBird / Red): 16:00–21:00
  Super Export window (GloBird):      18:00–20:00
  Red premium window:                 16:00–20:00
"""

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# TOU classification
# ---------------------------------------------------------------------------

def hour_tou(hour: int) -> str:
    """
    Returns ('peak'|'offpeak_night'|'offpeak_midday'|'shoulder') for a given hour (0-23).

    offpeak_night  = 00:00-07:00  (also $0 on GloBird)
    offpeak_midday = 11:00-14:00  ($0 GloBird bonus; shoulder on other plans)
    peak           = 16:00-23:00
    shoulder       = everything else
    """
    if 16 <= hour < 23:
        return "peak"
    if hour < 7:
        return "offpeak_night"
    if 11 <= hour < 14:
        return "offpeak_midday"
    return "shoulder"


def col_index_to_hour(col: int) -> int:
    """Column index (0-287) → hour of day (0-23)."""
    return (col * 5) // 60


# ---------------------------------------------------------------------------
# Daily aggregation structure
# ---------------------------------------------------------------------------

@dataclass
class DayBuckets:
    date_str: str

    # Import kWh by TOU window
    import_peak: float = 0.0
    import_shoulder: float = 0.0
    import_offpeak_night: float = 0.0
    import_offpeak_midday: float = 0.0   # 11-14h (GloBird $0; shoulder on others)

    # Export kWh by sub-window
    export_total: float = 0.0
    export_peak_window: float = 0.0     # 16:00-23:00 (same as peak import)
    export_fit_globird: float = 0.0     # 16:00-21:00 (GloBird FiT window)
    export_super_export: float = 0.0    # 18:00-20:00 (GloBird Super Export)
    export_red_premium: float = 0.0     # 16:00-20:00 (Red evening premium)
    export_fit_red_base: float = 0.0    # 20:00-21:00 (Red base FiT non-premium)

    # Raw 5-minute series for the hourly profile (list of (hour, kwh) for export)
    # Not stored by default to keep memory light — populated by load_csv if requested.


# ---------------------------------------------------------------------------
# Parse the file
# ---------------------------------------------------------------------------

def _parse_stream_block(lines: list[str]) -> dict[str, list[float]]:
    """
    Given the data rows of one stream block (after skipping the 3-line header),
    return {date_str: [288 float values]}.
    The last two columns (Quality, Total) are stripped.
    """
    reader = csv.reader(lines)
    result = {}
    for row in reader:
        if not row or not row[0].strip().isdigit():
            continue
        date_str_raw = row[0].strip()
        if len(date_str_raw) != 8:
            continue
        # Parse YYYYMMDD → YYYY-MM-DD
        date_str = f"{date_str_raw[:4]}-{date_str_raw[4:6]}-{date_str_raw[6:8]}"
        # Columns 1..288 are interval values; col 289 = Quality; col 290 = Total
        values = []
        for cell in row[1:289]:
            try:
                values.append(float(cell))
            except ValueError:
                values.append(0.0)
        # Pad if short
        while len(values) < 288:
            values.append(0.0)
        result[date_str] = values
    return result


def load_endeavour_csv(path: str | Path) -> dict[str, DayBuckets]:
    """
    Parse a MeterDataReport CSV and return per-day aggregated buckets.

    Handles multiple stream sections (B1, E1, K1, Q1).
    Only B1 (export) and E1 (import) are processed.
    """
    p = Path(path)
    raw_lines = p.read_text(encoding="utf-8-sig").splitlines()

    # Split into stream blocks: each block starts with "Stream ID,..."
    # followed by "LOCAL TIME,AEST", then header row, then data rows.
    stream_blocks: dict[str, list[str]] = {}  # stream_code → data lines
    current_stream = None
    skip_count = 0  # lines to skip after detecting stream header

    for line in raw_lines:
        stripped = line.strip()
        if stripped.startswith("Stream ID,"):
            # Parse stream code from e.g.: Stream ID,"Meter...",B1,B1,KWH,Solar
            parts = next(csv.reader([stripped]))
            # parts[2] is typically the stream code
            current_stream = parts[2].strip() if len(parts) > 2 else None
            skip_count = 2  # skip "LOCAL TIME" and the header column row
            stream_blocks[current_stream] = []
            continue
        if current_stream is not None:
            if skip_count > 0:
                skip_count -= 1
                continue
            stream_blocks[current_stream].append(line)

    b1_data = _parse_stream_block(stream_blocks.get("B1", []))
    e1_data = _parse_stream_block(stream_blocks.get("E1", []))

    # Merge into DayBuckets
    all_dates = sorted(set(b1_data) | set(e1_data))
    result: dict[str, DayBuckets] = {}

    for ds in all_dates:
        b = DayBuckets(date_str=ds)

        # --- Import (E1) ---
        for col, kwh in enumerate(e1_data.get(ds, [])):
            if kwh <= 0:
                continue
            h = col_index_to_hour(col)
            tou = hour_tou(h)
            if tou == "peak":
                b.import_peak += kwh
            elif tou == "offpeak_night":
                b.import_offpeak_night += kwh
            elif tou == "offpeak_midday":
                b.import_offpeak_midday += kwh
            else:
                b.import_shoulder += kwh

        # --- Export (B1) ---
        for col, kwh in enumerate(b1_data.get(ds, [])):
            if kwh <= 0:
                continue
            h = col_index_to_hour(col)
            b.export_total += kwh
            if 16 <= h < 23:
                b.export_peak_window += kwh
            if 16 <= h < 21:
                b.export_fit_globird += kwh
            if 18 <= h < 20:
                b.export_super_export += kwh
            if 16 <= h < 20:
                b.export_red_premium += kwh
            if 20 <= h < 21:
                b.export_fit_red_base += kwh

        result[ds] = b

    return result


# ---------------------------------------------------------------------------
# Hourly export profile (for visualisation / verification)
# ---------------------------------------------------------------------------

def hourly_export_profile(path: str | Path) -> dict[int, float]:
    """
    Return total kWh exported per hour of day (0-23), summed over all days.
    Useful for verifying the battery-discharge signature.
    """
    p = Path(path)
    raw_lines = p.read_text(encoding="utf-8-sig").splitlines()

    # Extract B1 only
    in_b1 = False
    skip_count = 0
    b1_lines = []
    for line in raw_lines:
        stripped = line.strip()
        if stripped.startswith("Stream ID,"):
            parts = next(csv.reader([stripped]))
            in_b1 = (parts[2].strip() == "B1") if len(parts) > 2 else False
            skip_count = 2
            continue
        if in_b1:
            if skip_count > 0:
                skip_count -= 1
                continue
            if stripped.startswith("Stream ID,"):
                in_b1 = False
                continue
            b1_lines.append(line)

    b1_data = _parse_stream_block(b1_lines)

    hourly: dict[int, float] = defaultdict(float)
    for day_vals in b1_data.values():
        for col, kwh in enumerate(day_vals):
            if kwh > 0:
                h = col_index_to_hour(col)
                hourly[h] += kwh

    return dict(sorted(hourly.items()))


# ---------------------------------------------------------------------------
# Monthly summary
# ---------------------------------------------------------------------------

def monthly_summary(buckets: dict[str, DayBuckets]) -> dict[str, dict]:
    months: dict[str, dict] = {}
    for ds, b in buckets.items():
        ym = ds[:7]  # YYYY-MM
        if ym not in months:
            months[ym] = dict(
                days=0,
                import_peak=0.0, import_shoulder=0.0,
                import_offpeak_night=0.0, import_offpeak_midday=0.0,
                import_total=0.0,
                export_total=0.0, export_super_export=0.0,
                export_fit_globird=0.0, export_red_premium=0.0,
            )
        m = months[ym]
        m["days"] += 1
        m["import_peak"] += b.import_peak
        m["import_shoulder"] += b.import_shoulder
        m["import_offpeak_night"] += b.import_offpeak_night
        m["import_offpeak_midday"] += b.import_offpeak_midday
        m["import_total"] += (b.import_peak + b.import_shoulder
                               + b.import_offpeak_night + b.import_offpeak_midday)
        m["export_total"] += b.export_total
        m["export_super_export"] += b.export_super_export
        m["export_fit_globird"] += b.export_fit_globird
        m["export_red_premium"] += b.export_red_premium

    return dict(sorted(months.items()))
