"""
NEM12 5-minute interval data parser.

Parses a NEM12-style CSV export (as produced by Ausgrid/Endeavour portals)
and returns per-interval records bucketed by stream (E1=import, B1=export)
and time-of-use window.

TOU windows for Endeavour Energy (Sydney metro, AEST/AEDT):
  Peak:        16:00–23:00 (4 pm–11 pm) every day
  Shoulder:    07:00–16:00 + 23:00–00:00 (non-peak, non-off-peak)
  Off-peak:    00:00–07:00 + [special window: 11:00–14:00 per GloBird]
"""

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# TOU classification (Endeavour Energy zone, all days)
# ---------------------------------------------------------------------------
# GloBird ZEROHERO defines a special $0 off-peak window 11am–2pm on top of
# the standard midnight–7am off-peak.  We model three windows:
#   PEAK      16:00–23:00
#   OFFPEAK   00:00–07:00  and  11:00–14:00 (GloBird bonus $0 slot)
#   SHOULDER  everything else
#
# Other retailers collapse OFFPEAK/SHOULDER differently — the raw bucket data
# is per-30-min-hour so any re-classification is done downstream.

PEAK_START = 16   # inclusive hour
PEAK_END = 23     # exclusive end (23:00 means up to but not including 23:00)

OFFPEAK_MORNING_END = 7      # 00:00–07:00
OFFPEAK_MIDDAY_START = 11    # 11:00–14:00
OFFPEAK_MIDDAY_END = 14


def classify_tou(dt: datetime) -> str:
    """Return 'peak', 'offpeak', or 'shoulder' for a given datetime (AEST/AEDT local)."""
    h = dt.hour
    if PEAK_START <= h < PEAK_END:
        return "peak"
    if h < OFFPEAK_MORNING_END:
        return "offpeak"
    if OFFPEAK_MIDDAY_START <= h < OFFPEAK_MIDDAY_END:
        return "offpeak"
    return "shoulder"


def is_evening_export_window(dt: datetime) -> bool:
    """True if within GloBird Super Export / Red evening FiT window (18:00–20:00)."""
    return 18 <= dt.hour < 20


def is_fit_window_globird(dt: datetime) -> bool:
    """GloBird FiT window: 16:00–21:00 (2c base, up to 10c in 18-20 window)."""
    return 16 <= dt.hour < 21


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class IntervalRecord:
    timestamp: datetime   # start of interval (local time)
    stream: str           # 'E1' (import) or 'B1' (export)
    kwh: float            # energy in kWh for this interval
    tou: str              # 'peak' | 'shoulder' | 'offpeak'
    is_evening_export: bool
    is_fit_window: bool


@dataclass
class DailyBuckets:
    date: str             # YYYY-MM-DD
    # import kWh by TOU window
    import_peak: float = 0.0
    import_shoulder: float = 0.0
    import_offpeak: float = 0.0
    # export kWh total and evening sub-window
    export_total: float = 0.0
    export_evening: float = 0.0   # 18:00–20:00 (Super Export / Red evening window)
    export_fit_window: float = 0.0  # 16:00–21:00 (GloBird FiT window)


# ---------------------------------------------------------------------------
# NEM12 parser (handles both proper NEM12 and simplified flat CSV exports)
# ---------------------------------------------------------------------------

def _parse_nem12(path: Path) -> Iterator[IntervalRecord]:
    """
    Parse a NEM12 CSV file.

    Supports two layouts:
    1. Proper NEM12: 100/200/300/400/900 record types.
    2. Flat export (some portal exports): columns like
       [date, time, E1_kwh, quality] or [date, time, B1_kwh, quality]
       — auto-detected by checking for a 300-record prefix.
    """
    text = path.read_text(encoding="utf-8-sig")  # strip BOM if present
    lines = [l.rstrip("\n\r") for l in text.splitlines() if l.strip()]

    if not lines:
        raise ValueError(f"Empty file: {path}")

    # Detect format by first field of first line
    first_field = lines[0].split(",")[0].strip()

    if first_field == "100":
        yield from _parse_proper_nem12(lines)
    else:
        yield from _parse_flat_csv(lines, path)


