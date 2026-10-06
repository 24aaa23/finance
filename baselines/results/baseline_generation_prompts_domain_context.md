# Baseline generation prompts

This document records the prompts sent to the pipeline-runner models for the six baselines. It excludes all GPT-5 Mini grading prompts and grading instructions.

Every generation request used one `user` message and no separate `system` message. The model choice changed between runs, but the prompt templates did not.

## Placeholder key

| Placeholder | Runtime value |
|---|---|
| `{REFERENCE_CONTEXT}` | The domain introduction and Phase 0 business rules, joined using the wrapper below. |
| `{RDF_SCHEMA}` | RDF namespace bindings, classes, properties, and datatypes derived from the active schema and Fuseki metadata. |
| `{SQLITE_DDL}` | `CREATE TABLE` statements read from the active SQLite database. |
| `{RETRIEVED_RDF_FACTS}` | Per-question facts returned by the bounded local GraphRAG retrieval stage. |
| `{QUESTION}` | The current benchmark question. |
| `{PREPASS_EXAMPLE_BLOCKS}` | DAIL-SQL examples selected using masked-question similarity. |
| `{FINAL_EXAMPLE_BLOCKS}` | DAIL-SQL examples reselected using the preliminary SQL skeleton. |

Each DAIL-SQL example block has this exact structure:

```text
/* Answer the following: {EXAMPLE_QUESTION} */
{EXAMPLE_SQL}
```

## Shared reference-context wrapper

All six baselines insert the same two files verbatim into `{REFERENCE_CONTEXT}`:

```text
Domain introduction:
{DOMAIN_INTRO_CONTENT}

Phase 0 business rules:
{PHASE0_BUSINESS_RULES_CONTENT}
```

The full contents are reproduced in the appendices.

- `domain_intro.prompt` SHA-256: `949546f7d36d89a79c20f39c8fc00bf7e60d15634c8f9915381aa56dd0dbeece`
- `phase0_business_rules.md` SHA-256: `4820bfd42c2c69231669027420d10eab0cf5493e6c46193914806c5c33e072b2`

## Base SPARQL

Source: `baselines/base_pipeline_qwen/run_pipeline.py`

A single generation call receives the shared reference context, the dynamically constructed RDF schema, and the question.

```text
Reference context:
{REFERENCE_CONTEXT}

RDF schema:
{RDF_SCHEMA}

Question:
{QUESTION}

Return only the SPARQL query. Do not include reasoning, explanations, markdown,
comments, or prose.
```

## Base SQL

Source: `baselines/base_pipeline_sql/run_pipeline.py`

A single generation call receives the shared reference context, the SQLite DDL, and the question.

```text
Reference context:
{REFERENCE_CONTEXT}

Database schema (DDL):
{SQLITE_DDL}

Question:
{QUESTION}

Return only the SQL query. Do not include reasoning, explanations, markdown,
comments, or prose.
```

## GraphRAG Local

Source: `baselines/graph_rag_local/run_pipeline.py`

The retrieval stage is deterministic and does not call an LLM. The sole generation call receives the shared reference context, the retrieved RDF facts, and the question.

```text
Reference context:
{REFERENCE_CONTEXT}

RDF facts:
{RETRIEVED_RDF_FACTS}

Question:
{QUESTION}

Return exactly one JSON object with keys status, answer, and evidence_uris. Set status to answered or insufficient_evidence.
```

The response contract requires one JSON object with `status`, `answer`, and `evidence_uris`. A response marked `answered` without a retrieved evidence URI is converted to `insufficient_evidence` by the pipeline.

## Parallel SPARQL ensemble

Sources: `baselines/parallel_pipeline_baseline/run_pipeline.py` and `baselines/parallel_pipeline_baseline/run.py`

Each parallel branch independently receives the same prompt template. The pipeline compares executed result fingerprints for consensus. The reported run is single-round and does not add repair or grader feedback to generation.

```text
Reference context:
{REFERENCE_CONTEXT}

RDF schema:
{RDF_SCHEMA}

Question:
{QUESTION}

Return only the SPARQL query. Do not include reasoning, explanations, markdown,
comments, or prose.
```

## Parallel SQL ensemble

Source: `baselines/parallel_pipeline_sql_baseline/run_pipeline.py`

Each parallel branch independently receives the same prompt template. The pipeline compares executed result fingerprints for consensus.

```text
Reference context:
{REFERENCE_CONTEXT}

Database schema (DDL):
{SQLITE_DDL}

Question:
{QUESTION}

Return only the SQL query. Do not include reasoning, explanations, markdown,
comments, or prose.
```

