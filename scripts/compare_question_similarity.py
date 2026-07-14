#!/usr/bin/env python3
"""Compare questions in final1.xlsx with two test-set workbooks.

The script intentionally uses only Python's standard library so it can run in
this workspace without pandas/openpyxl.
"""

from __future__ import annotations

import argparse
import csv
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree as ET


DEFAULT_BASE = Path("/DATAAMAN/financial/final1.xlsx")
DEFAULT_TARGETS = [
    Path("/DATAAMAN/financial/combined_questions_results (2).xlsx"),
    Path("/DATAAMAN/financial/iitk_testSet (2).xlsx"),
]
DEFAULT_OUTPUT_DIR = Path("/DATAAMAN/financial/question_similarity_reports")

CELL_RE = re.compile(r"^([A-Z]+)([0-9]+)$")
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "all",
    "alongside",
    "and",
    "are",
    "as",
    "available",
    "by",
    "calculate",
    "complete",
    "data",
    "dataset",
    "each",
    "for",
    "from",
    "given",
    "how",
    "in",
    "into",
    "is",
    "many",
    "of",
    "on",
    "show",
    "the",
    "their",
    "to",
    "what",
    "where",
    "which",
    "with",
}

SYNONYMS = {
    "avg": "average",
    "mean": "average",
    "number": "count",
    "counts": "count",
    "portfolios": "portfolio",
    "investors": "investor",
    "goals": "goal",
    "statuses": "status",
    "categories": "category",
    "categorised": "category",
    "categorized": "category",
    "scores": "score",
    "values": "value",
}


@dataclass
class Question:
    row_number: int
    text: str
    qtype: str


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
    return value - 1


def cell_position(cell_ref: str) -> tuple[int, int] | None:
    match = CELL_RE.match(cell_ref)
    if not match:
        return None
    return int(match.group(2)) - 1, column_index(match.group(1))


def read_shared_strings(zfile: zipfile.ZipFile) -> list[str]:
    try:
        xml_bytes = zfile.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ET.fromstring(xml_bytes)
    namespace = namespace_for(root.tag)
    strings: list[str] = []
    for item in root.findall(qname(namespace, "si")):
        parts = [node.text or "" for node in item.iter(qname(namespace, "t"))]
        strings.append("".join(parts))
    return strings


def read_first_sheet_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as zfile:
        shared_strings = read_shared_strings(zfile)
        sheet_xml = zfile.read("xl/worksheets/sheet1.xml")

    root = ET.fromstring(sheet_xml)
    namespace = namespace_for(root.tag)
    sheet_data = root.find(qname(namespace, "sheetData"))
    if sheet_data is None:
        return []

    values: dict[tuple[int, int], str] = {}
    max_row = -1
    max_col = -1

    for row in sheet_data.findall(qname(namespace, "row")):
        for cell in row.findall(qname(namespace, "c")):
            ref = cell.get("r")
            if not ref:
                continue
            position = cell_position(ref)
            if position is None:
                continue

            row_index, col_index = position
            max_row = max(max_row, row_index)
            max_col = max(max_col, col_index)
            cell_type = cell.get("t")

            if cell_type == "s":
                value_node = cell.find(qname(namespace, "v"))
                if value_node is None or value_node.text is None:
                    value = ""
                else:
                    value = shared_strings[int(value_node.text)]
            elif cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.iter(qname(namespace, "t")))
            else:
                value_node = cell.find(qname(namespace, "v"))
                value = value_node.text if value_node is not None and value_node.text is not None else ""

            values[(row_index, col_index)] = value.strip()

    rows: list[list[str]] = []
    for row_index in range(max_row + 1):
        rows.append([values.get((row_index, col_index), "") for col_index in range(max_col + 1)])
    return rows


