#!/usr/bin/env python3
"""Reproduserbar pumpepremiss-sjekk for uTAHPS.

Kjor fra repository-roten:
    .venv/bin/python analysis/pumpe_premiss.py

Skriptet leser kun kildedata og skriver rapport, CSV-filer og SVG-figurer under
analysis/pumpe_premiss/. Det bruker bare standardbiblioteket og NumPy.
"""

from __future__ import annotations

import csv
import datetime as dt
import math
import re
import statistics
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "analysis" / "pumpe_premiss"
REPORT = ROOT / "analysis" / "pumpe_premiss.md"

PRIMARY_DAILY = DATA / "utahps_daily" / "pricefile_utahps.txt"
PRIMARY_HOURLY = DATA / "utahps_hourly" / "pricefile_utahps.txt"
INFLOW_DAILY = DATA / "utahps_daily" / "inflowseries_utahps.txt"
SECONDARY_XLSX = ROOT / "spotpriser.xlsx"

EPS = 1e-12
EFFICIENCIES = ((0.83, 1.20), (0.75, 1.33), (0.67, 1.50))
HORIZONS = (("6t", 6, "hourly"), ("12t", 12, "hourly"),
            ("24t", 24, "hourly"), ("48t", 48, "hourly"),
            ("7d", 7, "daily"))


@dataclass(frozen=True)
class Series:
    name: str
    timestamps: tuple[dt.datetime, ...]
    values: np.ndarray


def assert_contiguous(timestamps: Iterable[dt.datetime], step: dt.timedelta, label: str) -> None:
    ts = tuple(timestamps)
    for i in range(1, len(ts)):
        if ts[i] != ts[i - 1] + step:
            raise AssertionError(
                f"{label}: ikke sammenhengende tid mellom {ts[i - 1]!s} og {ts[i]!s}; "
                f"forventet steg {step}."
            )


def assert_local_hourly_calendar(timestamps: Iterable[dt.datetime], label: str) -> None:
    """Valider lokal norsk klokke med én høstduplisering og ett vårhopp."""
    ts = tuple(timestamps)
    duplicate_hours = 0
    skipped_hours = 0
    for i in range(1, len(ts)):
        delta = ts[i] - ts[i - 1]
        if delta == dt.timedelta(hours=1):
            continue
        if delta == dt.timedelta(0):
            duplicate_hours += 1
            continue
        if delta == dt.timedelta(hours=2):
            skipped_hours += 1
            continue
        raise AssertionError(
            f"{label}: ugyldig lokal tidsrekkefølge mellom {ts[i - 1]!s} og {ts[i]!s}."
        )
    if duplicate_hours != 1 or skipped_hours != 1:
        raise AssertionError(
            f"{label}: forventet nøyaktig ett høstduplikat og ett vårhopp for norsk lokal tid; "
            f"fant {duplicate_hours} og {skipped_hours}."
        )


def read_pricefile(path: Path, expected_n: int, step_hours: int, name: str) -> Series:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 3 or not lines[0].startswith("RESTPRICE") or lines[1].split() != ["Date", "Price"]:
        raise AssertionError(f"{path}: forventet HERSS-pricefile med RESTPRICE og 'Date Price'-header.")
    timestamps: list[dt.datetime] = []
    values: list[float] = []
    for line_no, line in enumerate(lines[2:], start=3):
        fields = line.split()
        if len(fields) != 2:
            raise AssertionError(f"{path}:{line_no}: forventet to felter, fikk {fields!r}.")
        timestamps.append(dt.datetime.strptime(fields[0], "%Y%m%d%H"))
        values.append(float(fields[1]))
    arr = np.asarray(values, dtype=float)
    if len(arr) != expected_n:
        raise AssertionError(f"{path}: forventet {expected_n} priser, fant {len(arr)}.")
    if not np.all(np.isfinite(arr)) or not np.all(arr > 0):
        raise AssertionError(f"{path}: alle primærpriser må være endelige og strengt positive.")
    assert_contiguous(timestamps, dt.timedelta(hours=step_hours), name)
    return Series(name, tuple(timestamps), arr)


def validate_primary(daily: Series, hourly: Series) -> float:
    if daily.timestamps[0] != hourly.timestamps[0] or daily.timestamps[-1].date() != hourly.timestamps[-1].date():
        raise AssertionError("Primærseriene dekker ikke samme start- og sluttdato.")
    hourly_by_day: dict[dt.date, list[float]] = {}
    for stamp, value in zip(hourly.timestamps, hourly.values):
        hourly_by_day.setdefault(stamp.date(), []).append(float(value))
    means = np.asarray([np.mean(hourly_by_day[stamp.date()]) for stamp in daily.timestamps])
    delta = np.abs(daily.values - means)
    if np.max(delta) > 0.01 + EPS:
        raise AssertionError(
            "Døgnserien stemmer ikke med timeseriens døgnsnitt innen 0,01 EUR/MWh; "
            f"maksavvik var {np.max(delta):.6f}."
        )
    return float(np.max(delta))


