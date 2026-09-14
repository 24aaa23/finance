import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from openai import OpenAI


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPT_DIR / "verification_results_v2_sql_correct_442.xlsx"
DEFAULT_OUTPUT = SCRIPT_DIR / "verification_results_v2_sql_correct_442_arithmetic_categories.csv"

OUTPUT_COLUMNS = [
    "arithmetic_required",
    "arithmetic_category",
    "arithmetic_operations",
    "arithmetic_reason",
    "classification_confidence",
]

VALID_CATEGORIES = {
    "none",
    "direct_numeric_lookup",
    "aggregate",
    "difference_or_change",
    "ratio_or_percentage",
    "ranking_or_extreme",
    "date_arithmetic",
    "multi_step_formula",
    "other_arithmetic",
}


def load_local_env_file() -> None:
    env_candidates = [
        SCRIPT_DIR / ".env",
        SCRIPT_DIR.parent / ".env",
        SCRIPT_DIR.parent.parent / ".env",
        SCRIPT_DIR.parent.parent.parent / ".env",
    ]
    env_file = next((path for path in env_candidates if path.exists()), None)
    if not env_file:
        return

    with env_file.open(encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


load_local_env_file()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classify benchmark questions as requiring arithmetic or not using the OpenAI GPT API. "
            "The output CSV preserves the source rows and appends arithmetic/category metadata."
        )
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input .xlsx/.csv file.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path.")
    parser.add_argument("--sheet", default=None, help="Excel sheet name. Defaults to the first sheet.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model name.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max rows to process.")
    parser.add_argument("--resume", action="store_true", help="Reuse already-classified rows from the output CSV.")
    parser.add_argument("--only-missing", action="store_true", help="With --resume, classify only rows missing YES/NO in the output CSV.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between API calls.")
    return parser.parse_args()


def build_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY before running this script.")

    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def read_dataset(path: Path, sheet: str | None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet or 0)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported input type: {path.suffix}. Use .xlsx, .xls, or .csv.")


def load_resume_map(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    existing = pd.read_csv(path)
    if "global_question_id" not in existing.columns:
        return {}

    completed: dict[str, dict[str, Any]] = {}
    for _, row in existing.iterrows():
        qid = str(row.get("global_question_id", "")).strip()
        required = str(row.get("arithmetic_required", "")).strip().upper()
        category = str(row.get("arithmetic_category", "")).strip()
        if qid and required in {"YES", "NO"} and category and category.lower() != "nan":
            completed[qid] = {col: row.get(col, "") for col in OUTPUT_COLUMNS}
    return completed


def load_existing_output(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)


def clean_text(value: Any, max_chars: int = 3000) -> str:
    text = "" if pd.isna(value) else str(value)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 24] + "\n...[truncated]..."


def parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise ValueError(f"GPT response was not valid JSON: {raw[:500]}")


