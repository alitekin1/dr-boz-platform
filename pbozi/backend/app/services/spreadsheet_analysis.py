from __future__ import annotations

import csv
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import numpy as np


SPREADSHEET_EXTENSIONS = {".csv", ".xlsx", ".xlsm"}
EARTHQUAKE_KEYWORDS = (
    "earthquake",
    "زلزله",
    "pga",
    "pgv",
    "pgd",
    "sma",
    "seismosignal",
    "شتاب",
    "سرعت",
    "جابجایی",
    "جابه",
)
PERSIAN_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass(frozen=True)
class SpreadsheetFile:
    filename: str
    path: str


@dataclass(frozen=True)
class SpreadsheetPreprocessResult:
    title: str
    prompt_context: str
    source_files: list[str]
    raw_input_chars: int
    compact_chars: int


def build_spreadsheet_preprocessing_context(
    files: list[SpreadsheetFile],
    user_text: str,
) -> SpreadsheetPreprocessResult | None:
    usable_files = [f for f in files if Path(f.path).suffix.lower() in SPREADSHEET_EXTENSIONS and os.path.isfile(f.path)]
    if not usable_files:
        return None

    normalized_text = _normalize_digits(user_text or "").lower()
    if not any(keyword in normalized_text for keyword in EARTHQUAKE_KEYWORDS):
        return None

    records = _selected_csv_records(usable_files, normalized_text)
    time_histories = [_analyze_time_history_file(file) for file in usable_files if Path(file.path).suffix.lower() in {".xlsx", ".xlsm"}]
    time_histories = [item for item in time_histories if item]
    if not records and not time_histories:
        return None

    raw_chars = sum(_safe_file_size(file.path) for file in usable_files)
    lines = [
        "The following data was computed deterministically from the uploaded spreadsheets before calling the model.",
        "Do not ask the model to recalculate from raw tables. Use these compact computed results for the final analysis/report.",
        "",
        "Source files:",
    ]
    for file in usable_files:
        lines.append(f"- {file.filename} ({_safe_file_size(file.path)} bytes)")

    if records:
        lines.extend(["", "Selected rows from the search results CSV:"])
        for record in records:
            lines.append(f"- Row {record['row_number']}: {record['summary']}")

    if time_histories:
        lines.extend(["", "Computed time-history metrics:"])
        for item in time_histories:
            lines.extend(_render_time_history(item))

        ranked_pga = sorted(time_histories, key=lambda item: item["pga_abs_g"], reverse=True)
        ranked_sma3 = sorted(time_histories, key=lambda item: item["sma_third_peak_g"], reverse=True)
        lines.extend(["", "Rankings:"])
        lines.append("PGA descending: " + ", ".join(f"{item['filename']} ({item['pga_abs_g']:.6g} g)" for item in ranked_pga))
        lines.append("SMA third-peak descending: " + ", ".join(f"{item['filename']} ({item['sma_third_peak_g']:.6g} g)" for item in ranked_sma3))

    lines.extend(
        [
            "",
            "Reporting instructions:",
            "- Write the user-facing answer in Persian unless the user asks otherwise.",
            "- Keep numerical calculations based on the computed values above.",
            "- If a PDF is requested, generate the report from this compact result summary, not from raw spreadsheet rows.",
        ]
    )
    prompt_context = "\n".join(lines)
    return SpreadsheetPreprocessResult(
        title="spreadsheet_precomputed_earthquake_analysis",
        prompt_context=prompt_context,
        source_files=[file.filename for file in usable_files],
        raw_input_chars=raw_chars,
        compact_chars=len(prompt_context),
    )


def _normalize_digits(text: str) -> str:
    return text.translate(PERSIAN_DIGIT_MAP)


def _safe_file_size(path: str) -> int:
    try:
        return int(os.path.getsize(path))
    except OSError:
        return 0


def _selected_csv_records(files: list[SpreadsheetFile], user_text: str) -> list[dict[str, str | int]]:
    row_numbers = _extract_requested_rows(user_text)
    csv_files = [file for file in files if Path(file.path).suffix.lower() == ".csv"]
    if not row_numbers and csv_files:
        row_numbers = [59, 69, 112]

    output: list[dict[str, str | int]] = []
    for file in csv_files:
        rows = _read_csv_rows(file.path)
        if not rows:
            continue
        for row_number in row_numbers:
            index = row_number - 1
            if index < 0 or index >= len(rows):
                continue
            cells = [cell.strip() for cell in rows[index] if cell and cell.strip()]
            if not cells:
                continue
            output.append(
                {
                    "file": file.filename,
                    "row_number": row_number,
                    "summary": " | ".join(cells[:18])[:1200],
                }
            )
    return output


