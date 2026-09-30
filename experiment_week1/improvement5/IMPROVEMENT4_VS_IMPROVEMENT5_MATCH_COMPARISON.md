# Improvement4 vs Improvement5 Match Percentage

Compared graded outputs only.

## Files Used

- Improvement4: `improvement4/pipelien_output/graded_v1_*_terra.csv`
- Improvement5: `improvement5/pipeline_output_v1/*/*_graded.csv`

Important: `improvement5/pipeline_output_v2/*_v2.csv` files are run outputs, but they are not graded yet. So v2 match percentage cannot be calculated from those files until grading is run.

## Match Percentage Comparison

| Dataset | Improvement4 Match | Improvement5 Match | Difference |
| --- | ---: | ---: | ---: |
| ARC | 82.76% | 82.86% | +0.10% |
| BSQ | 63.16% | 67.50% | +4.34% |
| EC | 66.10% | 64.62% | -1.48% |
| MC | 19.74% | 20.00% | +0.26% |
| RC | 63.64% | 74.55% | +10.91% |
| SQA | 64.15% | 63.08% | -1.07% |
| TT | 70.27% | 52.31% | -17.96% |
| WM | 78.79% | 78.57% | -0.22% |

## Total

For the same 8 datasets:

| Version | Total Rows | Matches | Match Percentage |
| --- | ---: | ---: | ---: |
| Improvement4 | 442 | 273 | 61.76% |
| Improvement5 | 535 | 319 | 59.63% |

Improvement5 is lower by **2.13 percentage points** on these compared graded files.

## Extra Improvement5 Dataset

Improvement5 also has `MC_diverse`, which was not present in the improvement4 8-dataset summary.

| Dataset | Total Rows | Matches | Match Percentage |
| --- | ---: | ---: | ---: |
| MC_diverse | 70 | 10 | 14.29% |

Including all 9 available improvement5 graded datasets:

| Version | Total Rows | Matches | Match Percentage |
| --- | ---: | ---: | ---: |
| Improvement5 all 9 | 605 | 329 | 54.38% |

