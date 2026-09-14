"""Create rerunnable input manifests from completed V1 pipeline reports."""

from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "pipelien_output"
SOURCE_REPORTS = [
    OUTPUT_DIR / "v1_queries_1_to_100.csv",
    OUTPUT_DIR / "v1_queries_351_to_442.csv",
]
SUCCESS_OUTPUT = OUTPUT_DIR / "v1_pipeline_success_input.csv"
NON_SUCCESS_OUTPUT = OUTPUT_DIR / "v1_pipeline_non_success_input.csv"


def main() -> None:
    reports = []
    for source in SOURCE_REPORTS:
        if not source.exists():
            print(f"[WARN] Missing V1 report: {source}")
            continue
        report = pd.read_csv(source, dtype=str, keep_default_na=False)
        report["V1 Report Source"] = str(source.resolve())
        report["V1 Pipeline Status"] = report.get("New Status", "")
        reports.append(report)
    if not reports:
        raise FileNotFoundError("No V1 report CSVs were found.")

    combined = pd.concat(reports, ignore_index=True)
    # The manifests are inputs, not copies of the huge diagnostic output.  They retain
    # benchmark context plus source/status provenance required to audit a rerun.
    columns = [
        "Sample Row ID", "Question", "Ground Truth", "Difficulty", "Category",
        "Query Type", "Source CSV", "Status", "V1 Pipeline Status", "V1 Report Source",
    ]
    for column in columns:
        if column not in combined.columns:
            combined[column] = ""
    manifest = combined[columns].copy()
    manifest["Status"] = manifest["V1 Pipeline Status"]
    manifest = manifest.drop_duplicates(subset=["V1 Report Source", "Sample Row ID"], keep="first")

    success_mask = manifest["V1 Pipeline Status"].astype(str).str.strip().str.upper().eq("PIPELINE_SUCCESS")
    success = manifest[success_mask].copy()
    non_success = manifest[~success_mask].copy()
    success.to_csv(SUCCESS_OUTPUT, index=False, encoding="utf-8")
    non_success.to_csv(NON_SUCCESS_OUTPUT, index=False, encoding="utf-8")
    print(f"[SUCCESS] {SUCCESS_OUTPUT}: {len(success)} rows")
    print(f"[NON_SUCCESS] {NON_SUCCESS_OUTPUT}: {len(non_success)} rows")


if __name__ == "__main__":
    main()