def detect_question_column(rows: list[list[str]], path: Path) -> int:
    if not rows:
        raise ValueError(f"No rows found in {path}")

    headers = [header.strip().lower() for header in rows[0]]
    id_terms = ("id", "qid", "question id", "question_id")
    exact_question_terms = ("question", "query", "natural language question")
    for term in exact_question_terms:
        for index, header in enumerate(headers):
            if header == term:
                return index

    preferred_terms = ("question", "query", "natural language")
    for term in preferred_terms:
        for index, header in enumerate(headers):
            if term in header and not any(id_term in header for id_term in id_terms):
                return index

    sample_rows = rows[1: min(len(rows), 51)]
    scores = []
    for index in range(max(len(row) for row in rows)):
        texts = [row[index] for row in sample_rows if index < len(row) and row[index]]
        avg_len = sum(len(text) for text in texts) / len(texts) if texts else 0
        question_marks = sum("?" in text for text in texts)
        scores.append((avg_len + question_marks * 20, index))

    return max(scores)[1]


def classify_question(text: str) -> str:
    lower = text.lower()
    intents = []
    if re.search(r"\b(count|how many|number of)\b", lower):
        intents.append("count")
    if re.search(r"\b(sum|total|aggregate|average|avg|mean)\b", lower):
        intents.append("aggregation")
    if re.search(r"\b(maximum|minimum|max|min|highest|lowest|top|bottom|most|least)\b", lower):
        intents.append("ranking/comparison")
    if re.search(r"\b(compare|greater|less|more than|between|versus|vs)\b", lower):
        intents.append("comparison")
    if re.search(r"\b(year|month|quarter|date|before|after|during|latest|earliest)\b", lower):
        intents.append("temporal")
    if re.search(r"\b(list|show|find|which|what|who|where)\b", lower):
        intents.append("lookup/filter")
    return "+".join(dict.fromkeys(intents)) if intents else "other"


def extract_questions(path: Path) -> tuple[list[Question], str]:
    rows = read_first_sheet_rows(path)
    question_col = detect_question_column(rows, path)
    header = rows[0][question_col] if rows and question_col < len(rows[0]) else f"column_{question_col + 1}"

    questions: list[Question] = []
    for row_number, row in enumerate(rows[1:], start=2):
        text = row[question_col].strip() if question_col < len(row) else ""
        if text:
            questions.append(Question(row_number=row_number, text=text, qtype=classify_question(text)))
    return questions, header


def normalize(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.lower()))


