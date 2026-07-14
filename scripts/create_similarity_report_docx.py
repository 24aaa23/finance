#!/usr/bin/env python3
"""Create a DOCX report for question similarity comparisons."""

from __future__ import annotations

import csv
import html
import zipfile
from pathlib import Path


REPORT_ROOT = Path("/DATAAMAN/financial/question_similarity_reports")
OUTPUT_DOCX = REPORT_ROOT / "question_similarity_report.docx"

COMPARISONS = [
    {
        "name": "IITK Test Set Against 200 Questions",
        "source_file": "/DATAAMAN/financial/iitk_testSet (2).xlsx",
        "summary_csv": REPORT_ROOT / "iitk_top5_against_200" / "summary.csv",
        "details_csv": REPORT_ROOT / "iitk_top5_against_200" / "final1_similarity.csv",
        "interpretation": (
            "The IITK set is moderately similar to the 200-question file. "
            "Several questions share finance and portfolio topics, but many are not close duplicates."
        ),
    },
    {
        "name": "Combined Questions Against 200 Questions",
        "source_file": "/DATAAMAN/financial/combined_questions_results (2).xlsx",
        "summary_csv": REPORT_ROOT / "combined_top5_against_200" / "summary.csv",
        "details_csv": REPORT_ROOT / "combined_top5_against_200" / "final1_similarity.csv",
        "interpretation": (
            "The combined question set is highly similar to the 200-question file. "
            "Every combined question has a strong match among the 200 questions."
        ),
    },
]


def read_one_row(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No rows found in {path}")
    return rows[0]


def read_top_examples(path: Path, limit: int = 5) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("match_rank") == "1"]
    rows.sort(key=lambda row: float(row["match_score"]), reverse=True)
    return rows[:limit]


def text(value: str) -> str:
    return html.escape(value, quote=False)


def paragraph(value: str, style: str | None = None) -> str:
    style_xml = f'<w:pStyle w:val="{style}"/>' if style else ""
    return (
        "<w:p>"
        f"<w:pPr>{style_xml}</w:pPr>"
        f"<w:r><w:t xml:space=\"preserve\">{text(value)}</w:t></w:r>"
        "</w:p>"
    )


def table(rows: list[list[str]]) -> str:
    table_rows = []
    for row in rows:
        cells = []
        for cell in row:
            cells.append(
                "<w:tc>"
                "<w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr>"
                f"{paragraph(cell)}"
                "</w:tc>"
            )
        table_rows.append(f"<w:tr>{''.join(cells)}</w:tr>")
    return (
        "<w:tbl>"
        "<w:tblPr>"
        "<w:tblStyle w:val=\"TableGrid\"/>"
        "<w:tblW w:w=\"0\" w:type=\"auto\"/>"
        "</w:tblPr>"
        + "".join(table_rows)
        + "</w:tbl>"
    )


def build_document_xml() -> str:
    body: list[str] = []
    body.append(paragraph("Question Similarity Summary", "Title"))
    body.append(paragraph("Reference set: 200 questions from /DATAAMAN/financial/final1.xlsx."))
    body.append(paragraph("Method: each IITK/combined question was compared against all 200 questions. The top 5 matches were selected using lexical similarity, topic-word overlap, and question-intent overlap."))

    summary_rows = [["Dataset", "Questions", "Avg Score", "Strong Matches", "Partial/Related", "Different"]]

    comparison_summaries: list[tuple[dict[str, str], dict[str, str]]] = []
    for comparison in COMPARISONS:
        summary = read_one_row(comparison["summary_csv"])
        comparison_summaries.append((comparison, summary))
        strong = int(summary["near_duplicate"]) + int(summary["very_similar"]) + int(summary["similar"])
        partial = int(summary["somewhat_similar"]) + int(summary["related"])
        summary_rows.append(
            [
                comparison["name"].replace(" Against 200 Questions", ""),
                summary["questions"],
                summary["average_score"],
                str(strong),
                str(partial),
                summary["different"],
            ]
        )

    body.append(table(summary_rows))
    body.append(
        paragraph(
            "Conclusion: combined_questions_results (2).xlsx is highly similar to the 200-question set. "
            "It has 90/90 strong matches and no different questions. IITK is only moderately similar: "
            "39/53 questions are at least partial/related matches, while 14/53 are different."
        )
    )
    body.append(paragraph("Detailed CSVs are available in combined_top5_against_200/final1_similarity.csv and iitk_top5_against_200/final1_similarity.csv."))

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(body)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="720" w:bottom="1440" w:left="720" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
        + "</w:body></w:document>"
    )


def build_styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="280" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="220" w:after="100"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
        '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/></w:tblBorders></w:tblPr></w:style>'
        "</w:styles>"
    )


def create_docx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            "</Types>",
        )
        docx.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        docx.writestr(
            "word/_rels/document.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        docx.writestr("word/document.xml", build_document_xml())
        docx.writestr("word/styles.xml", build_styles_xml())


def main() -> None:
    create_docx(OUTPUT_DOCX)
    print(f"Saved: {OUTPUT_DOCX}")


if __name__ == "__main__":
    main()