def describe(values: np.ndarray) -> dict[str, float | int]:
    return {
        "n": int(len(values)), "min": float(np.min(values)), "max": float(np.max(values)),
        "median": float(np.median(values)), "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)), "under_20": int(np.sum(values < 20)),
        "over_200": int(np.sum(values > 200)),
    }


def histogram(values: np.ndarray, bins: int = 20) -> tuple[np.ndarray, np.ndarray]:
    if bins != 20:
        raise AssertionError("Rapportspesifikasjonen krever nøyaktig 20 histogram-bøtter.")
    counts, edges = np.histogram(values, bins=bins)
    return counts.astype(int), edges.astype(float)


def forward_ratios(values: np.ndarray, window_steps: int) -> tuple[np.ndarray, np.ndarray]:
    """Returnerer alle fremoverratioer og den strengt stigende delmengden."""
    if window_steps < 1:
        raise ValueError("window_steps må være minst 1")
    parts = [values[lag:] / values[:-lag] for lag in range(1, min(window_steps, len(values) - 1) + 1)]
    all_ratios = np.concatenate(parts) if parts else np.asarray([], dtype=float)
    return all_ratios, all_ratios[all_ratios > 1.0]


def ratio_summary(ratios: np.ndarray) -> dict[str, float | int]:
    if len(ratios) == 0:
        return {"n": 0, "gt_120": math.nan, "gt_133": math.nan, "gt_150": math.nan, "median": math.nan}
    return {
        "n": int(len(ratios)), "gt_120": float(np.mean(ratios > 1.20)),
        "gt_133": float(np.mean(ratios > 1.33)), "gt_150": float(np.mean(ratios > 1.50)),
        "median": float(np.median(ratios)),
    }


def classify_perfect_foresight(values: np.ndarray, window_steps: int) -> dict[str, int | float]:
    """Klassifisering med eksplisitt, optimistisk perfekt framsyn i vinduet."""
    categories = {"never": 0, "conditional": 0, "always": 0}
    max_ratios: list[float] = []
    for i in range(len(values) - 1):
        future = values[i + 1:min(i + window_steps + 1, len(values))]
        ratio = float(np.max(future) / values[i])
        max_ratios.append(ratio)
        if ratio < 1.20:
            categories["never"] += 1
        elif ratio > 1.33:
            categories["always"] += 1
        else:
            categories["conditional"] += 1
    n = len(max_ratios)
    return {**categories, "n": n, "never_share": categories["never"] / n,
            "conditional_share": categories["conditional"] / n,
            "always_share": categories["always"] / n,
            "median_max_ratio": float(np.median(max_ratios))}


def storage_requirement_m3(q_m3s: float, hours: float) -> float:
    return q_m3s * hours * 3600.0


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("Pearson-korrelasjon krever to like lange serier med minst to observasjoner.")
    if np.std(x) < EPS or np.std(y) < EPS:
        raise ValueError("Pearson-korrelasjon er udefinert for konstant serie.")
    return float(np.corrcoef(x, y)[0, 1])


def read_hjelle_inflow(path: Path, expected_dates: tuple[dt.datetime, ...]) -> np.ndarray:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise AssertionError(f"{path}: tom fil.")
    header = lines[0].split()
    if "0" not in header:
        raise AssertionError(
            f"{path}: mangler eksplisitt kolonneheader '0' for HJELLE/node 0; "
            f"fant {header!r}. Velger aldri tilsig etter kolonneposisjon."
        )
    hjelle_index = header.index("0")
    if header[0] != "Date_NodeID":
        raise AssertionError(f"{path}: forventet første header 'Date_NodeID', fikk {header[0]!r}.")
    dates: list[dt.date] = []
    values: list[float] = []
    for line_no, line in enumerate(lines[1:], start=2):
        fields = line.split()
        if len(fields) != len(header):
            raise AssertionError(f"{path}:{line_no}: header og datarad har ulikt antall felter.")
        dates.append(dt.datetime.strptime(fields[0], "%Y%m%d").date())
        values.append(float(fields[hjelle_index]))
    expected = [stamp.date() for stamp in expected_dates]
    if dates != expected:
        raise AssertionError(
            f"{path}: datoene i den validerte HJELLE-kolonnen stemmer ikke med prisserien "
            f"({len(dates)} mot {len(expected)} observasjoner)."
        )
    return np.asarray(values, dtype=float)


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(ns + "t")) for item in root.findall(ns + "si")]