def _parse_proper_nem12(lines: list[str]) -> Iterator[IntervalRecord]:
    """Parse standard NEM12 format (100/200/300/400/900 records)."""
    current_nmi = None
    current_stream = None
    interval_length = 30  # minutes, default; overridden by 200 record

    for line in lines:
        parts = line.split(",")
        rec_type = parts[0].strip()

        if rec_type == "200":
            # 200,NMI,NMIConfig,RegisterID,NMISuffix,MDMDataStreamID,MeterSerial,
            #     UOM,IntervalLength,...
            current_nmi = parts[1].strip() if len(parts) > 1 else None
            suffix = parts[4].strip() if len(parts) > 4 else ""
            current_stream = suffix if suffix else (parts[2].strip() if len(parts) > 2 else "E1")
            try:
                interval_length = int(parts[8].strip()) if len(parts) > 8 and parts[8].strip() else 30
            except ValueError:
                interval_length = 30

        elif rec_type == "300":
            # 300,YYYYMMDD,v1,v2,...,vN,quality,reasonCode,reasonDescription,updateDateTime
            if current_stream is None:
                continue
            date_str = parts[1].strip()
            try:
                base_date = datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                continue

            # Intervals start at 00:interval_length and end at 24:00
            # parts[2] onwards are interval values until quality flag (single letter)
            intervals_per_day = 1440 // interval_length
            values = []
            for p in parts[2:]:
                p = p.strip()
                if re.match(r"^[A-Z]$", p):
                    break  # quality flag
                try:
                    values.append(float(p))
                except ValueError:
                    break

            for i, kwh in enumerate(values[:intervals_per_day]):
                minutes_offset = (i + 1) * interval_length
                dt = base_date + timedelta(minutes=minutes_offset - interval_length)
                tou = classify_tou(dt)
                yield IntervalRecord(
                    timestamp=dt,
                    stream=current_stream,
                    kwh=kwh,
                    tou=tou,
                    is_evening_export=is_evening_export_window(dt),
                    is_fit_window=is_fit_window_globird(dt),
                )


def _parse_flat_csv(lines: list[str], path: Path) -> Iterator[IntervalRecord]:
    """
    Parse a flat CSV export (Endeavour / Ausgrid portal style).

    Expected columns (auto-detected):
      Date, Time, Stream/Channel, kWh, Quality
    or:
      Date, StartTime, E1, B1, Quality
    """
    reader = csv.DictReader(iter(lines))
    if reader.fieldnames is None:
        raise ValueError(f"Cannot determine CSV columns in {path}")

    headers_lower = [h.lower().strip() for h in reader.fieldnames]

    # Detect column names flexibly
    def _col(*candidates) -> str | None:
        for c in candidates:
            if c.lower() in headers_lower:
                return reader.fieldnames[headers_lower.index(c.lower())]
        return None

    date_col = _col("date", "read_date", "interval_date")
    time_col = _col("time", "start_time", "interval_time", "starttime")
    e1_col = _col("e1", "import", "grid_import", "consumption")
    b1_col = _col("b1", "export", "grid_export", "generation")
    stream_col = _col("stream", "channel", "register", "suffix")
    kwh_col = _col("kwh", "value", "energy", "reading")

    if date_col is None or time_col is None:
        raise ValueError(
            f"Cannot find date/time columns in {path}. Headers: {reader.fieldnames}"
        )

    for row in reader:
        date_str = row[date_col].strip()
        time_str = row[time_col].strip()

        # Flexible date parsing
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
            try:
                base_date = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        else:
            continue  # unparseable row

        # Flexible time parsing
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
            try:
                t = datetime.strptime(time_str, fmt)
                dt = base_date.replace(hour=t.hour, minute=t.minute, second=0)
                break
            except ValueError:
                continue
        else:
            continue

        tou = classify_tou(dt)
        ev = is_evening_export_window(dt)
        fw = is_fit_window_globird(dt)

        if e1_col and b1_col:
            # Both streams in one row
            try:
                e1_kwh = float(row[e1_col]) if row[e1_col].strip() else 0.0
                yield IntervalRecord(dt, "E1", e1_kwh, tou, ev, fw)
            except (ValueError, KeyError):
                pass
            try:
                b1_kwh = float(row[b1_col]) if row[b1_col].strip() else 0.0
                yield IntervalRecord(dt, "B1", b1_kwh, tou, ev, fw)
            except (ValueError, KeyError):
                pass
        elif stream_col and kwh_col:
            stream = row[stream_col].strip().upper()
            try:
                kwh = float(row[kwh_col]) if row[kwh_col].strip() else 0.0
            except ValueError:
                continue
            yield IntervalRecord(dt, stream, kwh, tou, ev, fw)
        else:
            raise ValueError(
                f"Cannot identify stream/kwh columns. Headers: {reader.fieldnames}"
            )


# ---------------------------------------------------------------------------
# Aggregate into daily buckets
# ---------------------------------------------------------------------------

def aggregate_daily(records: Iterator[IntervalRecord]) -> dict[str, DailyBuckets]:
    buckets: dict[str, DailyBuckets] = {}
    for r in records:
        day = r.timestamp.strftime("%Y-%m-%d")
        if day not in buckets:
            buckets[day] = DailyBuckets(date=day)
        b = buckets[day]
        if r.stream == "E1":
            if r.tou == "peak":
                b.import_peak += r.kwh
            elif r.tou == "offpeak":
                b.import_offpeak += r.kwh
            else:
                b.import_shoulder += r.kwh
        elif r.stream == "B1":
            b.export_total += r.kwh
            if r.is_evening_export:
                b.export_evening += r.kwh
            if r.is_fit_window:
                b.export_fit_window += r.kwh

    return dict(sorted(buckets.items()))


def load_csv(path: str | Path) -> dict[str, DailyBuckets]:
    p = Path(path)
    records = _parse_nem12(p)
    return aggregate_daily(records)
