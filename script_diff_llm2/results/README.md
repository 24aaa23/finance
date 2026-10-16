# Retained results

Seven selected graded reports, backed by six unique raw reports. The links below point to original run files; no large CSVs were duplicated or moved. All retained files have 1,000 rows.

| ID | Experiment | Match accuracy | Raw | Graded |
|---|---|---:|---|---|
| G01 | Improvement 10 SQL-only — DeepSeek V3.2, four-worker run; grader 2 / GPT-5 mini | 74.4% | [raw](retained/G01/raw.csv) | [graded](retained/G01/graded.csv) |
| G10 | Main hybrid — DeepSeek V3.2, without context, reliability_v6_01; grader 2 / GPT-5 mini | 80.6% | [raw](retained/G10/raw.csv) | [graded](retained/G10/graded.csv) |
| G14 | Main hybrid — Gemma 3 27B IT, without context, reliability_v6_01; grader 2 / GPT-5 mini | 61.3% | [raw](retained/G14/raw.csv) | [graded](retained/G14/graded.csv) |
| G16 | Main hybrid — GPT-OSS 120B, without context, reliability_v6_01; grader 2 / GPT-5 mini | 78.9% | [raw](retained/G16/raw.csv) | [graded](retained/G16/graded.csv) |
| G11 | Main hybrid — DeepSeek V3.2, without context, reliability_v6_01; grader 3 / GPT-5 mini | 81.0% | [raw](retained/G11/raw.csv) | [graded](retained/G11/graded.csv) |
| G15 | Main hybrid — GPT-OSS 120B, with context, reliability_v6_01; grader 2 / GPT-5 mini | 79.0% | [raw](retained/G15/raw.csv) | [graded](retained/G15/graded.csv) |
| G09 | Main hybrid — DeepSeek V3.2, with context, reliability_v6_01; grader 2 / GPT-5 mini | 78.3% | [raw](retained/G09/raw.csv) | [graded](retained/G09/graded.csv) |

G10 and G11 use the same raw report, evaluated by graders 2 and 3 respectively. Match percentages include all 1,000 saved rows in the denominator; partial/error rows are not matches.

The prior full inventory and deletion records remain in `analysis/csv_inventory_20261016/`. Its older links to unretained reports are historical and may no longer exist.