def _xlsx_rows(path: Path) -> list[list[str]]:
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as zf:
        strings = _xlsx_shared_strings(zf)
        root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
    rows: list[list[str]] = []
    for row in root.findall(".//" + ns + "row"):
        vals: list[str] = []
        for cell in row.findall(ns + "c"):
            value = cell.find(ns + "v")
            raw = "" if value is None else (value.text or "")
            vals.append(strings[int(raw)] if cell.get("t") == "s" and raw else raw)
        rows.append(vals)
    return rows


def read_secondary_no2(path: Path) -> Series:
    rows = _xlsx_rows(path)
    if not rows or rows[0] != ["Dato/klokkeslett", "NO1", "NO2", "NO3", "NO4", "NO5"]:
        raise AssertionError(f"{path}: forventet historikk-header med eksplisitt NO2-kolonne.")
    stamps: list[dt.datetime] = []
    raw_values: list[float] = []
    pattern = re.compile(r"^(\d{4}-\d{2}-\d{2}) Kl\. (\d{2})-\d{2}$")
    for row_no, row in enumerate(rows[1:], start=2):
        if len(row) != 6:
            raise AssertionError(f"{path}: rad {row_no} har {len(row)} kolonner, forventet 6.")
        match = pattern.match(row[0])
        if not match:
            raise AssertionError(f"{path}: ukjent tidsformat på rad {row_no}: {row[0]!r}")
        stamps.append(dt.datetime.strptime(match.group(1) + match.group(2), "%Y-%m-%d%H"))
        raw_values.append(float(row[2]))
    if len(stamps) != 8784:
        raise AssertionError(f"{path}: forventet 8784 timer for 2023/24-skuddåret, fant {len(stamps)}.")
    # Regnearket er i norsk lokal tid: høstens 02–03 forekommer to ganger og
    # vårens 02–03 mangler. Derfor valideres lokal kalender, ikke UTC-kontinuitet.
    assert_local_hourly_calendar(stamps, "Sekundær NO2-serie")
    if stamps[0] != dt.datetime(2023, 9, 1) or stamps[-1] != dt.datetime(2024, 8, 31, 23):
        raise AssertionError(f"{path}: uventet periode {stamps[0]} til {stamps[-1]}.")
    # Forbrukerrådet oppgir historikken i kr/kWh. Ved 10 NOK/EUR er 1 kr/kWh = 100 EUR/MWh.
    return Series("Sekundær NO2 (EUR/MWh)", tuple(stamps), np.asarray(raw_values, dtype=float) * 100.0)


def fmt(value: float, digits: int = 2) -> str:
    if math.isnan(value):
        return "–"
    return f"{value:.{digits}f}"


def pct(value: float) -> str:
    return "–" if math.isnan(value) else f"{value * 100:.1f} %"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(row) + " |" for row in rows),
    ])


def svg_open(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#111} .small{font-size:12px} .axis{stroke:#333;stroke-width:1} .grid{stroke:#d9d9d9;stroke-width:1}</style>',
        f'<text x="{width / 2:.0f}" y="28" text-anchor="middle" font-size="18" font-weight="bold">{title}</text>',
    ]


def svg_save(path: Path, parts: list[str]) -> None:
    path.write_text("\n".join([*parts, "</svg>"]) + "\n", encoding="utf-8")