def _extract_requested_rows(user_text: str) -> list[int]:
    row_numbers: list[int] = []
    normalized = _normalize_digits(user_text)
    for match in re.finditer(r"(?:row|rows|سطر|ردیف)\D{0,20}((?:\d+\D{0,8}){1,8})", normalized, flags=re.IGNORECASE):
        for value in re.findall(r"\d+", match.group(1)):
            number = int(value)
            if number not in row_numbers:
                row_numbers.append(number)
    return row_numbers[:12]


def _read_csv_rows(path: str) -> list[list[str]]:
    try:
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as file_obj:
            return list(csv.reader(file_obj))
    except OSError:
        return []


def _read_xlsx_rows(path: str) -> list[list[str]]:
    try:
        with ZipFile(path) as archive:
            shared_strings = _read_shared_strings(archive)
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
            sheet = workbook.find("main:sheets/main:sheet", XLSX_NS)
            if sheet is None:
                return []
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = rel_map.get(rel_id or "")
            if not target:
                return []
            sheet_path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
            root = ET.fromstring(archive.read(sheet_path))
            return [_xlsx_row_values(row, shared_strings) for row in root.findall("main:sheetData/main:row", XLSX_NS)]
    except Exception:
        return []


def _read_shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(text_node.text or "" for text_node in item.findall(".//main:t", XLSX_NS))
        for item in root.findall("main:si", XLSX_NS)
    ]


def _xlsx_row_values(row: ET.Element, shared_strings: list[str]) -> list[str]:
    values: list[str] = []
    for cell in row.findall("main:c", XLSX_NS):
        index = _xlsx_column_index(cell.attrib.get("r", "A1"))
        while len(values) < index:
            values.append("")
        values.append(_xlsx_cell_value(cell, shared_strings))
    return values


def _xlsx_column_index(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha())
    value = 0
    for ch in letters.upper():
        value = value * 26 + ord(ch) - 64
    return max(0, value - 1)


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text_node.text or "" for text_node in cell.findall(".//main:t", XLSX_NS))
    value_node = cell.find("main:v", XLSX_NS)
    if value_node is None:
        return ""
    value = value_node.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except Exception:
            return value
    return value


def _analyze_time_history_file(file: SpreadsheetFile) -> dict | None:
    rows = _read_xlsx_rows(file.path)
    if not rows:
        return None
    header_index = _find_header_row(rows)
    if header_index is None:
        return None
    headers = [str(value).strip().lower() for value in rows[header_index]]
    series = {
        "acceleration": _extract_series(rows[header_index + 1 :], headers, "acceleration"),
        "velocity": _extract_series(rows[header_index + 1 :], headers, "velocity"),
        "displacement": _extract_series(rows[header_index + 1 :], headers, "displacement"),
    }
    if series["acceleration"] is None:
        return None

    accel_t, accel_y = series["acceleration"]
    result = {
        "filename": file.filename,
        "point_count": len(accel_y),
        "pga_abs_g": _max_abs_value(accel_t, accel_y)[0],
        "pga_time_s": _max_abs_value(accel_t, accel_y)[1],
        "bracketed_duration_0_05g_s": _bracketed_duration(accel_t, accel_y, threshold=0.05),
        "significant_duration_5_95_s": _significant_duration(accel_t, accel_y),
        "dominant_period_s": _dominant_period(accel_t, accel_y),
        "sma_third_peak_g": _nth_peak(accel_y, 3),
        "sma_fifth_peak_g": _nth_peak(accel_y, 5),
    }
    if series["velocity"] is not None:
        vel_t, vel_y = series["velocity"]
        result["pgv_abs_cm_s"], result["pgv_time_s"] = _max_abs_value(vel_t, vel_y)
    else:
        result["pgv_abs_cm_s"], result["pgv_time_s"] = 0.0, 0.0
    if series["displacement"] is not None:
        disp_t, disp_y = series["displacement"]
        result["pgd_abs_cm"], result["pgd_time_s"] = _max_abs_value(disp_t, disp_y)
    else:
        result["pgd_abs_cm"], result["pgd_time_s"] = 0.0, 0.0
    return result


def _find_header_row(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows[:20]):
        joined = " ".join(str(value).lower() for value in row)
        if "time" in joined and "acceleration" in joined:
            return index
    return None