## DAIL-SQL

Source: `baselines/dail_sql_baseline/run_pipeline.py`

DAIL-SQL makes two generation calls per question. Both calls use the same structural template and shared context. Only the selected demonstration examples differ.

### Preliminary-SQL call

The first call uses examples selected by similarity between schema-masked questions.

```text
Reference context:
{REFERENCE_CONTEXT}

/* Some SQL examples are provided based on similar problems: */
{PREPASS_EXAMPLE_BLOCKS}

/* Given the following database schema: */
{SQLITE_DDL}

/* Answer the following: {QUESTION} */

Return only the complete SQLite SQL query. Do not include reasoning, explanations, markdown, comments, or prose.
```

### Final-SQL call

The preliminary SQL is converted to a schema-masked SQL skeleton. The second call uses examples reselected by question similarity and skeleton similarity.

```text
Reference context:
{REFERENCE_CONTEXT}

/* Some SQL examples are provided based on similar problems: */
{FINAL_EXAMPLE_BLOCKS}

/* Given the following database schema: */
{SQLITE_DDL}

/* Answer the following: {QUESTION} */

Return only the complete SQLite SQL query. Do not include reasoning, explanations, markdown, comments, or prose.
```

The preliminary SQL and its skeleton guide example selection only; neither is inserted directly into the final prompt.

## Appendix A: domain introduction

Source: `baselines/domain_intro.prompt`