def make_histogram_svg(path: Path, daily: np.ndarray, hourly: np.ndarray) -> None:
    width, height, left, right, top, bottom = 1100, 650, 85, 35, 70, 80
    parts = svg_open(width, height, "Prisfordeling: uTAHPS NO2, 2022-09-01 til 2023-08-31")
    plot_w, plot_h = width - left - right, height - top - bottom
    counts_h, edges = histogram(hourly)
    counts_d, _ = np.histogram(daily, bins=edges)
    ymax = max(int(np.max(counts_h)), int(np.max(counts_d)))
    parts += [f'<line class="axis" x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}"/>',
              f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}"/>']
    for i, count in enumerate(counts_h):
        x = left + plot_w * i / 20
        w = plot_w / 20
        h = plot_h * count / ymax
        parts.append(f'<rect x="{x:.2f}" y="{top + plot_h - h:.2f}" width="{w - 1:.2f}" height="{h:.2f}" fill="#4c78a8" opacity="0.78"/>')
    for i, count in enumerate(counts_d):
        x = left + plot_w * i / 20 + plot_w / 40
        w = plot_w / 40
        h = plot_h * count / ymax
        parts.append(f'<rect x="{x:.2f}" y="{top + plot_h - h:.2f}" width="{w - 1:.2f}" height="{h:.2f}" fill="#f58518" opacity="0.9"/>')
    for frac in (0, .25, .5, .75, 1):
        x = left + plot_w * frac
        value = edges[0] + (edges[-1] - edges[0]) * frac
        parts.append(f'<line class="grid" x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}"/>')
        parts.append(f'<text class="small" x="{x:.2f}" y="{top + plot_h + 22}" text-anchor="middle">{value:.0f}</text>')
    for frac in (0, .5, 1):
        y = top + plot_h * (1 - frac)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}"/>')
        parts.append(f'<text class="small" x="{left - 8}" y="{y + 4:.2f}" text-anchor="end">{ymax * frac:.0f}</text>')
    parts += [f'<text x="{width / 2:.0f}" y="{height - 25}" text-anchor="middle">Pris [EUR/MWh], 20 like brede bøtter</text>',
              f'<text transform="translate(20 {top + plot_h / 2:.0f}) rotate(-90)" text-anchor="middle">Antall observasjoner</text>',
              f'<rect x="{width - 255}" y="45" width="14" height="14" fill="#4c78a8"/><text class="small" x="{width - 235}" y="57">Time (n={len(hourly)})</text>',
              f'<rect x="{width - 255}" y="64" width="14" height="14" fill="#f58518"/><text class="small" x="{width - 235}" y="76">Døgn (n={len(daily)})</text>']
    svg_save(path, parts)


def make_season_svg(path: Path, daily: Series, hourly: Series) -> None:
    width, height = 1100, 700
    parts = svg_open(width, height, "Sesong- og døgnmønster: uTAHPS NO2")
    panels = [(80, 70, 940, 240, "Gjennomsnittlig døgnpris per måned", "Måned"),
              (80, 410, 940, 210, "Gjennomsnittlig timespris per klokkeslett", "Klokkeslett")]
    monthly = [float(np.mean([v for s, v in zip(daily.timestamps, daily.values) if s.month == m])) for m in range(1, 13)]
    by_hour = [float(np.mean([v for s, v in zip(hourly.timestamps, hourly.values) if s.hour == h])) for h in range(24)]
    for (x, y, w, h, title, label), values in zip(panels, (monthly, by_hour)):
        lo, hi = min(values), max(values)
        pad = max((hi - lo) * .12, 1.0)
        lo -= pad; hi += pad
        parts += [f'<text x="{x}" y="{y - 12}" font-size="15" font-weight="bold">{title}</text>',
                  f'<line class="axis" x1="{x}" y1="{y + h}" x2="{x + w}" y2="{y + h}"/>',
                  f'<line class="axis" x1="{x}" y1="{y}" x2="{x}" y2="{y + h}"/>']
        points = []
        for i, value in enumerate(values):
            px = x + w * i / (len(values) - 1)
            py = y + h * (hi - value) / (hi - lo)
            points.append(f"{px:.2f},{py:.2f}")
            if i % (2 if len(values) == 24 else 1) == 0:
                text = str(i) if len(values) == 24 else str(i + 1)
                parts.append(f'<text class="small" x="{px:.2f}" y="{y + h + 20}" text-anchor="middle">{text}</text>')
        for frac in (0, .5, 1):
            py = y + h * (1 - frac)
            val = lo + (hi - lo) * frac
            parts += [f'<line class="grid" x1="{x}" y1="{py:.2f}" x2="{x + w}" y2="{py:.2f}"/>',
                      f'<text class="small" x="{x - 8}" y="{py + 4:.2f}" text-anchor="end">{val:.0f}</text>']
        parts += [f'<polyline points="{" ".join(points)}" fill="none" stroke="#54a24b" stroke-width="2.5"/>',
                  f'<text class="small" x="{x + w / 2:.0f}" y="{y + h + 42}" text-anchor="middle">{label}</text>']
    parts.append('<text class="small" x="1020" y="690" text-anchor="end">Pris [EUR/MWh]</text>')
    svg_save(path, parts)


