"""Read saved evidence only. Writes review artifacts exclusively beside this script."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
DEST = Path(__file__).resolve().parent
PARTS = ("success_55", "non_success_part1_69", "non_success_part2_68")
csv.field_size_limit(100_000_000)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def references():
    # Read the OOXML values with stdlib; do not modify or recalculate the workbook.
    path = ROOT.parent / "improvement2/dataset/verification_results_v2_sql_correct_442.xlsx"
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        shared = ["".join(t.itertext()) for t in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", ns)] if "xl/sharedStrings.xml" in archive.namelist() else []
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.findall("s:sheetData/s:row", ns):
            values = {}
            for cell in row.findall("s:c", ns):
                value = cell.find("s:v", ns)
                inline = cell.find("s:is", ns)
                text = value.text if value is not None else "".join(inline.itertext()) if inline is not None else ""
                values["".join(c for c in cell.attrib["r"] if c.isalpha())] = shared[int(text)] if cell.get("t") == "s" else text
            rows.append(values)
    return {r["A"]: {name: r.get(col, "") for col, name in rows[0].items()} for r in rows[1:]}


def main():
    refs = references()
    evidence, summary, identities = [], {}, {}
    for part in PARTS:
        versions = {}
        for version in (5, 6):
            prefix = f"v{version}_multistep_contract_{part}"
            graded = read_csv(ROOT / "pipelien_output" / f"graded_{prefix}_terra.csv")
            # Select the actual report, excluding abandoned manifest-only attempts.
            reports = sorted(p for p in (ROOT / "pipelien_output").glob(prefix + "*.csv") if not p.stem.endswith("_debug"))
            assert len(reports) == 1, reports
            report = reports[0]
            debug = {r["Sample Row ID"]: r for r in read_csv(report.with_name(report.stem + "_debug.csv"))}
            manifest = json.loads(Path(str(report) + ".manifest.json").read_text())
            identities[prefix] = {
                "report": report.name, "run_identity": manifest["run_identity"],
                "source_differences": [name for name, saved in manifest["source_files"].items()
                                       if digest(ROOT / f"run_pipeline_v{version}" / name) != saved],
            }
            summary[prefix] = {"all": dict(Counter(r["Grade Status"] for r in graded)),
                               "comparative_family": dict(Counter(r["Grade Status"] for r in graded if ":MC-" in r["Sample Row ID"])),
                               "failure_stages": dict(Counter(r["Failure Stage"] for r in debug.values() if r["Failure Stage"]))}
            versions[version] = {r["Sample Row ID"]: (r, debug[r["Sample Row ID"]]) for r in graded}
        assert versions[5].keys() == versions[6].keys()
        for key in versions[5]:
            reference = refs[key]
            row = {"id": key, "part": part, "reference": reference}
            for version in (5, 6):
                grade, debug = versions[version][key]
                assert grade["Question"] == reference["question"]
                assert grade["Ground Truth"] == reference["ground_truth_answer"]
                spec = json.loads(debug["Debug Final Spec"] or "{}")
                row[f"v{version}"] = {
                    "grade": grade["Grade Status"], "grade_reason": grade["Grade Reason"],
                    "answer": grade["New Pipeline Result"], "status": grade["New Status"],
                    "requirements": json.loads(debug["Debug Answer Requirements"] or "{}"),
                    "final_plan": {k: v for k, v in spec.items() if k in {"final_steps", "projection", "semantic_contract", "contract_errors"}},
                }
            evidence.append(row)
    (DEST / "v5_v6_evidence.json").write_text(json.dumps({"summary": summary, "identities": identities, "questions": evidence}, indent=2, ensure_ascii=False), encoding="utf-8")
    fields = ["id", "part", "question", "v5_grade", "v6_grade", "v5_reason", "v6_reason", "reference_sql"]
    with (DEST / "v5_v6_transitions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for r in evidence:
            writer.writerow({"id": r["id"], "part": r["part"], "question": r["reference"]["question"],
                             **{f"v{v}_grade": r[f"v{v}"]["grade"] for v in (5, 6)},
                             **{f"v{v}_reason": r[f"v{v}"]["grade_reason"] for v in (5, 6)},
                             "reference_sql": r["reference"]["sql_query"]})
    print(json.dumps({"questions": len(evidence), "summary": summary, "identities": identities}, indent=2))


if __name__ == "__main__":
    main()
