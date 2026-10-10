# Business-Rules Addendum — calculation rules used in this review

These rules extend `phase0_business_rules.md` and are grounded in `domain_intro.prompt`,
`table_medatada/*.yaml`, and **empirically verified facts of `wealth_management_diverse.db`**.
They are the "clear, agreed business rules" IIT Kanpur asked for. The previously-open items (R2, R3, R8,
and the returns-weighting policy) have now been **ratified by the IIT Kanpur expert** and are implemented
as-is throughout the deliverables; the rulings are recorded in each rule and in the
"Resolved rule clashes" and "Ratification status" sections at the end of this file.

---

## R1. Cash-flow sign convention  (empirically verified)
Cash-flow `amount` is **stored signed** in the DB:
- **Inflows positive** — `Deposit, SIP, Interest Credit, Tax Refund, Dividend Reinvestment, Lump Sum`
  (and blank/`None` type): all `amount ≥ 0`.
- **Outflows negative** — `Withdrawal, Redemption`: all `amount ≤ 0`.

Consequences (mandatory):
- **R1.1 Net cash flow = `SUM(amount)`.** Do **not** re-sign with
  `CASE WHEN inflow THEN amount ELSE -amount END` — on already-signed data that double-negates
  outflows and inflates net flow. *(This is the root cause of concern 3(e).)*
- **R1.2 Outflow magnitude** (e.g. "total amount withdrawn") = `-SUM(amount)` or `SUM(ABS(amount))`
  over that type.

## R2. Withdrawal / outflow presentation  **[RATIFIED by expert — use as-is]**
When a question asks for a "total Withdrawal amount" / "amount withdrawn" (a magnitude), present it
as a **positive number** (`-SUM(amount)`), alongside positive Deposit totals, so the two are directly
comparable. Rationale: the noun "amount withdrawn" denotes magnitude; mixing a positive deposit with a
negative withdrawal in a comparison is confusing. *(Resolves concern 3(d) — standardize to positive.)*
Net-flow questions still keep sign per R1.1.

## R3. Ranking tie-break rule  **[RATIFIED by expert — use as-is]**
Any `ORDER BY <score> LIMIT k` where the score can tie (it can: `returns_pct=9900` has 50 rows;
`risk_score=100`, and the 0–100 health scores tie heavily) must add a **deterministic secondary key**
so the result is stable and reproducible:
`ORDER BY <score> DESC/ASC, <entity_id> ASC`.
We use the natural id (`holding_id`, `investor_id`). *(Resolves concern 3(b).)*

## R4. Missing scores in "highest/lowest" rankings
Health scores are NULL for **77 of 1550** investors (`risk_score, liquidity_score,
diversification_score, goal_match_pct` — same 77). A NULL is *missing*, **not** the lowest value.
"Which N have the lowest X?" must add `WHERE X IS NOT NULL` so missing rows are not returned as the
bottom. Symmetrically, `ORDER BY X DESC` already drops NULLs last, but we still add `IS NOT NULL` for
clarity. *(Resolves concern 3(c).)*

## R5. Averaging grain must be uniform across metrics  (extends phase0 A2)
When grouping by an **investor attribute** (`risk_tolerance, time_horizon, segment, category,
sector_focus`), **every** averaged metric is computed **per-investor-first** (aggregate to one row per
investor in a CTE, then `AVG` across investors). Do not mix a per-investor-first metric with a
row-pooled metric in the same SELECT. *(Resolves concern 3(f): EC-4T-013 averaged allocation
per-investor-first but pooled returns at holding grain.)*

## R6. Join only what the question asks; keep the population intact  (extends phase0 A4)
- **R6.1** Do not join a table the question does not reference. An extra `INNER JOIN` (e.g. to
  `PORTFOLIO_HEALTH` or `SECTOR_ALLOCATION`) silently drops investors lacking that child record and
  changes counts/averages. *(Resolves concern 3(g).)*
- **R6.2** When a question legitimately combines optional child metrics, join child CTEs with
  `LEFT JOIN` from `INVESTOR_PROFILE` (one row per investor) so no cohort member is dropped.
- **R6.3** Conversely, every condition the question *does* state must be expressed in SQL
  (an existence filter, a value filter, a join). *(Resolves concern 3(a).)*