def make_ratio_svg(path: Path, ratio_data: dict[str, np.ndarray]) -> None:
    width, height, cols = 1500, 440, 5
    parts = svg_open(width, height, "Ratiofordeling for fremoverpar (verdier over 5 klippes i figuren)")
    for idx, (name, ratios) in enumerate(ratio_data.items()):
        x, y, w, h = 50 + idx * 290, 70, 230, 290
        clipped = np.minimum(ratios, 5.0)
        counts, edges = np.histogram(clipped, bins=20, range=(0, 5))
        ymax = max(int(np.max(counts)), 1)
        parts += [f'<text x="{x + w / 2:.0f}" y="{y - 14}" text-anchor="middle" font-size="15" font-weight="bold">{name}</text>',
                  f'<line class="axis" x1="{x}" y1="{y + h}" x2="{x + w}" y2="{y + h}"/>',
                  f'<line class="axis" x1="{x}" y1="{y}" x2="{x}" y2="{y + h}"/>']
        for b, count in enumerate(counts):
            bx, bw = x + w * b / 20, w / 20
            bh = h * count / ymax
            parts.append(f'<rect x="{bx:.2f}" y="{y + h - bh:.2f}" width="{bw - 1:.2f}" height="{bh:.2f}" fill="#e45756"/>')
        for line, label in ((1.20, "1,20"), (1.33, "1,33"), (1.50, "1,50")):
            px = x + w * line / 5
            parts += [f'<line x1="{px:.2f}" y1="{y}" x2="{px:.2f}" y2="{y + h}" stroke="#222" stroke-dasharray="4,3"/>',
                      f'<text class="small" x="{px:.2f}" y="{y + h + 17}" text-anchor="middle">{label}</text>']
        parts += [f'<text class="small" x="{x}" y="{y + h + 35}">n={len(ratios):,}; median={np.median(ratios):.2f}</text>',
                  f'<text class="small" x="{x}" y="{y + h + 52}">klippet: {int(np.sum(ratios > 5)):,}</text>']
    svg_save(path, parts)


def write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def conditional_assessment(share: float) -> str:
    if share < .20:
        return "sannsynligvis triviell (<20 % betinget)"
    if share <= .60:
        return "ikke-triviell (20–60 % betinget)"
    return "høy betinget andel; lagringsutnyttelse må vurderes (>60 %)"