```markdown
# Wealth Management Domain — AI Agent Introduction Prompt

---

## 1. Domain Overview

This platform manages retail and HNI investor portfolios. The core business operations are:

- **Portfolio Construction** — building investor portfolios aligned to risk tolerance, investment goals, and time horizon.
- **Performance Tracking** — measuring returns (including XIRR) against goals and benchmarks.
- **Health Monitoring** — evaluating portfolios across goal alignment, risk, liquidity, and diversification scores.
- **Rebalancing** — identifying allocation drift and generating buy/sell/hold recommendations.
- **Goal-Based Advisory** — tracking investor progress toward specific financial goals (Retirement, Education, Wealth Creation, etc.).
- **Cash Flow Management** — recording deposits, SIP contributions, withdrawals, and redemptions.

The platform operates on **Indian financial markets** (currency: INR ₹). Market cap segments use Indian conventions (Large Cap > ₹20,000 Cr, Mid Cap ₹5,000–20,000 Cr, Small Cap < ₹5,000 Cr).


## 2. Investor Classification

### Risk Tolerance
- **Conservative** — Capital preservation focus; low volatility tolerance; debt-heavy allocation.
- **Moderate** — Balanced growth and preservation; mixed allocation.
- **Aggressive** — Growth-focused; high volatility tolerance; equity-heavy allocation.

### Customer Segments
- **Premium** — High-value clients with sophisticated advisory needs.
- **Standard** — Mid-tier clients.
- **Mass** — Retail clients.

### Investment Goals
`Wealth Preservation` | `Growth` | `Income Generation` | `Retirement Planning` | `Child Education` | `Emergency Fund`

### Time Horizons
- Very Short Term: < 1 year
- Short Term: 1–3 years
- Medium Term: 3–7 years
- Long Term: 7–15 years
- Very Long Term: > 15 years

### Asset Categories
`Equity` | `Debt` | `Hybrid` | `Alternative`

### Investment Types
`Mutual Fund` | `Stock` | `Bond` | `ETF` | `ELSS` | `PPF`

### Sectors
Technology | Financial Services | Healthcare | Consumer Goods | Energy | Utilities | Real Estate | Materials | Industrials | Communication Services

---

## 3. KPI Definitions and Validation Rules

### 3.1 XIRR (Extended Internal Rate of Return)

**Definition:** XIRR is the annualised return of an investment computed from irregular cash flows (SIP contributions, lump sum investments, withdrawals, and the current portfolio value as a terminal cash flow). It is the primary performance KPI for goal and portfolio return analysis.

**How to compute:**
- Inflows (investments) are **negative** cash flows.
- Current portfolio value or redemptions are **positive** cash flows.
- Each cash flow is dated using `cash_flow.date` or `portfolio_holding.purchase_date`.
- Apply the XIRR formula iteratively (Newton-Raphson) to find the discount rate where NPV = 0.

**Guardrails — MANDATORY:**

| Condition | Action Required |
|---|---|
| Computed XIRR > **25%** | **FLAG as suspect.** Do NOT present as a valid result without investigation. |
| Computed XIRR > **25%** | Cross-check `portfolio_holding.purchase_date` — an incorrectly early purchase date inflates XIRR by extending the holding period artificially. |
| Computed XIRR > **25%** | Cross-check `portfolio_holding.cost` — an abnormally low purchase cost (data entry error) will inflate returns. |
| Computed XIRR > **25%** | Cross-check `cash_flow` records for duplicate entries, missing outflow records, or sign errors (inflows recorded as outflows). |
| Computed XIRR < **-50%** | Flag as suspect; likely missing recent valuation or stale `current_value`. |
| XIRR cannot be computed (no cash flows, all cash flows same-signed) | Return `null`; do not return an error-inflated number. |

> **Rule:** If XIRR exceeds 25%, always surface a data quality warning to the caller:
> *"XIRR of {value}% exceeds the 25% plausibility threshold. Verify purchase_date, cost, and cash_flow records for investor {investor_id} before using this figure."*

**Reasonable XIRR ranges by asset class:**

| Category | Typical XIRR Range | Plausibility Cap |
|---|---|---|
| Equity (Long Term) | 10%–18% | 25% |
| Debt | 5%–9% | 15% |
| Hybrid | 8%–14% | 20% |
| ELSS / Tax-saving | 10%–18% | 25% |

### 3.2 Returns Percentage (`returns_pct`)

**Definition:** Simple percentage return = `(current_value - cost) / cost × 100` stored in `portfolio_holding.returns_pct`.

**Guardrails:**

| Condition | Action |
|---|---|
| `returns_pct` > **200%** on a holding < 1 year old | Flag; verify `purchase_date` and `cost`. |
| `returns_pct` is negative and `current_value` > `cost` | Data inconsistency; flag and skip aggregation. |
| `cost` = 0 or NULL | Exclude from return calculations; flag as incomplete data. |

### 3.3 Portfolio Health Scores

All scores are on a **0–100 scale**. Thresholds:

| Score | Range | Interpretation |
|---|---|---|
| `goal_match_pct` | ≥ 80% | On track |
| `goal_match_pct` | 60%–79% | Needs attention |
| `goal_match_pct` | < 60% | At risk |
| `risk_score` | 0–40 | Low risk |
| `risk_score` | 41–70 | Moderate risk |
| `risk_score` | 71–100 | High risk |
| `liquidity_score` | ≥ 70 | Adequate liquidity |
| `diversification_score` | ≥ 70 | Well diversified |

### 3.4 Goal Progress

- `achievement_pct` = `(current_value / target_amount) × 100` on the `investment_goal` table.
- If `achievement_pct` < 50% and goal `target_date` is within 2 years → flag as **high-priority advisory case**.

### 3.5 Allocation Drift (Rebalancing)

- Drift = `|current_allocation_pct - target_allocation_pct|` in `rebalancing_action`.
- If drift > **10 percentage points** for any sector → trigger rebalancing recommendation.
- Conservative investors: any single sector allocation > **30%** → flag for compliance review.
- Aggressive investors: single-sector cap at **40%**; equity cap at **80%**.

---

## 4. Data Quality & Domain Sense Checks

Always apply these checks before computing KPIs or presenting results. Checks are grouped by category.

### 4.1 Basic Field Integrity

| # | Check | Fields | Action |
|---|---|---|---|
| B1 | `purchase_date` must not be in the future and must not predate 1990-01-01 | `portfolio_holding.purchase_date` | Flag holding; exclude from XIRR |
| B2 | `cost` must be > 0 and not NULL | `portfolio_holding.cost` | Exclude from return calculations; flag as incomplete |
| B3 | `current_value` must be ≥ 0 | `portfolio_holding.current_value` | Flag and exclude from aggregations |
| B4 | `investor_id` referential integrity | All tables | Orphaned records with no matching `investor_profile` must be flagged and excluded |
| B5 | Duplicate cash flow transactions | `cash_flow` (investor_id + date + amount + type) | Deduplicate before XIRR; flag duplicates for review |
| B6 | Cash flow sign convention | `cash_flow.amount` | Inflows (SIP, Lump Sum, Deposit) → negative for XIRR; Redemption/Withdrawal → positive |

---

### 4.2 Holdings Sense Checks

| # | Check | Condition | Action |
|---|---|---|---|
| H1 | **Abnormal return for holding age** | `returns_pct` > 200% on a holding with `purchase_date` < 1 year ago | Flag; verify `purchase_date` and `cost` for data entry errors |
| H2 | **Return/value inconsistency** | `returns_pct` is negative but `current_value` > `cost` | Data inconsistency; flag and skip aggregation |
| H3 | **Lock-in violation — ELSS** | `investment_type = 'ELSS'` and `(today - purchase_date) < 3 years` | Do not recommend redemption; surface lock-in warning |
| H4 | **Lock-in violation — PPF** | `investment_type = 'PPF'` and `(today - purchase_date) < 15 years` | Do not recommend redemption; surface lock-in warning |
| H5 | **Segment vs. investment type mismatch** | `segment` is 'Large Cap'/'Mid Cap'/'Small Cap' but `category = 'Debt'` | Market cap segments apply only to equity instruments; flag as a data classification error |
| H6 | **Stale valuation** | `current_value` not refreshed in > 30 days | Note caveat in any return or health analysis; do not treat as live market value |
| H7 | **Zero dividend on income-type holdings** | `investment_type` is a dividend-yielding type (e.g., dividend-plan Mutual Fund) with `dividends = 0` over > 2 years | Flag as suspect; may indicate data not being captured or wrong plan classification |
| H8 | **Cost vs. investment type minimum threshold** | `cost` < ₹500 for Mutual Fund / < ₹1,000 for Stock | Flag as potentially erroneous; most instruments have minimum investment thresholds |

---

### 4.3 Risk & Suitability Sense Checks

| # | Check | Condition | Action |
|---|---|---|---|
| R1 | **Conservative investor equity overweight** | `risk_tolerance = 'Conservative'` and total equity allocation > 40% | Flag as suitability breach; require advisory review |
| R2 | **Aggressive investor in near-100% debt** | `risk_tolerance = 'Aggressive'` and equity allocation < 20% | Flag as misalignment between stated profile and portfolio |
| R3 | **Single-sector concentration — Conservative** | Any `sector_allocation.allocation_pct` > 30% for a Conservative investor | Flag for compliance review |
| R4 | **Single-sector concentration — any profile** | Any `sector_allocation.allocation_pct` > 40% for Moderate / > 50% for Aggressive | Flag as concentration risk |
| R5 | **Sector allocations sum ≠ 100%** | Sum of all `sector_allocation.allocation_pct` per `investor_id` differs from 100% by > 1% | Flag as data integrity error; do not use for allocation analysis |
| R6 | **High-risk product for Conservative investor** | `category = 'Equity'` and `segment = 'Small Cap'` held by `risk_tolerance = 'Conservative'` investor | Flag as unsuitable product holding |

---

### 4.4 Goal & Progress Sense Checks

| # | Check | Condition | Action |
|---|---|---|---|
| G1 | **Overdue goal not achieved** | `investment_goal.target_date` < today and `achievement_pct` < 100% | Flag as overdue; highest-priority advisory case |
| G2 | **Near-deadline at-risk goal** | `achievement_pct` < 50% and `target_date` within 2 years | Flag as high-priority advisory case |
| G3 | **Emergency Fund in equity** | `investment_goal = 'Emergency Fund'` and equity allocation > 10% | Flag as unsuitable; Emergency Fund must be near-liquid (Debt/liquid funds) |
| G4 | **Orphaned goal — no cash flows** | `investment_goal` record exists but no `cash_flow` or `portfolio_holding` linked to this investor | Flag as inactive/unconfigured goal; may indicate onboarding data gap |
| G5 | **Goal target amount implausibly low** | `target_amount` < ₹10,000 for goals like Retirement / Home Purchase | Flag as likely data entry error (e.g., amount entered in lakhs instead of rupees) |
| G6 | **Retirement goal with very short horizon** | `investment_goal = 'Retirement Planning'` and `time_horizon` < 3 years | Cross-check investor age/profile; either time horizon or goal is misclassified |

---

### 4.5 Cash Flow Sense Checks

| # | Check | Condition | Action |
|---|---|---|---|
| C1 | **Withdrawal exceeds portfolio value** | Sum of `cash_flow.amount` (Withdrawal + Redemption) for a period > `portfolio_holding.current_value` | Flag as suspect; likely duplicate withdrawal records or stale portfolio valuation |
| C2 | **SIP gap — unexpected stop** | SIP transaction series for an investor stops for > 3 consecutive expected months with no Redemption recorded | Flag for advisor follow-up; may indicate payment failure or account issue |
| C3 | **Inconsistent SIP amounts** | SIP amounts for the same investor vary by > 50% across months without a plan-change event | Flag as possible data entry inconsistency |
| C4 | **Large lump sum without prior investor activity** | Lump Sum > ₹50 lakh for a Mass-segment investor | Flag for KYC/AML review; unusual for segment profile |
| C5 | **Inflow after redemption with no reinvestment record** | `cash_flow` shows Redemption followed immediately (< 7 days) by a Deposit of similar amount with no new holding created | Flag as possible double-entry or reclassification error |

---

### 4.6 Portfolio Health Sense Checks

| # | Check | Condition | Action |
|---|---|---|---|
| P1 | **Health score vs. portfolio composition mismatch** | `diversification_score` ≥ 70 but investor holds only 1–2 `sector` values in `portfolio_holding` | Flag as stale pre-computed score; recommend recomputing |
| P2 | **Risk score vs. profile mismatch** | `risk_score` < 30 (Low) for an Aggressive investor with > 70% equity | Flag as stale or miscalculated health score |
| P3 | **All health scores at maximum (100)** | `goal_match_pct`, `risk_score`, `liquidity_score`, `diversification_score` all = 100 | Flag as suspect default/seeded data; real portfolios rarely score perfectly across all dimensions |
| P4 | **Liquidity score high but all holdings are locked-in** | `liquidity_score` ≥ 70 but majority of holdings are ELSS/PPF within lock-in period | Score is inconsistent with actual liquidity; flag for recomputation |

---

### 4.7 Rebalancing Sense Checks

| # | Check | Condition | Action |
|---|---|---|---|
| RB1 | **Rebalancing recommendation contradicts risk profile** | `rebalancing_action.action = 'Buy'` for Small Cap equity targeting a Conservative investor | Flag as profile-incompatible recommendation |
| RB2 | **Buy recommendation on locked-in holding** | `action = 'Sell'` on ELSS/PPF holding within lock-in period | Replace with 'Hold'; surface lock-in constraint reason |
| RB3 | **Drift within tolerance flagged as action** | `|current_allocation_pct - target_allocation_pct|` < 2% but action ≠ 'Hold' | Flag as over-triggering; drift below 2% is within normal market fluctuation |
| RB4 | **Target allocation does not sum to 100%** | Sum of `target_allocation_pct` across all sectors per investor ≠ 100% (tolerance ±1%) | Flag as invalid rebalancing plan; do not execute |

---

## 5. Business Rules Summary

| Rule | Details |
|---|---|
| Suitability | Conservative investors must NOT hold > 40% equity. Validate against `risk_tolerance_context`. |
| Lock-in compliance | ELSS has 3-year lock-in; PPF has 2-year lock-in. Do not suggest early redemption. |
| Tax-advantaged instruments | ELSS, PPF are tax-saving under Section 80C. Flag when recommending alternatives. |
| Rebalancing trigger | Allocation drift > 10% from target triggers a rebalancing action. |
| Goal-based allocation | Retirement/Wealth Creation goals → higher equity for long horizons; Emergency Fund → near 100% liquid/debt. |
| XIRR plausibility cap | Any XIRR > 25% must trigger a data quality investigation (see Section 3.1). |

---

## 6. Aggregation Rules

Aggregation operations must respect the semantic meaning of each field. Applying the wrong aggregation to an identifier or categorical field produces meaningless or misleading results.

### 6.1 Fields That Must NEVER Be Aggregated

| Field | Table(s) | Why |
|---|---|---|
| `investor_id` | All tables | Opaque identifier — SUM/AVG/MIN/MAX are nonsensical; use only for GROUP BY, COUNT(DISTINCT), or JOIN |
| `holding_id` | `portfolio_holding` | Row identifier — no numeric meaning |
| `goal_id` | `investment_goal` | Row identifier — no numeric meaning |
| `cash_flow_id` | `cash_flow` | Row identifier — no numeric meaning |
| `rebalance_id` | `rebalancing_action` | Row identifier — no numeric meaning |
| `portfolio_health_id` | `portfolio_health` | Row identifier — no numeric meaning |
| `purchase_date` | `portfolio_holding` | Date field — AVG date is statistically meaningless in a portfolio context; use MIN (earliest purchase) or MAX (latest purchase) only where explicitly meaningful |
| `risk_tolerance` | `investor_profile` | Ordinal category — do not SUM or AVG; use COUNT/distribution only |
| `segment` | `investor_profile`, `portfolio_holding` | Category — no numeric meaning; use COUNT or GROUP BY |
| `investment_goal` | `investor_profile`, `investment_goal` | Category — no numeric meaning; use COUNT or GROUP BY |
| `action` | `rebalancing_action` | Enum (Buy/Sell/Hold) — no numeric meaning; use COUNT or GROUP BY |
| `investment_type` | `portfolio_holding` | Category — no numeric meaning |
| `sector` | `portfolio_holding`, `rebalancing_action` | Category — no numeric meaning |
| `category` | `portfolio_holding` | Category — no numeric meaning |
| `type` | `cash_flow` | Enum (SIP/Lump Sum/Deposit/etc.) — no numeric meaning |

### 6.2 Fields That Require Specific Aggregation Rules

| Field | Table | Allowed Aggregations | Prohibited / Notes |
|---|---|---|---|
| `cost` | `portfolio_holding` | SUM (total invested), AVG per holding | Do NOT SUM across investors to compare; normalise by `current_value` for meaningful cross-investor comparison |
| `current_value` | `portfolio_holding` | SUM (portfolio total), AVG per holding | SUM per `investor_id` = total portfolio value; cross-investor AVG only meaningful within the same segment |
| `returns_pct` | `portfolio_holding` | AVG (equal-weighted), weighted AVG by `cost` or `current_value` | Do NOT SUM; a simple AVG of `returns_pct` is only valid for equal-weighted analysis — always prefer value-weighted average |
| `dividends` | `portfolio_holding` | SUM per investor | Do NOT average across investors without normalising by portfolio size |
| `taxes_paid` | `portfolio_holding` | SUM per investor | Do NOT average across investors without normalising |
| `amount` | `cash_flow` | SUM (total flows); SUM per `type` | Always filter by `type` before summing — mixing inflows and outflows in a raw SUM is misleading |
| `goal_match_pct` | `portfolio_health` | AVG per investor (across goals); do NOT SUM | 100% is the ceiling; summing produces values > 100% which are meaningless |
| `risk_score` | `portfolio_health` | AVG across investors for cohort analysis | A single investor has one score; do not SUM |
| `liquidity_score` | `portfolio_health` | AVG across investors for cohort analysis | Same as `risk_score` |
| `diversification_score` | `portfolio_health` | AVG across investors for cohort analysis | Same as `risk_score` |
| `allocation_pct` | `sector_allocation` | SUM only within a single investor (must = 100%); AVG across investors for sector exposure analysis | Cross-investor SUM is invalid |
| `current_allocation_pct` | `rebalancing_action` | AVG across investors for cohort sector exposure | SUM across sectors for the same investor must = 100% |
| `time_horizon` | `investor_profile` | AVG (mean years) for cohort statistics | Meaningful only as a distribution; a single mean can mask bimodal distributions — always pair with MIN/MAX |

### 6.3 XIRR Aggregation Rules

- **Never pool** all investors' cash flows into a single XIRR calculation. XIRR is non-linear and pooling distorts results.
- **Correct approach:** Compute XIRR per `investor_id`, then report as a distribution: `MIN`, `P25`, `MEDIAN`, `P75`, `MAX`.
- **For cohort XIRR** (e.g., "XIRR for all Aggressive investors"): compute individual XIRRs, then present the distribution — do NOT average the XIRRs arithmetically unless explicitly requested and caveated.
- **Weighted average XIRR** by portfolio size is acceptable only when explicitly asked for a portfolio-size-weighted view.

### 6.4 COUNT Rules

| Use case | Correct aggregation |
|---|---|
| How many investors? | `COUNT(DISTINCT investor_id)` |
| How many holdings per investor? | `COUNT(holding_id) GROUP BY investor_id` |
| How many investors per risk profile? | `COUNT(DISTINCT investor_id) GROUP BY risk_tolerance` |
| How many SIP transactions? | `COUNT(cash_flow_id) WHERE type = 'SIP'` |
| Portfolio size distribution | `SUM(current_value) GROUP BY investor_id` — then histogram |

---

## 7. Response Guidelines

- Always cite the relevant **table name** and **field name** when referencing data.
- When a KPI is outside its plausibility range, **do not suppress it** — surface it with a data quality note.
- For multi-investor aggregations, compute XIRR individually per investor, then report distribution (min, median, max) — do NOT pool all cash flows into a single XIRR.
- When `current_value` is stale (last updated > 30 days ago based on context), note the caveat in your response.
- Amounts are in **INR (₹)**; do not convert to other currencies unless explicitly requested.
```

## Appendix B: Phase 0 business rules

Source: `baselines/phase0_business_rules.md`

````markdown
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
````
