# Question Similarity Report

This report compares two question sets against the 200-question file:

- Base reference: `/DATAAMAN/financial/final1.xlsx`
- IITK set: `/DATAAMAN/financial/iitk_testSet (2).xlsx`
- Combined set: `/DATAAMAN/financial/combined_questions_results (2).xlsx`

For each question in the IITK or combined file, the script finds the top 5 most similar questions from the 200-question file.

## Method

Similarity is calculated using three scores:

- `lexical_score`: direct wording similarity, using sentence similarity plus shared word overlap.
- `topic_score`: overlap of important topic words after removing common words like `the`, `what`, `show`, `data`.
- `intent_score`: overlap of question type, such as `count`, `aggregation`, `ranking/comparison`, `comparison`, `temporal`, or `lookup/filter`.

Final score:

```text
match_score = 0.50 * lexical_score
            + 0.35 * topic_score
            + 0.15 * intent_score
```

Labels:

```text
>= 0.90  near duplicate
>= 0.75  very similar
>= 0.60  similar
>= 0.45  somewhat similar
related   lower score but topic/intent overlap
else      different
```

## IITK Against 200 Questions

File compared: `/DATAAMAN/financial/iitk_testSet (2).xlsx`

```text
IITK questions:       53
Reference questions:  200
Top matches per row:  5
Total report rows:    265
Average best score:   0.4933
```

Best-match label counts, out of 53 IITK questions:

```text
near duplicate:       0
very similar:         0
similar:              5
somewhat similar:    30
related:              4
different:           14
```

Interpretation:

The IITK set is only moderately similar to the 200-question set. Most questions have at least a weak or partial match, but many are not close duplicates. The IITK questions often share broad finance/portfolio topics, while the exact operation or wording differs.

Detailed CSV:

`/DATAAMAN/financial/question_similarity_reports/iitk_top5_against_200/final1_similarity.csv`

## Combined Against 200 Questions

File compared: `/DATAAMAN/financial/combined_questions_results (2).xlsx`

```text
Combined questions:   90
Reference questions:  200
Top matches per row:  5
Total report rows:    450
Average best score:   0.8921
```

Best-match label counts, out of 90 combined questions:

```text
near duplicate:      41
very similar:        47
similar:              2
somewhat similar:     0
related:              0
different:            0
```

Interpretation:

The combined question set is highly similar to the 200-question set. Every combined question has a strong match in the 200-question file, and most are near duplicates or very similar.

Detailed CSV:

`/DATAAMAN/financial/question_similarity_reports/combined_top5_against_200/final1_similarity.csv`

## Overall Conclusion

The combined question file is much closer to the 200-question set than the IITK test set.

```text
combined_questions_results (2).xlsx  -> highly similar
iitk_testSet (2).xlsx                -> moderately similar
```

The combined file appears to use almost the same question style and templates as the 200-question file. The IITK file overlaps in topic, but has fewer strong wording-level or answer-equivalent matches.