def _extract_series(rows: list[list[str]], headers: list[str], value_name: str) -> tuple[np.ndarray, np.ndarray] | None:
    value_index = next((idx for idx, header in enumerate(headers) if value_name in header), None)
    if value_index is None:
        return None
    time_index = _nearest_time_header(headers, value_index)
    if time_index is None:
        return None

    times: list[float] = []
    values: list[float] = []
    for row in rows:
        if value_index >= len(row) or time_index >= len(row):
            continue
        time_value = _to_float(row[time_index])
        data_value = _to_float(row[value_index])
        if time_value is None or data_value is None:
            continue
        times.append(time_value)
        values.append(data_value)
    if not times:
        return None
    return np.asarray(times, dtype=float), np.asarray(values, dtype=float)


def _nearest_time_header(headers: list[str], value_index: int) -> int | None:
    for index in range(value_index - 1, -1, -1):
        if "time" in headers[index]:
            return index
    for index, header in enumerate(headers):
        if "time" in header:
            return index
    return None


def _to_float(value: str) -> float | None:
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _max_abs_value(times: np.ndarray, values: np.ndarray) -> tuple[float, float]:
    if values.size == 0:
        return 0.0, 0.0
    index = int(np.argmax(np.abs(values)))
    return float(abs(values[index])), float(times[index])


def _bracketed_duration(times: np.ndarray, accel_g: np.ndarray, threshold: float) -> float:
    indices = np.flatnonzero(np.abs(accel_g) >= threshold)
    if indices.size < 2:
        return 0.0
    return float(times[int(indices[-1])] - times[int(indices[0])])


def _significant_duration(times: np.ndarray, accel_g: np.ndarray) -> float:
    if times.size < 2 or accel_g.size < 2:
        return 0.0
    dt = np.diff(times)
    dt = np.where(dt > 0, dt, np.nan)
    increments = ((accel_g[:-1] ** 2 + accel_g[1:] ** 2) / 2.0) * dt
    increments = np.nan_to_num(increments, nan=0.0)
    cumulative = np.concatenate([[0.0], np.cumsum(increments)])
    total = float(cumulative[-1])
    if total <= 0:
        return 0.0
    t5 = float(np.interp(0.05 * total, cumulative, times))
    t95 = float(np.interp(0.95 * total, cumulative, times))
    return max(0.0, t95 - t5)


def _dominant_period(times: np.ndarray, accel_g: np.ndarray) -> float:
    if times.size < 4 or accel_g.size < 4:
        return 0.0
    diffs = np.diff(times)
    diffs = diffs[diffs > 0]
    if diffs.size == 0:
        return 0.0
    dt = float(np.median(diffs))
    if dt <= 0:
        return 0.0
    signal = accel_g - np.mean(accel_g)
    spectrum = np.abs(np.fft.rfft(signal))
    freqs = np.fft.rfftfreq(signal.size, d=dt)
    if spectrum.size <= 1:
        return 0.0
    index = int(np.argmax(spectrum[1:]) + 1)
    freq = float(freqs[index])
    if freq <= 0:
        return 0.0
    return 1.0 / freq


def _nth_peak(values: np.ndarray, n: int) -> float:
    if values.size == 0:
        return 0.0
    abs_values = np.abs(values)
    peak_indices: list[int] = []
    for index in range(1, values.size - 1):
        if abs_values[index] >= abs_values[index - 1] and abs_values[index] >= abs_values[index + 1]:
            peak_indices.append(index)
    peaks = np.sort(abs_values[peak_indices])[::-1] if peak_indices else np.sort(abs_values)[::-1]
    if peaks.size == 0:
        return 0.0
    return float(peaks[min(n - 1, peaks.size - 1)])


def _render_time_history(item: dict) -> list[str]:
    return [
        f"- {item['filename']}:",
        f"  PGA = {item['pga_abs_g']:.6g} g at t={item['pga_time_s']:.6g} s",
        f"  PGV = {item['pgv_abs_cm_s']:.6g} cm/s at t={item['pgv_time_s']:.6g} s",
        f"  PGD = {item['pgd_abs_cm']:.6g} cm at t={item['pgd_time_s']:.6g} s",
        f"  SMA third peak = {item['sma_third_peak_g']:.6g} g; fifth peak = {item['sma_fifth_peak_g']:.6g} g",
        f"  Bracketed duration (|a| >= 0.05g) = {item['bracketed_duration_0_05g_s']:.6g} s",
        f"  Significant duration 5-95% Arias proxy = {item['significant_duration_5_95_s']:.6g} s",
        f"  Dominant period from FFT peak = {item['dominant_period_s']:.6g} s",
    ]
