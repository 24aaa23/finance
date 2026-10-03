# Phase 0 — Working Business-Rules Spec (442 disputed rows)

**Purpose.** This is the agreed rule set we will bind every re-authored ground-truth SQL to,
when correcting the 442 "Relevant + Correct" rows IIT Kanpur flagged (arithmetic ground truths
wrong / partially wrong). It resolves the three root causes we diagnosed:
(1) aggregation grain, (2) undefined band/metric thresholds, (3) join population.

**Scope.** Applies **only to the 442 rows**. Nothing here changes the 1,000-question corpus.

**Authoritative source.** `wealthmanagement_tables-main_repository_download/domain_intro.prompt`
(the client's own domain spec). Its DB (`raw_data_sample/wealth_management_diverse.db`) is
**byte-identical** (MD5 `2675e1406fa16956f9037d7c39931d9f`) to our
`wealth_management_diverse.db`, so every rule below applies directly to our data.
The `table_medatada/*.yaml` files only *name* derived metrics qualitatively — the numbers live
in `domain_intro.prompt`.

---

## A. Confirmed decisions (locked with the user)

### A1. Column-name mapping (verified empirically)
- `progress_pct` (our `ATOM_ENTITY_INVESTMENT_GOAL_001`) **≡** `achievement_pct` in the spec.
  Verified: `progress_pct = current_value / target_amount × 100` matches to the decimal on all rows.
- `shortfall` **≡** `target_amount − current_value` (verified exactly).
- Spec fields **not present** in our DB: `target_date`, `time_horizon` on the goal table
  (we have `time_to_goal_months` instead). Any spec rule keyed on `target_date` is out of scope
  for arithmetic GT unless a question needs it — flag if encountered.

### A2. Aggregation grain — **"grain follows the grouping dimension"**
- **Group by an _investor_ attribute** (`segment`, `risk_tolerance`, `time_horizon`,
  customer `segment`) → **per-investor-first**: compute the metric per investor in a CTE
  (one row per investor), then `AVG()` across investors. Investors are the unit; this prevents
  investors with many goals/holdings from dominating and matches spec §6
  ("AVG per investor across goals; do NOT SUM"; "cross-investor AVG only meaningful within segment").
- **Group by the _child row's own_ attribute** (`investment_goal` type, `sector`,
  `investment_type`, cash-flow `type`) → **aggregate the rows directly** (the row is the natural
  unit). This is why `GROUP BY investment_goal` (SQA-1T-006) was already correct.
- **No grouping / whole-cohort** average of a per-investor metric → per-investor-first.

### A3. `returns_pct` weighting — honor the question's literal wording
- Question says "average return" → **equal-weighted** `AVG(returns_pct)` at the A2 grain.
- Switch to **value-weighted** (by `cost`/`current_value`) **only** when the question explicitly
  says "portfolio / overall / value-weighted return."
- Rationale note (for IIT Kanpur): spec §6.2 states a general *preference* for value-weighting;
  we deliberately answer the literal question and caveat where relevant.

### A4. Join population — **LEFT JOIN from `investor_profile`**
- Every multi-table cohort query = `investor_profile LEFT JOIN <pre-aggregated child CTEs>`.
- Each child table is **pre-aggregated to one row per investor in its own CTE** (fan-out safe),
  then joined. All cohort investors are retained; a missing child metric is `NULL` and naturally
  excluded by `AVG` — but the investor is **not** silently dropped from other metrics.
  Replaces the old `INNER JOIN` chains that shrank denominators.

### A5. PPF lock-in conflict → use **15 years**
- Spec §5 says PPF = 2 yr; §4.2/H4 says 15 yr (contradiction). We use **15 years** (detailed
  sense-check rule + domain-accurate). ELSS = 3 years (consistent). Low impact (flagging rule,
  not arithmetic). **Flag this contradiction to IIT Kanpur.**

---

## B. Numeric thresholds & bands (from `domain_intro.prompt`; replaces our invented cutoffs)