def normalize_label(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return "YES"
    if text in {"false", "no", "n", "0"}:
        return "NO"
    return "UNKNOWN"


def normalize_category(value: Any, required: str) -> str:
    category = str(value or "").strip().lower().replace(" ", "_")
    if category not in VALID_CATEGORIES:
        return "other_arithmetic" if required == "YES" else "none"
    if required == "NO":
        return "none"
    if category == "none":
        return "other_arithmetic"
    return category


def classify_row(client: OpenAI, model: str, row: pd.Series) -> dict[str, Any]:
    question = clean_text(row.get("question", ""))
    existing_category = clean_text(row.get("category", ""))
    query_type = clean_text(row.get("query_type", ""))
    difficulty = clean_text(row.get("difficulty", ""))
    sql_query = clean_text(row.get("sql_query", ""), max_chars=6000)
    ground_truth = clean_text(row.get("ground_truth_answer", ""), max_chars=4000)

    prompt = f"""
You are classifying finance benchmark questions.

Decide whether answering the question requires an arithmetic operation.

Use these rules:
- Mark arithmetic_required YES when the answer requires numeric computation such as sum, count, average, min/max aggregate, net value, difference, change, ratio, percentage, formula, date arithmetic, or comparing computed values.
- Mark arithmetic_required NO when the question only asks to retrieve stored fields, filter records, list entities, join tables, or return already-stored numeric values without computing a new value.
- Ranking by an already-stored value is ranking_or_extreme. Mark YES only if the question needs an aggregate/computed ranking, otherwise NO with category none.
- If SQL uses COUNT, SUM, AVG, MIN, MAX, arithmetic expressions, GROUP BY with numeric aggregation, date-difference functions, division, subtraction, multiplication, or addition for the answer, that is usually YES.

Allowed arithmetic_category values:
none, direct_numeric_lookup, aggregate, difference_or_change, ratio_or_percentage,
ranking_or_extreme, date_arithmetic, multi_step_formula, other_arithmetic

Return only JSON:
{{
  "arithmetic_required": "YES" or "NO",
  "arithmetic_category": "one allowed value",
  "arithmetic_operations": ["short operation names"],
  "arithmetic_reason": "one concise sentence",
  "classification_confidence": 0.0
}}

Question: {question}
Existing dataset category: {existing_category}
Difficulty: {difficulty}
Query type: {query_type}
SQL query: {sql_query}
Ground truth answer: {ground_truth}
""".strip()

    request_kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You return compact, valid JSON and do not include markdown.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    if "terra" not in model.lower() and not model.lower().startswith("gpt-5"):
        request_kwargs["temperature"] = 0

    response = client.chat.completions.create(**request_kwargs)

    parsed = parse_json_object(response.choices[0].message.content or "")
    required = normalize_label(parsed.get("arithmetic_required"))
    category = normalize_category(parsed.get("arithmetic_category"), required)
    operations = parsed.get("arithmetic_operations", [])
    if isinstance(operations, list):
        operations_text = "; ".join(str(item).strip() for item in operations if str(item).strip())
    else:
        operations_text = str(operations or "").strip()

    try:
        confidence = float(parsed.get("classification_confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(max(confidence, 0.0), 1.0)

    return {
        "arithmetic_required": required,
        "arithmetic_category": category,
        "arithmetic_operations": operations_text,
        "arithmetic_reason": str(parsed.get("arithmetic_reason", "")).strip(),
        "classification_confidence": confidence,
    }


def write_progress(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig", errors="replace")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    df = read_dataset(input_path, args.sheet)
    if args.limit is not None:
        df = df.head(args.limit).copy()
    else:
        df = df.copy()

    for column in OUTPUT_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    existing_output = load_existing_output(output_path) if args.resume else None
    resume_map = load_resume_map(output_path) if args.resume else {}
    if existing_output is not None:
        merge_columns = ["global_question_id", *OUTPUT_COLUMNS]
        if all(column in existing_output.columns for column in merge_columns):
            existing_values = existing_output[merge_columns].copy()
            existing_values = existing_values.rename(columns={column: f"{column}__existing" for column in OUTPUT_COLUMNS})
            df = df.merge(existing_values, on="global_question_id", how="left")
            for column in OUTPUT_COLUMNS:
                existing_column = f"{column}__existing"
                existing_series = df[existing_column]
                df[column] = existing_series.where(existing_series.notna(), df[column])
                df = df.drop(columns=[existing_column])
    client = build_client()

    for idx, row in df.iterrows():
        qid = str(row.get("global_question_id", "")).strip()
        current_required = str(row.get("arithmetic_required", "")).strip().upper()
        if args.only_missing and current_required in {"YES", "NO"}:
            continue
        if qid in resume_map:
            for column, value in resume_map[qid].items():
                df.at[idx, column] = value
            continue

        try:
            result = classify_row(client, args.model, row)
        except Exception as exc:
            result = {
                "arithmetic_required": "UNKNOWN",
                "arithmetic_category": "none",
                "arithmetic_operations": "",
                "arithmetic_reason": f"CLASSIFICATION_ERROR: {type(exc).__name__}: {exc}",
                "classification_confidence": 0.0,
            }

        for column, value in result.items():
            df.at[idx, column] = value

        print(
            f"[{idx + 1}/{len(df)}] {row.get('question_id', qid)} "
            f"{result['arithmetic_required']} {result['arithmetic_category']}",
            flush=True,
        )
        write_progress(df, output_path)

        if args.sleep:
            time.sleep(args.sleep)

    write_progress(df, output_path)
    print(f"Wrote classified dataset: {output_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