## R7. Allocation concentration  (the flagship derived metric)
`allocation concentration` for an investor = **the largest single-sector share** =
`MAX(allocation_pct)` over that investor's rows in `ATOM_ENTITY_SECTOR_ALLOCATION_001`.
A cohort's "average allocation concentration" = **per-investor MAX, then AVG across investors** (R5).
Grounding: domain_intro §3.5/§4.3 single-sector concentration caps (Conservative >30%, Moderate >40%,
Aggressive >50%) are defined on the *single largest* sector share, i.e. the per-investor MAX.
Any question using this metric must **state the definition in its wording** (e.g. "average of each
investor's largest single-sector allocation %").

## R8. Composite scores — **EXPERT-RATIFIED formulas**
A composite score combines several metrics into one ranked number. Mixed-scale sums (0–100 score + INR
amount + percentage-point delta) are dominated by the largest-magnitude term and are not interpretable,
so every composite must have an agreed formula. The definitions below are **ratified by the expert** and
are implemented **consistently** across the deliverables (rewrites in
`review_sql_correct_442.xlsx` → sheet `5_Composite_Metric_Rewrites`, GT in
`442_verified_gt_with_business_rules.xlsx`).

### R8.0 Shared per-investor term definitions (keyed by `investor_id`)
| Symbol | Definition | Table.column | Scale/unit |
|---|---|---|---|
| `RS`,`LS`,`DS`,`GM` | risk / liquidity / diversification / goal-match score (1 row per investor) | `ATOM_ENTITY_PORTFOLIO_HEALTH_001.{risk_score,liquidity_score,diversification_score,goal_match_pct}` | 0–100 |
| `CONC` | allocation concentration = `MAX(allocation_pct)` (R7) | `ATOM_ENTITY_SECTOR_ALLOCATION_001.allocation_pct` | 0–100 (%) |
| `VOL` | `AVG(avg_volatility_pct)` | `ATOM_ENTITY_INVESTMENT_GOAL_001.avg_volatility_pct` | ~0–30 (%) |
| `SHORT` | `SUM(shortfall)`  (shortfall = target_amount − current_value) | `ATOM_ENTITY_INVESTMENT_GOAL_001.shortfall` | INR |
| `AVGSHORT` | `AVG(shortfall)` | `ATOM_ENTITY_INVESTMENT_GOAL_001.shortfall` | INR |
| `GAIN` | `SUM(current_value − cost)` | `ATOM_ENTITY_PORTFOLIO_HOLDING_001` | INR |
| `HVAL` | `SUM(current_value)` | `ATOM_ENTITY_PORTFOLIO_HOLDING_001.current_value` | INR |
| `NCF` | `SUM(amount)` (signed; R1); over the **period the question states** | `ATOM_EVENT_CASH_FLOW_001.amount` | INR |
| `REB` | `SUM(amount)` | `ATOM_EVENT_REBALANCING_ACTION_001.amount` | INR |
| `SCENΔsum` | `SUM(new_allocation_pct − current_allocation_pct)` (standardized to SUM) | `ATOM_EVENT_SCENARIO_REBALANCING_001` | percentage-point |

### R8.1 Ratified composite inventory
| # | Official metric | Question IDs | Ratified formula | Treatment |
|---|---|---|---|---|
| C1 | `risk_pressure_score` | SQA-3T-018, SQA-4T-013, SQA-4T-014, SQA-5T-007 (also a term of C3) | `RS + (100 − LS) + (100 − DS)`  (0–300; NULL if any health score is NULL → investor excluded) | **Keep — the single official `risk_pressure_score`.** |
| ~~C2~~ | ~~`risk_pressure_score` (5-term)~~ | MC-104 | ~~`RS + CONC + VOL − LS + SCENΔavg`~~ | **DROPPED. MC-104 → remove & replace** with a single-scale question. The 5-term formula is void. |
| C3 | `quantitative_burden_index` | SQA-5T-002, SQA-5T-006 | normalized 0–100 index (R8.2) of `{SHORT, −GAIN, −NCF, C1}` | Rewritten to the index; SQA-5T-006 threshold reset (R8.3). |
| C4 | `combined_gain_and_ncf` | SQA-4T-006 | `GAIN + NCF` (INR) | Kept; **renamed** from `combined_amount`. |
| C5 | `combined_ncf_and_reb` | TT-033 | `NCF + REB` (INR) | Kept; **renamed** from `combined_amount`. |
| C6 | `combined_holding_value_and_shortfall` | WM-4T-005 | `HVAL + SHORT` (INR) | Kept. |
| C7 | `transaction_rebalance_index` | TT-057 | normalized 0–100 index (R8.2) of `{NCF, REB, SCENΔsum}` | Rewritten to the index. |
| C8 | `temporal_pressure_index` | TT-063 | normalized 0–100 index (R8.2) of `{NCF(period), REB, −AVGSHORT, SCENΔsum}` | Rewritten to the index; NCF window = the year the question states. |

### R8.2 Normalized 0–100 index (C3, C7, C8)
Over the population of investors that have **all** components present (missing-component investors are
excluded, consistent with the C1 NULL rule), for each component `x`:
`x̃ = (x − min_pop(x)) / (max_pop(x) − min_pop(x))`  (min-max to [0,1]; guard `max=min`), then
`index = 100 × mean(x̃₁, …, x̃ₙ)` with **equal weights**. A component that should *reduce* the score
enters as `(1 − x̃)` (shown with a leading `−` in R8.1). Exact forms:
- **C3** `quantitative_burden_index = 100 × mean( S̃HORT , (1−G̃AIN) , (1−ÑCF) , C̃1 )`, `C1 = risk_pressure_score`.
- **C7** `transaction_rebalance_index = 100 × mean( ÑCF , R̃EB , S̃CENΔsum )`.
- **C8** `temporal_pressure_index = 100 × mean( ÑCF(period) , R̃EB , (1−ÃVGSHORT) , S̃CENΔsum )`.
Rankings add the R3 id tie-break. The index is **population-relative** to this DB.

### R8.3 Ratified consequences applied to the deliverables
- **C2 / MC-104:** dropped; MC-104 is **remove & replace** (single-scale) — sheet `5_Composite_Metric_Rewrites`.
- **`risk_pressure_score`:** C1 (`RS + (100−LS) + (100−DS)`) is the single official definition.
- **Renames:** C4 → `combined_gain_and_ncf`; C5 → `combined_ncf_and_reb` (formulas unchanged).
- **C8 NCF window:** taken from the year the question states (TT-063 states 2025 → NCF = 2025 flows). If a
  question uses a period-bearing term without stating the period, the **question is incomplete** and must
  be fixed at the question level.
- **SQA-5T-006 threshold:** the old `> 50,000,000` is meaningless on a 0–100 index → reset to
  **`quantitative_burden_index > 65`** (≈ top ~3%, 36 investors — a "critical burden" cohort). *[expert-confirmable]*
- **Scenario-change aggregation:** standardized to `SUM` (`SCENΔsum`) for C7/C8.

### R8.4 Expert answers to the earlier open questions (closed)
1. `risk_pressure_score` = C1 (3-term) only; **C2 dropped**.
2. C3/C7/C8 → **normalised 0–100 index** (confirmed).
3. Component **weights = equal** (confirmed).
4. C2 dropped; scenario-change **standardized to SUM** for C7/C8.
5. NCF period **must be stated in the question**; a period-less question is incomplete.

## R9. returns_pct weighting (restate phase0 A3)  **[RATIFIED by expert — equal-weighted]**
"average return" → equal-weighted `AVG(returns_pct)` at the per-investor-first grain (R5).
"portfolio / overall / value-weighted return" → weight by `current_value`/`cost`. Honor the wording.
The expert has ratified **equal-weighting** (this overrides domain_intro §6.2's value-weighted preference;
corrected in `domain_intro_latest.prompt` §6.2 — see "Resolved rule clashes" below). The 10 "average return"
rows keep their equal-weighted ground truth.

## R11. Proportion / "share of investors" denominators
"What share of investors in the group have metric > X?" uses the **full cohort** as the denominator
(`AVG(CASE WHEN metric > X THEN 1 ELSE 0 END)` over every investor in the group). A missing (NULL)
metric counts as **not** meeting the threshold and is **not** removed from the denominator — dropping
NULL-metric investors would shrink the denominator and inflate the share. This is distinct from R4,
which excludes NULLs only from *highest/lowest rankings* (where a missing value must not masquerade as
an extreme), not from proportions.

## R10. Aggregation guardrails (restate phase0 B5)
Never aggregate ids / dates / enums; count investors with `COUNT(DISTINCT investor_id)`;
`goal_match_pct` and other 0–100 scores are AVG'd per investor, never summed.

---

### Resolved rule clashes (found across the source spec; all expert-ratified)
Three genuine contradictions in `domain_intro.prompt` were found and resolved; the corrected spec is
`domain_intro_latest.prompt`.
- **CLASH 1 — cash-flow signs.** §3.1/§4.1-B6/§6.3 stated "inflows negative, outflows positive" (an XIRR
  modelling convention) — the **opposite** of how the DB stores amounts. **Resolved:** inflows are stored
  **positive**, outflows **negative** (R1); the XIRR sign-flip is re-stated as an explicit `−amount`
  transform. No 442 GT computes XIRR, so no GT changed.
- **CLASH 2 — PPF lock-in.** §4.2-H4 said 15 yr, §5 said 2 yr. **Resolved: 15 years** (A5); §5 corrected.
- **CLASH 3 — `returns_pct` weighting.** §6.2 preferred value-weighted; phase0 A3 uses equal-weighted for
  "average return". **Resolved: equal-weighted** (R9); §6.2 corrected. Affects the 10 "average return" rows,
  which keep their equal-weighted GT.
- *Non-clash data/spec note:* the DB's enum **values** (asset categories, investment types, sectors, goals)
  differ from §2's lists; the **DB is authoritative** for values (SQL uses actual DB values).

### Ratification status (all closed by the IIT Kanpur expert)
- **R2** — outflow totals presented as positive magnitudes. **RATIFIED.**
- **R3** — deterministic id tie-break on all top-k rankings. **RATIFIED.**
- **R8** — composite formulas: C1 is the sole `risk_pressure_score`; C2/MC-104 dropped (remove & replace);
  C3/C7/C8 use the normalized 0–100 index; C4/C5 renamed; C8 NCF window per question. **RATIFIED.**
- **R9 / A3** — `returns_pct` equal-weighted for "average return". **RATIFIED** (overrides domain_intro §6.2).
- **PPF lock-in = 15 yr** (A5). **RATIFIED.**
- Cash-flow signs: inflows positive / outflows negative (R1) is the truth (CLASH 1). **RATIFIED.**
- The only remaining expert-confirmable value: the **SQA-5T-006 index threshold (`>65`)** (R8.3).