def token_set(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def concept_set(text: str) -> set[str]:
    concepts = set()
    for token in TOKEN_RE.findall(text.lower()):
        token = SYNONYMS.get(token, token)
        if token not in STOP_WORDS and len(token) > 1:
            concepts.add(token)
    return concepts


def intent_set(qtype: str) -> set[str]:
    return set(qtype.split("+"))


def overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def similarity(left: str, right: str) -> float:
    lexical, _topic = similarity_parts(left, right)
    return lexical


def similarity_parts(left: str, right: str) -> tuple[float, float]:
    left_norm = normalize(left)
    right_norm = normalize(right)
    if not left_norm or not right_norm:
        return 0.0, 0.0
    seq_score = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens = token_set(left_norm)
    right_tokens = token_set(right_norm)
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens or right_tokens else 0.0
    lexical = (0.65 * seq_score) + (0.35 * jaccard)
    topic = overlap_score(concept_set(left), concept_set(right))
    return lexical, topic


def combined_similarity(left: Question, right: Question) -> tuple[float, float, float, float]:
    lexical, topic = similarity_parts(left.text, right.text)
    intent = overlap_score(intent_set(left.qtype), intent_set(right.qtype))
    combined = (0.50 * lexical) + (0.35 * topic) + (0.15 * intent)
    return combined, lexical, topic, intent


def similarity_label(score: float, topic_score: float = 0.0, intent_score: float = 0.0) -> str:
    if score >= 0.90:
        return "near duplicate"
    if score >= 0.75:
        return "very similar"
    if score >= 0.60:
        return "similar"
    if score >= 0.45:
        return "somewhat similar"
    if score >= 0.35 and topic_score >= 0.35 and intent_score > 0:
        return "related"
    return "different"


def best_matches(base_questions: list[Question], target_questions: list[Question], top_k: int = 1) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for base in base_questions:
        scored_matches: list[tuple[float, float, float, float, Question]] = []
        for target in target_questions:
            score, lexical, topic, intent = combined_similarity(base, target)
            scored_matches.append((score, lexical, topic, intent, target))

        scored_matches.sort(key=lambda item: item[0], reverse=True)
        for rank, (score, lexical, topic, intent, target) in enumerate(scored_matches[:top_k], start=1):
            results.append(
                {
                    "base_row": str(base.row_number),
                    "base_type": base.qtype,
                    "base_question": base.text,
                    "match_rank": str(rank),
                    "match_row": str(target.row_number),
                    "match_type": target.qtype,
                    "match_score": f"{score:.4f}",
                    "lexical_score": f"{lexical:.4f}",
                    "topic_score": f"{topic:.4f}",
                    "intent_score": f"{intent:.4f}",
                    "match_label": similarity_label(score, topic, intent),
                    "matched_question": target.text,
                }
            )
    return results


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "base_row",
        "base_type",
        "base_question",
        "match_rank",
        "match_row",
        "match_type",
        "match_score",
        "lexical_score",
        "topic_score",
        "intent_score",
        "match_label",
        "matched_question",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(match_rows: list[dict[str, str]]) -> dict[str, str]:
    top_rows = [row for row in match_rows if row.get("match_rank", "1") == "1"]
    scores = [float(row["match_score"]) for row in top_rows]
    labels = Counter(row["match_label"] for row in top_rows)
    same_type = sum(bool(intent_set(row["base_type"]) & intent_set(row["match_type"])) for row in top_rows)
    return {
        "questions": str(len(top_rows)),
        "average_score": f"{sum(scores) / len(scores):.4f}" if scores else "0.0000",
        "max_score": f"{max(scores):.4f}" if scores else "0.0000",
        "min_score": f"{min(scores):.4f}" if scores else "0.0000",
        "same_type_count": str(same_type),
        "same_type_percent": f"{(same_type / len(top_rows) * 100):.1f}" if top_rows else "0.0",
        "near_duplicate": str(labels["near duplicate"]),
        "very_similar": str(labels["very similar"]),
        "similar": str(labels["similar"]),
        "somewhat_similar": str(labels["somewhat similar"]),
        "related": str(labels["related"]),
        "different": str(labels["different"]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare question similarity across XLSX files.")
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--target", type=Path, action="append", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-k", type=int, default=1, help="Number of matches to keep for each base question. Default: 1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    targets = args.target or DEFAULT_TARGETS

    base_questions, base_header = extract_questions(args.base)
    print(f"Base: {args.base} | column: {base_header!r} | questions: {len(base_questions)}")

    summaries = []
    for target in targets:
        target_questions, target_header = extract_questions(target)
        rows = best_matches(base_questions, target_questions, top_k=args.top_k)
        report_name = target.stem.replace(" ", "_").replace("(", "").replace(")", "") + "_similarity.csv"
        report_path = args.output_dir / report_name
        write_csv(report_path, rows)

        summary = summarize(rows)
        summary["target"] = str(target)
        summary["target_column"] = target_header
        summary["target_questions"] = str(len(target_questions))
        summary["report"] = str(report_path)
        summaries.append(summary)

        print(f"Target: {target} | column: {target_header!r} | questions: {len(target_questions)}")
        print(
            "  avg={average_score}, same_type={same_type_percent}%, "
            "near_dup={near_duplicate}, very_similar={very_similar}, similar={similar}, "
            "somewhat={somewhat_similar}, related={related}, different={different}".format(**summary)
        )
        print(f"  report: {report_path}")

    summary_path = args.output_dir / "summary.csv"
    summary_fields = [
        "target",
        "target_column",
        "target_questions",
        "questions",
        "average_score",
        "max_score",
        "min_score",
        "same_type_count",
        "same_type_percent",
        "near_duplicate",
        "very_similar",
        "similar",
        "somewhat_similar",
        "related",
        "different",
        "report",
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