### B1. Portfolio health bands (§3.3) — scores are 0–100
| Metric | Band | Label |
|---|---|---|
| `goal_match_pct` | ≥ 80 | On track |
| `goal_match_pct` | 60–79 | Needs attention |
| `goal_match_pct` | < 60 | At risk |
| `risk_score` | 0–40 | Low risk |
| `risk_score` | 41–70 | Moderate risk |
| `risk_score` | 71–100 | High risk |
| `liquidity_score` | ≥ 70 | Adequate liquidity |
| `diversification_score` | ≥ 70 | Well diversified |

### B2. Goal progress (§3.4)
- `progress_pct` (≡ achievement_pct) = `current_value / target_amount × 100`.
- `progress_pct` < 50 **and** deadline within 2 yr → high-priority advisory (needs `target_date`; n/a in our DB).

### B3. Allocation / concentration / suitability (§3.5, §4.3, §5)
- Drift = `|current_allocation_pct − target_allocation_pct|`; **> 10 pp** → rebalance trigger.
- Single-sector concentration caps: **Conservative > 30%**, **Moderate > 40%**, **Aggressive > 50%** → flag.
- Conservative investor **equity ≤ 40%** (else suitability breach); Aggressive equity cap 80%.
- Sector `allocation_pct` per investor must sum to 100% (±1%).

### B4. Returns / XIRR plausibility (§3.1, §3.2)
- Simple return = `(current_value − cost)/cost × 100` = stored `returns_pct`.
- XIRR: **never pool** across investors; compute per investor, report distribution
  (MIN/P25/MEDIAN/P75/MAX). XIRR > 25% or < −50% → flag as suspect.

### B5. Aggregation guardrails (§6)
- **Never aggregate** ids, dates, or categorical/enum fields (§6.1): `investor_id`, `goal_id`,
  `holding_id`, `cash_flow_id`, `rebalance_id`, `portfolio_health_id`, `purchase_date`,
  `risk_tolerance`, `segment`, `investment_goal`, `action`, `investment_type`, `sector`,
  `category`, cash-flow `type`. Use COUNT / COUNT(DISTINCT) / GROUP BY only.
- `goal_match_pct`: AVG per investor across goals; never SUM (ceiling 100).
- `amount` (cash flow): filter by `type` before SUM; never mix inflow/outflow.
- COUNT investors = `COUNT(DISTINCT investor_id)`.

### B6. Lock-in / tax (§4.2, §5)
- ELSS lock-in = 3 yr; PPF = **15 yr** (see A5). ELSS & PPF are 80C tax-saving.

---

## C. Standard SQL shape we will use (fan-out safe + A2/A4 compliant)

Cohort comparison grouped by an investor attribute:
```sql
WITH goal AS (   -- one row per investor
  SELECT investor_id, AVG(progress_pct) AS progress_pct
  FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investor_id
)
SELECT p.segment AS group_value,
       ROUND(AVG(goal.progress_pct), 2) AS avg_progress_pct,
       COUNT(DISTINCT p.investor_id)     AS n_investors
FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p
LEFT JOIN goal ON goal.investor_id = p.investor_id   -- keep all investors
GROUP BY p.segment
ORDER BY p.segment;
```
Grouped by a child-row attribute (natural grain, pool rows directly):
```sql
SELECT investment_goal AS group_value,
       ROUND(AVG(progress_pct), 2) AS avg_progress_pct,
       ROUND(AVG(shortfall),    2) AS avg_shortfall
FROM ATOM_ENTITY_INVESTMENT_GOAL_001
GROUP BY investment_goal ORDER BY investment_goal;
```

---

## D. Open items to flag to IIT Kanpur (do not block Phase 1)
1. PPF lock-in contradiction (A5) — confirm 15 yr.
2. `returns_pct` weighting policy (A3) — confirm "literal wording" convention is acceptable.
3. Fields with no `target_date`/`time_horizon` in our goal table — any rule needing them is n/a.

---

## E. Status
Phase 0 **CLOSED**. Rules above govern Phase 1 (triage of the 442 into: GT-wrong-grain /
GT-wrong-rule / GT-correct-pipeline-error) and Phase 2 (re-author SQL + regenerate ground truth).
