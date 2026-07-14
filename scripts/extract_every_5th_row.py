#!/usr/bin/env python3
"""Create a workbook with rows 1, 6, 11, 16, ... from FINAL.xlsx.

This script uses only Python's standard library, so it does not require
pandas/openpyxl to be installed.
"""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


DEFAULT_INPUT = Path("/DATAAMAN/financial/FINAL.xlsx")
DEFAULT_OUTPUT = Path("/DATAAMAN/financial/final1.xlsx")

CELL_REF_RE = re.compile(r"^([A-Z]+)([0-9]+)$")


def namespace_for(tag: str) -> str:
    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


def qname(namespace: str, tag: str) -> str:
    if namespace:
        return f"{{{namespace}}}{tag}"
    return tag


def column_index(column: str) -> int:
    value = 0
    for char in column:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


def column_name(index: int) -> str:
    chars: list[str] = []
    while index:
        index, remainder = divmod(index - 1, 26)
        chars.append(chr(ord("A") + remainder))
    return "".join(reversed(chars)) or "A"


def split_cell_ref(cell_ref: str) -> tuple[str, int] | None:
    match = CELL_REF_RE.match(cell_ref)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def rewrite_sheet(xml_bytes: bytes, start_row: int, step: int) -> tuple[bytes, int]:
    root = ET.fromstring(xml_bytes)
    namespace = namespace_for(root.tag)
    if namespace:
        ET.register_namespace("", namespace)

    sheet_data = root.find(qname(namespace, "sheetData"))
    if sheet_data is None:
        return xml_bytes, 0

    rows = list(sheet_data.findall(qname(namespace, "row")))
    selected_rows = []
    for fallback_index, row in enumerate(rows, start=1):
        row_number = int(row.get("r", fallback_index))
        if row_number >= start_row and (row_number - start_row) % step == 0:
            selected_rows.append(row)

    for row in rows:
        sheet_data.remove(row)

    max_column = 1
    for new_row_number, row in enumerate(selected_rows, start=1):
        row.set("r", str(new_row_number))
        row.attrib.pop("spans", None)

        for cell in row.findall(qname(namespace, "c")):
            ref = cell.get("r")
            if not ref:
                continue
            split_ref = split_cell_ref(ref)
            if split_ref is None:
                continue
            column, _old_row_number = split_ref
            max_column = max(max_column, column_index(column))
            cell.set("r", f"{column}{new_row_number}")

        sheet_data.append(row)

    dimension = root.find(qname(namespace, "dimension"))
    if dimension is not None:
        if selected_rows:
            dimension.set("ref", f"A1:{column_name(max_column)}{len(selected_rows)}")
        else:
            dimension.set("ref", "A1")

    auto_filter = root.find(qname(namespace, "autoFilter"))
    if auto_filter is not None and selected_rows:
        auto_filter.set("ref", f"A1:{column_name(max_column)}{len(selected_rows)}")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True), len(selected_rows)


def extract_rows(input_path: Path, output_path: Path, start_row: int, step: int) -> list[tuple[str, int]]:
    if start_row < 1:
        raise ValueError("--start-row must be 1 or greater")
    if step < 1:
        raise ValueError("--step must be 1 or greater")
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_counts: list[tuple[str, int]] = []

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx", dir=output_path.parent) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(input_path, "r") as zin, zipfile.ZipFile(
            tmp_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith("xl/worksheets/sheet") and item.filename.endswith(".xml"):
                    data, row_count = rewrite_sheet(data, start_row=start_row, step=step)
                    sheet_counts.append((item.filename, row_count))
                zout.writestr(item, data)

        shutil.move(tmp_path, output_path)
        shutil.copymode(input_path, output_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return sheet_counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract rows 1, 6, 11, 16, ... from an XLSX workbook."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help=f"Input XLSX file. Default: {DEFAULT_INPUT}")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output XLSX file. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument("--start-row", type=int, default=1, help="First row to keep. Default: 1")
    parser.add_argument("--step", type=int, default=5, help="Keep every Nth row. Default: 5")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sheet_counts = extract_rows(args.input, args.output, args.start_row, args.step)
    for sheet_name, row_count in sheet_counts:
        print(f"{sheet_name}: wrote {row_count} rows")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