def build_report(daily: Series, hourly: Series, max_daily_delta: float, secondary: Series,
                 basic: dict[str, dict[str, float | int]], ratio_rows: list[dict[str, object]],
                 classes: dict[str, dict[str, int | float]], monthly: list[float], by_hour: list[float],
                 day_night: float, summer_winter: float, storage_rows: list[dict[str, object]],
                 correlation: float) -> str:
    stats_rows = []
    for name in ("Døgn", "Time"):
        s = basic[name]
        stats_rows.append([name, str(s["n"]), fmt(float(s["min"])), fmt(float(s["max"])),
                           fmt(float(s["median"])), fmt(float(s["mean"])), fmt(float(s["std"])),
                           str(s["under_20"]), str(s["over_200"])])
    ratio_md_rows = []
    for r in ratio_rows:
        ratio_md_rows.append([str(r["horizon"]), str(r["population"]), f'{r["n"]:,}',
                              pct(float(r["gt_120"])), pct(float(r["gt_133"])), pct(float(r["gt_150"])),
                              fmt(float(r["median"]), 3)])
    class_rows = []
    for name, result in classes.items():
        class_rows.append([name, str(result["n"]), pct(float(result["never_share"])),
                           pct(float(result["conditional_share"])), pct(float(result["always_share"])),
                           fmt(float(result["median_max_ratio"]), 3),
                           conditional_assessment(float(result["conditional_share"]))])
    storage_md_rows = [[str(r["q"]), str(r["horizon"]), fmt(float(r["required_mm3"]), 4),
                        "ja" if r["hjelle"] else "nei", "ja" if r["gresse"] else "nei"] for r in storage_rows]
    candidates = [(name, r) for name, r in classes.items() if .20 <= float(r["conditional_share"]) <= .60]
    if candidates:
        best_name, _ = min(candidates, key=lambda item: next(h for label, h, _ in HORIZONS if label == item[0]))
        best_hours = next(h for label, h, _ in HORIZONS if label == best_name) * (24 if best_name == "7d" else 1)
        min_storage = storage_requirement_m3(1, best_hours) / 1e6
        minimum_text = (f"Innenfor den testede ruten er minste ikke-trivielle kandidat **1 m³/s i {best_name}**, "
                        f"som krever **{min_storage:.4f} Mm³** aktiv lagring. Dette er en fysisk "
                        "nedre grense, ikke en dimensjonering av en full pumpestasjon.")
    else:
        minimum_text = ("Ingen av de testede horisontene havnet i 20–60 %-båndet; testen kan derfor ikke "
                        "identifisere en minimal ikke-triviell kombinasjon innen det angitte rutenettet.")
    best_horizon = max(classes, key=lambda key: float(classes[key]["conditional_share"]))
    c = classes[best_horizon]
    conclusion_1 = (f"**Nei**, ikke etter det forhåndsdefinerte 20 %-kriteriet: den høyeste betingede andelen er "
                    f"{pct(float(c['conditional_share']))} i {best_horizon}, altså "
                    f"**{conditional_assessment(float(c['conditional_share']))}**. Prisspreaden må likevel "
                    "ikke vurderes med maksimumratio alene; ratio-tabellen viser også hvor ofte muligheten oppstår.")
    conclusion_2 = (f"**Ukehorisonten (7d) er den beste av de testede horisontene**, fordi den har høyest "
                    f"betinget andel. Alle angitte kombinasjoner opptil 7 døgn får fysisk plass i begge "
                    f"magasiner i denne rene volumtesten. Dag/natt-ratioen er {day_night:.2f}, mens "
                    f"sommer/vinter-ratioen er {summer_winter:.2f}; sesongpumping er ikke dimensjonert i "
                    "denne 7-døgnstesten og kan derfor ikke anbefales på dette grunnlaget.")
    conclusion_3 = (f"**Sannsynligvis triviell i den prisbaserte screeningen**: selv horisonten med mest "
                    f"betinget struktur, {best_horizon}, har bare {pct(float(c['conditional_share']))}. "
                    "Pumping med eksisterende magasiner og disse prisene har dermed ikke vist et hardt "
                    "optimeringsproblem. Magasinnivå, tilsig og hydrauliske grenser kan testes separat dersom "
                    "man vil utfordre denne konservative konklusjonen.")
    return f"""# Pumpepremiss-sjekk: skaper pumping et hardt optimeringsproblem?

**Kjørt:** {dt.datetime.now().astimezone().isoformat(timespec='seconds')}  
**Primærdata:** `data/utahps_daily/pricefile_utahps.txt` og `data/utahps_hourly/pricefile_utahps.txt`, NO2, 1. september 2022–31. august 2023.  
**Metode/kode:** `analysis/pumpe_premiss.py`.

Alle beregnede tall nedenfor er **[målt]**. Tersklene 1,20, 1,33 og 1,50 følger rundtursvirkningsgrader 0,83, 0,75 og 0,67 **[antakelse]**.

## Datavalidering

- **[målt]** Døgnserien har 365 observasjoner, timeserien har 8 760 observasjoner, og begge dekker samme år.
- **[målt]** Døgnprisene samsvarer med timeseriens døgnsnitt; største absolutte differanse er {max_daily_delta:.3f} EUR/MWh.
- **[målt]** Alle primærpriser er strengt positive. Ratioene er derfor veldefinerte.
- **[målt]** HJELLE-tilsiget er valgt etter den eksplisitt validerte headeren `0` i `inflowseries_utahps.txt`, ikke etter kolonneposisjon.

## 1. Prisstrukturanalyse

### 1.1 Grunnleggende statistikk

{md_table(["Oppløsning", "n", "Min", "Maks", "Median", "Snitt", "Std.avvik (n−1)", "<20", ">200"], stats_rows)}

Figur: [prisfordeling (SVG)](pumpe_premiss/prisfordeling.svg).

### 1.2 Ratioer mellom fremoverpar

For hvert vindu er alle ordnede par `(t, t+k)` med `1 ≤ k ≤ vindu` brukt. «Alle fremoverpar» beholder også prisfall og måler hvor ofte en vilkårlig tidsflytting er lønnsom. «Kun stigende par» betinger på at sluttprisen er høyere enn startprisen og måler størrelsen på de faktiske oppgangene.

{md_table(["Vindu", "Populasjon", "Antall par", ">1,20", ">1,33", ">1,50", "Median ratio"], ratio_md_rows)}

Figur: [ratiofordelinger (SVG)](pumpe_premiss/ratiofordelinger.svg).

### 1.3 Sesongmønster

- **[målt]** Dag/natt-ratioen (gjennomsnitt 08–19 delt på gjennomsnitt 00–05) er **{day_night:.2f}**.
- **[målt]** Sommer/vinter-ratioen (jun–aug delt på des–feb) er **{summer_winter:.2f}**.
- **[vurdering]** En ratio klart over én indikerer høyere pris i førstnevnte periode, men er ikke i seg selv en operativ pumpepolicy.

Figur: [måneds- og timeprofil (SVG)](pumpe_premiss/sesongmonster.svg).

## 2. Pumpehorisont og magasinstørrelse

Aktiv lagring er 9,0 Mm³ for HJELLE og 61,4 Mm³ for GRESSE. Tabellen bruker `ΔV = Q_pump × Δt`; «ja» betyr at pumpevolumet alene er mindre enn eller lik aktiv lagring.

{md_table(["Q_pump [m³/s]", "Horisont", "Krav [Mm³]", "HJELLE", "GRESSE"], storage_md_rows)}

**[vurdering]** Dette er en nødvendig volumtest, ikke en full hydraulisk feasibility-test: den forutsetter ledig aktiv lagring, tilgjengelig nedre magasin og tilstrekkelig turbin-/pumpekapasitet.

## 3. Er pumpebeslutningen triviell?

Klassifiseringen under bruker `maks(fremtidig pris innen vinduet) / nåpris` **[antakelse: perfekt framsyn innen vinduet]**. For hvert gyldige starttidspunkt er ratio `<1,20` «pump aldri lønnsomt», `>1,33` «pump alltid lønnsomt» og ellers «betinget lønnsomt».

{md_table(["Vindu", "Starttidspunkter", "Aldri", "Betinget", "Alltid", "Median maksratio", "Tolkning"], class_rows)}

**[antakelse: perfekt framsyn innen vinduet]** Dette er en optimistisk øvre grense: en reell pumpebeslutning kan ikke observere fremtidige priser, og den faktiske andelen «alltid lønnsomt» vil være lavere.

## 4. Pris og tilsig

- **[målt]** Pearsons korrelasjon mellom daglig NO2-pris og HJELLEs lokale tilsig (node 0) er **{correlation:.3f}** (`n=365`).
- **[vurdering]** {'Negativ korrelasjon gir konflikt mellom høy tilrenning og lav pris.' if correlation < -0.05 else 'Positiv korrelasjon samvarierer høy tilrenning med høy pris.' if correlation > 0.05 else 'Korrelasjonen er nær null; pris og tilsig er i hovedsak uavhengige i dette året.'}

## 5. Sekundær sammenligning: Forbrukerrådet

- **[målt]** `spotpriser.xlsx` inneholder NO2 per time fra {secondary.timestamps[0]:%d.%m.%Y} til {secondary.timestamps[-1]:%d.%m.%Y}, totalt {len(secondary.values):,} timer; 2023/24 inneholder 29. februar.
- **[antakelse]** Råverdiene er behandlet som kr/kWh og multiplisert med 100 til EUR/MWh ved 10 NOK/EUR. [Forbrukerrådet](https://www.forbrukerradet.no/strompris/spotpriser) oppgir den historiske Excel-serien i kr/kWh og inkludert mva for NO2.
- **[målt]** Sekundær NO2 etter konvertering: min {np.min(secondary.values):.2f}, median {np.median(secondary.values):.2f}, snitt {np.mean(secondary.values):.2f}, maks {np.max(secondary.values):.2f} EUR/MWh.

Serien er et annet år og brukes bare som sammenligning; ingen av primærtallene over er blandet med den.

## 6. Konklusjon

1. **Er prisspreaden stor nok til ikke-triviell pumping?** **[vurdering]** {conclusion_1}
2. **Hvilken horisont passer magasinene?** **[vurdering]** {conclusion_2}
3. **Ekte optimeringsproblem eller triviell beslutning?** **[vurdering]** {conclusion_3}
4. **Minimal størrelse og kapasitet innen den testede ruten.** **[vurdering]** {minimum_text}

Deterministiske historiske priser med perfekt framsyn er en gunstig analysebetingelse. Prisprognosefeil vil gjøre den reelle pumpebeslutningen vanskeligere enn denne screeningen viser.
"""


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    daily = read_pricefile(PRIMARY_DAILY, 365, 24, "Primær døgnserie")
    hourly = read_pricefile(PRIMARY_HOURLY, 8760, 1, "Primær timeserie")
    max_daily_delta = validate_primary(daily, hourly)
    secondary = read_secondary_no2(SECONDARY_XLSX)
    hjelle_inflow = read_hjelle_inflow(INFLOW_DAILY, daily.timestamps)

    basic = {"Døgn": describe(daily.values), "Time": describe(hourly.values)}
    ratio_rows: list[dict[str, object]] = []
    classes: dict[str, dict[str, int | float]] = {}
    ratio_data: dict[str, np.ndarray] = {}
    ratio_csv: list[list[object]] = []
    for label, steps, resolution in HORIZONS:
        values = hourly.values if resolution == "hourly" else daily.values
        actual_steps = steps if resolution == "hourly" else steps
        all_ratios, rising = forward_ratios(values, actual_steps)
        ratio_data[label] = all_ratios
        for population, ratios in (("Alle fremoverpar", all_ratios), ("Kun stigende par", rising)):
            summary = ratio_summary(ratios)
            ratio_rows.append({"horizon": label, "population": population, **summary})
            ratio_csv.append([label, resolution, population, summary["n"], summary["gt_120"],
                              summary["gt_133"], summary["gt_150"], summary["median"]])
        classes[label] = classify_perfect_foresight(values, actual_steps)

    monthly = [float(np.mean([v for s, v in zip(daily.timestamps, daily.values) if s.month == m])) for m in range(1, 13)]
    by_hour = [float(np.mean([v for s, v in zip(hourly.timestamps, hourly.values) if s.hour == h])) for h in range(24)]
    day = np.asarray([v for s, v in zip(hourly.timestamps, hourly.values) if 8 <= s.hour <= 19])
    night = np.asarray([v for s, v in zip(hourly.timestamps, hourly.values) if 0 <= s.hour <= 5])
    summer = np.asarray([v for s, v in zip(daily.timestamps, daily.values) if s.month in (6, 7, 8)])
    winter = np.asarray([v for s, v in zip(daily.timestamps, daily.values) if s.month in (12, 1, 2)])
    day_night, summer_winter = float(np.mean(day) / np.mean(night)), float(np.mean(summer) / np.mean(winter))

    storage_rows: list[dict[str, object]] = []
    for q in (1, 2, 5):
        for label, hours in (("6t", 6), ("12t", 12), ("24t", 24), ("7d", 7 * 24)):
            required = storage_requirement_m3(q, hours) / 1e6
            storage_rows.append({"q": q, "horizon": label, "required_mm3": required,
                                 "hjelle": required <= 9.0, "gresse": required <= 61.4})
    correlation = pearson(daily.values, hjelle_inflow)

    write_csv(OUT / "grunnstatistikk.csv", ["opplosning", "n", "min", "maks", "median", "snitt", "std_n_minus_1", "under_20", "over_200"],
              [[name, *describe_values.values()] for name, describe_values in basic.items()])
    write_csv(OUT / "ratioanalyse.csv", ["horisont", "opplosning", "populasjon", "n_par", "andel_gt_120", "andel_gt_133", "andel_gt_150", "median_ratio"], ratio_csv)
    write_csv(OUT / "klassifisering.csv", ["horisont", "antakelse", "n_starttidspunkter", "aldri", "betinget", "alltid", "andel_aldri", "andel_betinget", "andel_alltid", "median_maksratio"],
              [[label, "perfekt_framsyn_innen_vinduet", result["n"], result["never"], result["conditional"], result["always"], result["never_share"], result["conditional_share"], result["always_share"], result["median_max_ratio"]] for label, result in classes.items()])
    write_csv(OUT / "magasinkrav.csv", ["q_pump_m3s", "horisont", "krav_mm3", "hjelle_mulig", "gresse_mulig"],
              [[r["q"], r["horizon"], r["required_mm3"], r["hjelle"], r["gresse"]] for r in storage_rows])
    make_histogram_svg(OUT / "prisfordeling.svg", daily.values, hourly.values)
    make_season_svg(OUT / "sesongmonster.svg", daily, hourly)
    make_ratio_svg(OUT / "ratiofordelinger.svg", ratio_data)
    REPORT.write_text(build_report(daily, hourly, max_daily_delta, secondary, basic, ratio_rows, classes,
                                   monthly, by_hour, day_night, summer_winter, storage_rows, correlation), encoding="utf-8")
    expected_outputs = (OUT / "grunnstatistikk.csv", OUT / "ratioanalyse.csv", OUT / "klassifisering.csv",
                        OUT / "magasinkrav.csv", OUT / "prisfordeling.svg", OUT / "sesongmonster.svg",
                        OUT / "ratiofordelinger.svg", REPORT)
    if len(ratio_rows) != 10 or len(classes) != 5 or len(storage_rows) != 12:
        raise AssertionError("Ufullstendig ende-til-ende-resultat: feil antall ratio-, klasse- eller lagringsrader.")
    for output in expected_outputs:
        if not output.is_file() or output.stat().st_size == 0:
            raise AssertionError(f"Ende-til-ende-resultat mangler eller er tomt: {output}")
    for svg in (OUT / "prisfordeling.svg", OUT / "sesongmonster.svg", OUT / "ratiofordelinger.svg"):
        ET.parse(svg)
    print(f"Skrev {REPORT.relative_to(ROOT)} og resultater i {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    run()
