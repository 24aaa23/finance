# NeoWealth Domain & Business Rules

Consolidated domain knowledge for the NeoWealth data warehouse, organised by subject. This document is the
single source of business rules and domain knowledge for querying the warehouse correctly: every rule, grain
hazard, join hazard, house convention and KPI definition needed to answer a question accurately is stated here,
once. A user asking a question supplies no evidence of their own, so nothing needed to answer correctly should
live outside this document.

Warehouse: **21 tables, 313 columns** — 7 `client_*` facts, 14 `dim_*` dimensions.
Engine: **DuckDB**. Currency: **INR ₹**. Market: **India**.

> **Session settings are mandatory.** Before any query:
> `SET default_null_order='nulls_last_on_asc_first_on_desc'; SET default_collation='nocase';`
> Without them, ordering and string matching will differ from what these rules describe.

---

## 1. Domain Overview

This platform manages HNI and retail wealth portfolios for an Indian wealth manager. Core operations:

- **Book and AUM reporting** — assets under management per client, family, line of business and tier.
- **Position and valuation tracking** — daily holdings snapshots and mark-to-market valuations.
- **Transaction and flow management** — purchases and redemptions, and net new money by period.
- **Realised gain and tax analysis** — matched buy–sell lots, holding periods and Indian capital gains.
- **Revenue attribution** — advisory fees, trail and upfront commission, brokerage, per client and employee.
- **Benchmark comparison** — fund and portfolio performance against market indices.
- **Data integrity auditing** — the schema declares no foreign keys, so orphans and breaks are audited.

The **fiscal year runs 1 April to 31 March**. FY2026 = 1 Apr 2025 → 31 Mar 2026 inclusive.
Market cap segments use Indian conventions and are stored on the company master as
`Large Cap` | `Mid Cap` | `Small Cap`.

---

## 2. Client and Product Classification

> **Three live columns are missing from `NEOWEALTH_DDL.sql`.** They exist in the database and are
> queryable, but a model that reads only the DDL will not know they are there:
> `dim_client_master.current_city`, `client_holdings.benchmark_return_1y` and
> `client_holdings.benchmark_return_3y`. Everything else matches — 313 columns across 21 tables.

### Client Tiers (`dim_client_master.tier`)
`Retail` | `Affluent` | `HNI` | `Ultra HNI` — free text, not a foreign key. "UHNI" means `Ultra HNI`.

### Client Cities (`dim_client_master.current_city`)
`Ahmedabad` (7) | `Goa` (6) | `Delhi` (6) | `Bengaluru` (6) | `Mumbai` (5) — a closed set of five,
never blank. Match case-insensitively; users type "goa" and "bengaluaru".

### Client Families (`dim_client_master.family_name`)
`Choudhary Family` | `Fernandes Family` | `Krishnan Family` | `Mehra Family` | `Patel Family`.
Denormalised onto the client row alongside `family_id`, so family questions need no join.

### Client Attributes
`occupation`: `Salaried` (12) | `Retired` (6) | `Business` (6) | `Professional` (5) | `Homemaker` (1).
`gender`: `Male` (16) | `Female` (14).
`kyc_status` is `KYC Compliant` on all 30 clients and `pep_status` is `Non-PEP` on all 30 — see §4.6.

### Employees (`dim_employee_profile`)
10 staff. `designation`: `VP` (4) | `AVP` (4) | `Senior VP` (2). `role_name` carries the job title
(`Relationship Manager`, `Senior RM`, `Team Lead`, `Branch Manager`, `Portfolio Advisor`,
`Wealth Advisor`). `department`: `Wealth Advisory` (5) | `Broking` (2) | `Family Office` | `NRI Advisory` |
`Asset Mgmt`. The hierarchy is **self-referencing on the business code, not the id**:
`reporting_manager_code` points at another profile's `code`. `resignation_date` is NULL on all ten,
so nobody has left. `client_revenue` carries **both** `emp_id` and `emp_code` as keys into this table.

### Lines of Business (`sub_lob_name`)
`Private Wealth` | `Family Office` | `NRI Advisory` | `Retail Broking` | `Institutional Broking` |
`Equity Schemes` | `Debt Schemes` — rolling up to three SBUs: `Wealth SBU`, `AMC SBU`, `Capital Markets SBU`.

### Account Types (`dim_client_account_map.account_type`)
`Individual` | `Joint` | `HUF` | `NRI` — this is the **account holder type**, not a discriminator of which
identifier column is populated. An account's kind is read from whichever identifier is actually
non-null on the row: `dp_id` → demat, `folio` → mutual-fund folio, `account_number`/`ifsc_code` → bank.

### Product Types (`dim_product_unified_cat.product_type`)
`Mutual Funds` | `Direct Equity` | `Bonds` | `Fixed Deposits` | `AIF` | `PMS` | `REITs` | `InvITs`

### Asset Classes (`asset_class`)
`Equity` | `Fixed Income` | `Alternatives` | `Hybrid`

- `sub_asset_class` is the finer SEBI level, but is **NULL on 28 of 98 products** — every AIF, REIT,
  InvIT, PMS and fixed deposit.
- `category` holds the regulator's scheme classification (`Bank FD`, `Category II/III`, `Discretionary`, `REIT`).
- **"Allocation category" = `COALESCE(sub_asset_class, category)`.** `sub_asset_class` alone leaves a
  large unnamed NULL bucket.

### Sectors (`dim_cmot_company_mstr.sector_name`)
IT - Software | Banks - Private | Banks - Public | Financial Services | Consumer Goods | Automobiles |
Pharma | Power | Oil & Gas | Telecom | Defence | Electronics | Infrastructure | Diversified

### Credit Ratings (`dim_product_credit_rtng.credit_rating`)
`AAA` | `AA+` | `AA` | `AA-` — stored **bare**, with `credit_rating_agency = 'CRISIL'` on every row.

### Fund House and Scheme Detail
There is **no `dim_amc` table** — the fund house is denormalised onto `dim_mf_fund_complete` as
`amc_id`, `amc_name` and `amc_code`, and onto the catalogue as `amc_display_name`.
`category` holds SEBI's mandated scheme classification; `sub_category` is the finer split
(`Large Cap`, `Mid Cap`, `Sectoral`, `Flexi Cap`, `ELSS`, `Index`, `Focused`, `Value`, `Contra`,
`Balanced Advantage`, `FoF Overseas`, `Small Cap`), populated on all 30 funds.
`dim_product_unified_cat.is_etf` marks exchange-traded products — true on **1 of 98**.

### Trade Economics (`client_transactions`)
`amount` is the rupee consideration, `units` the quantity transacted and `nav_price` the per-unit
execution price. They are three different things; `amount` is the one that sums to turnover.
`amount` and `units` are always stored **positive** — direction is carried only by `transaction_type`.
**Net traded flow** = `SUM(CASE WHEN transaction_type='Redemption' THEN -amount ELSE amount END)`.
**Turnover** = `SUM(amount)` over both directions, not netted.

### Transaction and Revenue Types
`transaction_type`: `Purchase` | `Redemption`.
`revenue_type`: `Advisory Fee` | `Trail Commission` | `Upfront Commission` | `Brokerage` | `Transaction Fee`.

---

## 3. KPI Definitions and Validation Rules

### 3.1 XIRR (Extended Internal Rate of Return)

**Definition:** XIRR is the annualised return computed from irregular, dated cash flows — SIP
contributions, lump sums, withdrawals, and the closing portfolio value as a terminal cash flow. It is
the primary performance KPI for goal and portfolio return analysis in wealth management.

**How it would be computed:**
- Inflows (investments) are **negative** cash flows; redemptions and the closing value are **positive**.
- Every cash flow must carry its own date.
- Solve iteratively (Newton-Raphson) for the discount rate at which NPV = 0.

> **STATUS IN THIS WAREHOUSE: NOT COMPUTABLE. Decline; do not approximate.**

| Requirement | Available here? |
|---|---|
| Dated external cash flows per position | **No** — `client_transactions` records purchases and redemptions but carries no opening balance and no valuation cash flow |
| Opening and closing valuation for the window | **No** — `client_valuations` covers 6 dates and does not align to a flow series |
| Position-level flow granularity | **No** — `client_net_new_money` is aggregated to a product bucket per period |
| Iterative solver | **No** — DuckDB has no XIRR function and no root-finder callable from SQL |

**Required behaviour:** return `null` with the reason. Never substitute a simple or annualised return
and label it XIRR — `(current_value − invested_value) / invested_value` is a **holding-period return**,
not a money-weighted one, and the two diverge sharply whenever contributions are irregular.
Say: *"XIRR cannot be computed from this warehouse: it needs a dated cash-flow series with opening and
closing valuations, which is not recorded. A holding-period return is available instead if useful."*

**Guardrails to apply if a cash-flow series is ever added:**

| Condition | Action Required |
|---|---|
| Computed XIRR > **25%** | **FLAG as suspect.** Cross-check purchase dates (an early date inflates XIRR), cost (an abnormally low cost inflates returns), and flows for duplicates, missing outflows or sign errors. |
| Computed XIRR < **-50%** | Flag as suspect; likely a missing recent valuation or a stale closing value. |
| No cash flows, or all flows same-signed | Return `null`; never return an error-inflated number. |

**Plausibility ranges by asset class:** Equity (long term) 10–18%, cap 25% · Fixed Income 5–9%, cap
15% · Hybrid 8–14%, cap 20%.

### 3.2 AUM (Assets Under Management)

- `client_aum.aum_value` is the client-month total. **`aum_equity`, `aum_fixed_income` and
  `aum_alternatives` decompose that same total — they do not add to it.**
- Grained **per client per line of business per month**, so one client has several rows in a month.
  A client total sums across their LOBs **and** pins to one `as_on_date`.
- Snapshots are stamped on the **first day of the month** they describe, so `as_on_date` is already a
  month key and needs no truncation.
- It is the **only per-client value series** in the schema — every trend, month-on-month and drawdown
  question is answered from it.

### 3.3 Unrealised Gain

- **Derive**: `current_value − invested_value`; percent is `100 × (current_value − invested_value) / invested_value`.
- `client_holdings.unrealized_gain` and `unrealized_gain_pct` are typed **VARCHAR** and must never be summed.
- `client_holdings` carries **no acquisition date** for open positions, so holding period is unavailable
  for unrealised positions.

### 3.4 Realised Gain and Capital Gains Tax

- `client_realized_gain` holds one row per matched **buy–sell lot**, with both legs, `holding_period_days`
  and a correctly typed `realized_gain` that **can** be summed.
- A gain is booked in the fiscal year of its **`sell_date`**.
- **Long-term** for listed equity is **more than 365 days**; 365 or fewer is short-term.
- **LTCG on listed equity is taxed at 12.5%**, after the **first ₹125,000 of long-term gain per client
  per financial year is exempt**. The exemption is claimed **once per client across all lots**, never per lot.
- A client at or below the exemption owes nothing; a client with a **negative** long-term total owes
  nothing rather than earning a credit.
- **"Equity" for tax means Direct Equity *and* equity-oriented funds** — a fund whose
  `dim_mf_fund_complete.asset_alloc_equity_net` is at least **65** (§5). Both run under the same
  holding-period threshold, the same 12.5% rate and **one shared exemption per client per financial
  year**; a client never gets a second ₹125,000 for their fund lots. All 23 realised fund lots in this
  delivery sit in funds between 90.7% and 99.2% net equity, so every one of them qualifies.
- **Short-term gain on the same instruments is taxed at 20%**, with **no exemption and no
  indexation**. Short-term is `holding_period_days <= 365`.
- **Tax falls only on a positive gain.** A lot closed at a loss attracts none and is carried at its
  full negative amount, so any book-level figure is net of losses.
- **"Post-tax", "net of tax" and "what we kept" mean gain − tax**, with the exemption applied **once
  per client** exactly as above — never lot by lot. A lot-level tax cannot be netted against the
  per-client exemption afterwards.
- **A question scoped to a subset of instruments** ("post-tax on fund exits") still nets the
  exemption against the client's **whole** long-term position for the year, because the allowance is
  a per-person one and cannot be claimed twice. Attribute the resulting long-term tax to the subset
  **in proportion to its share of the client's long-term gain**; short-term tax carries no exemption
  and attributes directly to the lot that bears it.

### 3.5 Net New Money

- **Derive**: `inflow − outflow`. `client_net_new_money.net_flow` is typed **VARCHAR** and must not be summed.
- It isolates asset gathering from market movement, so unlike AUM growth it **can be negative**, shares
  can exceed 100%, and a tier's share can be negative when tiers offset.

### 3.6 Drawdown

- Peak-to-trough decline computed from the **monthly AUM level using a running maximum**.
- If no client's AUM has declined over the period in view, every drawdown is correctly **0** — that is
  a valid answer, not a bug.

### 3.7 Allocation and Portfolio Weight

- A position's weight is its share of **that client's own** portfolio, so the denominator is a window
  sum over the client's pinned holdings and must be computed **before** any top-N cut.
- Allocation percentages are read from holdings joined to the catalogue, or from the three `client_aum`
  split columns — the two routes have different dates and cannot be equi-joined.
- **Which route to use.** A question about a **portfolio, holdings, investments or positions** takes
  the holdings ⋈ catalogue route — it is the only one that carries `Hybrid` and that reaches product
  type. The `client_aum` split columns are used when the question names **AUM** or a month-end AUM
  snapshot, for the 60/40 house-model drift (§5), and for an allocation asked of a **family, tier or
  line of business**, since those cohorts are measured by AUM (§6.5).
  The two totals agree (₹2,348.18M) but the percentages do not, because the two sources classify the
  same products differently — book-wide, holdings give Fixed Income 43.01 / Equity 38.13 /
  Alternatives 18.62 / Hybrid 0.24 %, while the AUM split gives Equity 44.55 / Fixed Income 26.69 /
  Alternatives 28.76 %. Name the source you used; it is not optional here.

### 3.8 Benchmark Comparison

- `dim_cmot_index_prices` holds a daily OHLC series per index, with **no volume** (an index has none)
  and **no index identifier anywhere in the schema**. The only link is the name.
- The two sides **spell it differently**: the product side (`benchmark_name`, `benchmark`) names the
  **total-return** series with a trailing `' TRI'`; the price table names the **price** series without it.
  A plain equality join **matches nothing and fails silently**:

  ```sql
  JOIN dim_cmot_index_prices i
    ON i.index_name = REGEXP_REPLACE(f.benchmark_name, ' TRI$', '')
  ```

- **A second, non-fragile route exists.** `client_holdings.benchmark_return_1y` and
  `benchmark_return_3y` carry a pre-joined benchmark return on the position row itself — populated on
  **375 of 505** positions, covering every product type except **Bonds (0 of 66)** and
  **Fixed Deposits (0 of 51)**. Neither column is in `NEOWEALTH_DDL.sql`. Prefer these when the
  question is about a position's performance against its benchmark; use the name join only when the
  index level itself is wanted.

- **Which column is "the benchmark".** `dim_mf_fund_complete.benchmark_name` is the **fund's own**
  benchmark and is specific (16 distinct values — `Nifty 100 TRI`, `Nifty IT TRI` …).
  `dim_product_unified_cat.benchmark`, copied onto `client_holdings.benchmark_name`, is the **coarse
  product-level** benchmark (4 distinct values). They differ for **19 of 30 funds**. A question about
  **funds** reads the fund master; a question about **products or positions** reads the catalogue or
  holdings column. The `' TRI'` strip applies to both.

- **A TRI benchmark does count as held when its stripped name matches an index.** After stripping,
  4 of the 5 held indices are named as benchmarks — `Nifty 50`, `Nifty 500`, `Nifty Midcap 150` and
  `Nifty Smallcap 250` — covering **15 funds**; `Nifty 10yr G-sec` is named by no fund. "Do we hold
  levels for that benchmark?" is therefore **yes** for those, subject to the dividend-yield caveat
  below. Do not read the TRI/price distinction as meaning nothing is held.

- **No spelling is mapped beyond the `' TRI'` strip.** 28 catalogue products name
  `Nifty 10 yr Benchmark G-Sec Index` while the held series is spelled `Nifty 10yr G-sec`. They are
  almost certainly the same index, but the strip rule does not reach it and **no further name mapping
  is sanctioned** — report it as unmatched and state the spelling as a data-quality caveat.

- Caveat to state in any published figure: the fund is benchmarked to a **total-return** index but only
  the **price** series exists here, so the comparison understates the benchmark by its dividend yield.

### 3.9 Revenue

- `client_revenue` is grained **per client per employee per `revenue_date` per `revenue_type`**.
- It attributes income to the **booking employee** via `emp_id` — a different relationship from either
  the servicing or the acquiring banker.

### 3.10 House Terminology and Derived Measures

Terms an RM uses that are not column names. Each is defined once here; a question that uses the term
needs nothing beyond this section.

| Term | Definition |
|---|---|
| **Held away** | Assets the firm advises on but does not custody, flagged by `client_holdings.is_held_away`. The flag is nullable in the schema and fully populated here (72 held-away of 505 positions). |
| **Fee-billable / billable book** | Market value **excluding** held-away positions: `SUM(current_value)` on the pinned date where `COALESCE(is_held_away, FALSE) = FALSE`. Held-away assets still count in a total-wealth view. |
| **Accrued interest** | Income earned but not yet paid, on `client_holdings.accrued_interest`. It accrues only on coupon-paying instruments, so debt positions carry it and equity positions do not. "Carries accrued interest" means `> 0`, not merely non-null. |
| **Approved product** | A product carrying at least one **live** segment mapping in `dim_product_segment_map`. |
| **Turnover** | `SUM(client_transactions.amount)` over the window, both directions counted — not netted. |
| **Revenue yield** | Revenue booked over a period ÷ the assets that produced it, quoted in **basis points** (one bp = one hundredth of a percentage point, so multiply the ratio by 10,000). |
| **Organic growth** | Net new money over the period ÷ the assets the period **opened** with, as a percentage. It isolates gathering from market movement, so it can exceed 100% or go negative. |
| **Dormant client** | No transaction executed on their behalf in the trailing twelve months. Read from presence in the trade ledger — there is no dormancy flag. |
| **First trade** | The client's earliest `transaction_date` across **all time**, not inside a fiscal window. |
| **New high** | A benchmark prints a new high on a date when its close exceeds **every** close it posted earlier inside the window. The first date in a window can never be one. |
| **Tenure** | Measured from `dim_employee_profile.doj` to the reference date in completed years. Joining dates run 2010-11-05 to 2019-05-18. |
| **Concentration** | A position's share of its **own client's** book (§3.7). "Most concentrated client" means the client whose single largest position is the biggest share of their own portfolio. |
| **EUIN** | Employee Unique Identification Number — SEBI/AMFI require it of anyone advising on or distributing mutual funds. Held on `dim_employee_profile`; nullable. |
| **Underwater** | A position worth less than it cost: `current_value < invested_value` on the pinned date. |
| **Account identifiers** | `dim_client_account_map.account_type` is the discriminator for which identifier on the row is populated — a **folio number** for mutual fund accounts, a **DP id** for demat, an **account number** for bank. Three identifier systems coexist in one table; none is a client key. |
| **Fund NAV key** | `dim_mf_nav_history` is keyed by `mstar_id`, the Morningstar identifier — it carries no `product_id`. Reach it from the fund master, not the catalogue. |
| **Percentiles of a client measure** | Computed over the distribution of **client totals** — one observation per client after summing their LOB rows — never over the raw fact rows. |
| **Debt book / fixed-income book** | `asset_class = 'Fixed Income'` — on the pinned date, 66 **bond**, 51 **fixed-deposit** and 21 **debt mutual-fund** positions. Coupon, annual-interest and accrual questions cover the **coupon-bearing** part, bonds and FDs: an FD carries an interest rate on the catalogue (6.5%–8.5%) and accrues exactly as a coupon does, while a debt fund carries no rate and drops out on its own. Say **"bonds"** or **"rated debt"** to mean bonds alone, and note that any measure **grouped or filtered by a rating attribute** (rating, rating agency) is rated debt by construction, because no fixed deposit carries one. Reach the rate from `dim_product_unified_cat` on `product_id` — `dim_product_credit_rtng` holds bonds only, and all 51 FD positions carry a **NULL `isin`**, so any ISIN join silently loses them. |
| **Coupon / interest principal** | The base an interest rate is applied to: `quantity × face_value` for a **bond**, and `invested_value` for a **fixed deposit**, whose `face_value` is NULL and whose `quantity` is 1. Write it as `COALESCE(quantity × face_value, invested_value)` so one expression covers the debt book. Daily accrual is that figure × rate ÷ 365. |
| **Equity holdings / stocks / shares** | `product_type = 'Direct Equity'`. **"Equity exposure" or "the Equity asset class"** is the wider `asset_class = 'Equity'`, which also holds equity mutual funds and PMS. **Never identify equity by an `INE` ISIN prefix** — `INE` also covers corporate bonds, REITs and InvITs (§5), so the prefix is wrong under either reading. Capital-gains tax has its own scope; see §3.4. |
| **"This year" / "year to date"** | The **fiscal** year to date — from the most recent 1 April on or before the anchor date (C1). The house convention is Indian; plain "this year" is never the calendar year. |
| **"Last year"** | The **previous fiscal year**, not a trailing twelve months. "Trailing twelve months" is said explicitly when it is meant, as it is for a **dormant client** above. |
| **AMC / fund house** | A **mutual-fund** house, on `dim_mf_fund_complete` (§2). `dim_product_unified_cat.amc_display_name` also names **PMS and AIF managers** (ASK, Avendus, Motilal Oswal, Nippon India AIF); those are not AMCs and stay out of "which AMCs" questions unless the question names PMS or AIF. |

---

## 4. Data Quality & Domain Sense Checks

Apply before computing any KPI. Nearly every check exists because ignoring it produces a query that
runs, returns rows, and is quietly wrong.

### 4.1 Grain Checks

| # | Check | Condition | Action |
|---|---|---|---|
| G1 | **AUM is per line of business** | Aggregating `client_aum` by client | Sum across the client's LOBs first; counting rows counts LOB rows, not clients |
| G2 | **AUM retains every month** | Any aggregate over `client_aum` | Pin to a single `as_on_date` unless the history *is* the answer |
| G3 | **Duplicate position rows** | Same client + instrument on one date via several accounts | Collapse positions before reading them as one holding |
| G4 | **Event tables must not be pinned** | Filtering `client_transactions`, `client_realized_gain`, `client_revenue` or `client_net_new_money` to a "latest" date | They have no `as_on_date`; pinning silently drops history |
| G5 | **Snapshot tables must be pinned** | "Current" holdings or valuations | Pin `client_holdings` / `client_valuations` to `MAX(date)` |
| G6 | **Flattened hierarchy fan-out** | Joining `dim_lob_hierarchy` (one row per sub-line) to a fact | Reduce to `DISTINCT` first, or every figure is multiplied |
| G7 | **Account bridge fan-out** | Filtering a fact through `dim_client_account_map` (one row per account) | Reduce to distinct client ids first |
| G8 | **Returns history is a snapshot series** | An undated "1-year / 3-year return" from `dim_mf_returns_history` | 12 monthly snapshots per fund. A fund's *current* return is the row on the latest `return_date`; average across snapshots only where the question asks for the history |
| G9 | **`client_revenue` has no unique grain** | Aggregating revenue | Always `SUM(revenue_amount)` within whatever grouping is used; do not assume one row per client/employee/date/type |

### 4.2 Key and Join Checks

| # | Check | Condition | Action |
|---|---|---|---|
| K1 | **No declared foreign keys** | Any join | Referential integrity is an assumption; orphans are possible and are audited, not assumed away |
| K2 | **`co_code` is overloaded** | Joining `dim_cmot_index_prices` to the company master on `co_code` | It means a **company** in three tables and an **index** in the index table. The join compiles, returns rows, and is meaningless — join on `index_name` |
| K3 | **Never join `id` across tables** | `a.id = b.id` | Per-table sequences with disjoint ranges. Same for `source_table` and `row_hash` |
| K4 | **Join clients on `client_id`** | Joining on PAN | PAN is nullable, user-entered, correctable and sensitive |
| K5 | **Join products on `product_id`** | Reaching market data | Go catalogue-first, then to market data on `isin` |
| K6 | **No primary key declared** | `GROUP BY` a name | Carry the id alongside the name; names are not guaranteed unique |
| K7 | **Two sector columns disagree** | Sector analysis | `dim_product_unified_cat.sector` and `dim_cmot_company_mstr.sector_name` can differ; the company master is the listed-equity authority. It holds **no REITs or InvITs**, so read their sector (`Real Estate`, `Infrastructure`) from the catalogue — a sector question includes them rather than dropping them |
| K8 | **Benchmark name never equals index name** | Joining a benchmark to a price series | Strip the `' TRI'` suffix (§3.8) |
| K9 | **Credit-rating table: join on `scheme_master_id`, not `isin`** | Reaching `dim_product_credit_rtng` from the catalogue | 3 rated instruments carry the literal text `'N/A'` for `isin`, so an `isin` join misses them; `scheme_master_id` matches every row |
| K10 | **`client_holdings.wsw_account_code` → `dim_client_account_map` is unreliable** | Deriving a client's identity or account details from a holding | About a quarter of holdings have no matching account row, and roughly half of the matches that do exist point to an account of a **different** client. Never derive client identity through this join — use `client_id` directly for anything client-level |
| K11 | **`client_aum.as_on_date` is month-start; `client_holdings.as_on_date` is a daily date** | Joining or comparing dates across the two tables | Align explicitly with `DATE_TRUNC('month', ...)` before comparing; an equi-join on the raw dates returns nothing or the wrong rows |

### 4.3 Numeric Typing Checks

| # | Field | Stored type | Action |
|---|---|---|---|
| T1 | `client_holdings.unrealized_gain`, `unrealized_gain_pct` | VARCHAR | Derive from `current_value` and `invested_value` |
| T2 | `client_net_new_money.net_flow` | VARCHAR | Derive as `inflow − outflow` |
| T3 | `client_valuations.unrealized_pnl` | VARCHAR | Derive as `market_value − cost_value` |
| T4 | `dim_mf_returns_history.return_1m/3m/6m/1y` | VARCHAR | Cast before arithmetic (`return_3y/5y/10y` are `real`) |
| T5 | `client_holdings.quantity` | single-precision `real` | A recomputed `quantity × price` differs from the stored value; tolerate ~₹1 before calling it a break |
| T6 | `dim_product_credit_rtng.interest_rate` | percent | `7.25` means 7.25%, so "coupon above 7%" is `interest_rate > 7` |
| T7 | `dim_product_credit_rtng.brick_rating` | unusable legacy | All NULL; never select |
| T8 | `dim_mf_fund_complete.asset_alloc_*` | percent, rounded | The sleeves need not total exactly 100. Tolerate **1 percentage point** before calling it a break, as T5 tolerates ~₹1. State the tolerance you used (§7) |
| T9 | `dim_product_unified_cat.is_listed` | VARCHAR, not boolean | Values are `'Listed'` / `'Unlisted'`; filter on the text value, never with a bare `WHERE is_listed` |
| T10 | `dim_mf_returns_history.return_*` | stored, not derived | Stored return values do not reconcile to a NAV-derived return. Always use the stored column; never recompute a return from NAV history and substitute it |

### 4.4 Scope and Status Checks

| # | Check | Condition | Action |
|---|---|---|---|
| S1 | **Status flags are nullable** | `is_active` / `is_deleted` | A client or product is in scope unless `is_deleted` is explicitly true or `is_active` explicitly false — null means never populated |
| S2 | **Population vs named lookup** | "How many clients…" vs "What is Ram Krishnan's AUM?" | Population questions apply the status filter; naming a client presupposes existence and applies none |
| S3 | **Case-insensitive matching** | City, name and rating filters | Users type "goa", "bengaluaru" |
| S4 | **Servicing ≠ acquiring banker** | "Who is the RM for…" | `servicing_banker_name` manages the client now; `acquiring_banker_name` brought them in. Default to servicing. "RM", "banker" and "relationship manager" are one role |
| S5 | **Names are denormalised** | Needing a banker's or family's name | Already on the client row — no join to the employee register needed |
| S6 | **Closed rating vocabulary** | "AA+ or higher" | Enumerate `('AAA','AA+')`; do not compare rating strings ordinally |
| S7 | **Near-miss client names** | A typed name that matches no client exactly | Match **every token** of the typed name against client names, case-insensitively and as a substring, and resolve only where **exactly one** client satisfies all tokens: `Rama Krishna` → `Ram Krishnan`. If any token matches no client, return **none matched** — `Lakshmi Narayanan` does **not** resolve to `Lakshmi Krishnan`, because no client is a `Narayanan`. Never fall back to the nearest surname |

### 4.5 Coverage Checks

| # | Check | Condition | Action |
|---|---|---|---|
| C1 | **No calendar dimension** | "Last 6 months", "this year", "recently" | Anchor to a date read from the data (`MAX(date)`), never the wall clock. The anchor is the `MAX` of **the table that answers the question**, not one delivery-wide date: transactions end **2026-04-21**, AUM and net new money **2026-05-01**, holdings, valuations and NAV **2026-05-19**. "No purchases last month" is measured from the transaction ledger's own end |
| C2 | **Series are not padded** | "Every month", "consecutive months" | An absent month is indistinguishable from an inactive one; answer over months present |
| C3 | **Holdings have one date** | "Holdings over the last N months" | `client_holdings` covers 2026-05-19 only |
| C4 | **No equity price series** | Day-over-day equity moves, BSE closes | `dim_equity_price_latest` is a single-date NSE-only snapshot |
| C5 | **Index prices do not overlap AUM** | Portfolio-vs-index over a shared window | Index prices cover 12 days in May 2026; AUM covers Dec 2025 – May 2026 |
| C6 | **Flow product keys are buckets** | Joining `client_net_new_money` to the catalogue | `product_id` holds `AGG_*` labels; read the bucket from `product_type` on the same row |
| C7 | **Segment map is equity-only** | Segment questions about funds | `dim_product_segment_map` covers Direct Equity only |
| C8 | **`dim_master_enums` is unusable** | Resolving a label | Every payload column on this table is NULL; `tier` and similar coded columns already store the label directly on their own table, so read it from there instead |
| C9 | **A table's first date is a loading date** | "New clients", "funds launched in FY2026", "since they came on the book" | All 30 clients' first AUM month is 2025-12-01 and all 30 funds' first NAV is 2025-05-19 **because that is where the data starts** — real first trades run 2014-10-22 to 2024-02-03 and inceptions 2013–2021. Never infer a start date from the first row of a window-limited table: use **first trade** (§3.10) or `dim_mf_fund_complete.inception_date`, or say it cannot be determined |
| C10 | **Realised-gain lots are independent of the transaction ledger** | Reconciling or rebuilding realised gains | No lot in `client_realized_gain` matches a trade in `client_transactions`; never try to derive one from the other |

### 4.6 Degenerate Cohort Checks

A comparison whose contrast cohort is empty returns one row, and that one row is the **correct**
answer. Do not relax the filter to manufacture the missing side, and do not read a single row as a
sign the grouping was wrong. Every column below holds exactly **one** value across the delivery:

| Column | Sole value | Coverage |
|---|---|---|
| `dim_client_master.kyc_status` | `KYC Compliant` | 30 / 30 |
| `dim_client_master.pep_status` | `Non-PEP` | 30 / 30 |
| `dim_client_master.group_name` | `Group 900` | 30 / 30 |
| `dim_product_credit_rtng.credit_rating_agency` | `CRISIL` | 15 / 15 |
| `dim_equity_price_latest.exchange` | `NSE` | 25 / 25 |
| `dim_cmot_company_mstr.bse_group` | `A` | 25 / 25 |
| `dim_mf_nav_history.nav_currency` | `INR` | 7,860 / 7,860 |
| `dim_mf_fund_complete.is_obsolete` | `false` | 30 / 30 |
| `dim_employee_profile.reporting_manager_code` | `EMP5001` | 9 of 10 (1 null) |

Three more are degenerate only after a join or a derivation:

- **Plan type.** All 30 funds are **Direct** plans — there is no `Regular` cohort, and no plan-type
  column either; the plan is read from `'Direct'` in the fund name.
- **Realised-gain asset class.** All 65 closed lots are on **Equity** products.
- **Scope flags.** Even where every current `is_active` is `true` and every `is_deleted` is `false`
  across the tables that carry them, so the §4.4 S1 scope filter currently removes no rows, write it
  anyway — it is correct, and the data could change.

---

## 5. Business Rules Summary

| Rule | Details |
|---|---|
| Fiscal year | 1 April – 31 March. FY2026 = 1 Apr 2025 → 31 Mar 2026. |
| Long-term equity | More than 365 days held. Taxed at 12.5% after a ₹125,000 per-client annual exemption. Covers Direct Equity **and** equity-oriented funds under **one shared** exemption per client per FY (§3.4). |
| Short-term equity | 365 days or fewer, on the same instruments. Taxed at **20%** — no exemption, no indexation (§3.4). |
| Senior citizen | Age 60, attained on the sixtieth birthday; an anniversary on the reference date qualifies. |
| Equity-oriented fund | At least 65% of the portfolio in equity, net of derivative and short positions. |
| Fund identity | `dim_mf_fund_complete` is one row per scheme–plan–option. A scheme named without its plan resolves to several rows with **different expense ratios** — Direct is materially cheaper than Regular. |
| ISIN prefixes | `INF` = fund units; `INE` = equity and corporate debt. |
| Client scope | In scope unless explicitly deleted or inactive; nulls count as in scope. |
| Benchmark join | Strip `' TRI'` before matching an index name. |
| House model portfolio | The house target is **60% equity / 40% everything else**. "Drift from the house target" is `ABS(equity share − 60)` in percentage points, measured on the pinned `client_aum` month. |
| Advisory fee schedule | A **marginal** slab: **0.75%** on the first **₹50,000,000** of a client's assets and **0.50%** on the excess. A client above the break pays the higher rate on the first ₹5 crore only. Bill per client, then sum — never on the book total. |
| Indian number words | `1 lakh` = 100,000 and `1 crore` = 10,000,000, so "50 crore" = 500,000,000. Users write amounts this way; the data is in plain rupees. |
| Sector coverage | `dim_product_unified_cat.sector` is populated on **30 of 98 products** — Direct Equity (25), REITs (3), InvITs (2). It is **NULL for all 30 mutual funds** and for every bond, fixed deposit, AIF and PMS, so about **80% of book value carries no sector at all**; a fund has no single sector. See K7 for which sector column wins, and §6.5 for the denominator. |
| Fund returns are net of fees | `dim_mf_returns_history.return_*` are published NAV-based returns and are **already net of the expense ratio**, as published Indian fund returns are. A "net of fees" question is answered by the stored return as it stands — **never subtract `expense_ratio` from it again**, which charges the fee twice. |
| XIRR | **Not computable from this warehouse.** Decline with the reason; never substitute a holding-period return. |

---

## 6. Aggregation Rules

### 6.1 Fields That Must NEVER Be Aggregated

| Field | Why |
|---|---|
| `id` on any table | Per-table sequence with a disjoint range — no numeric meaning; never SUM, AVG or join on it |
| `client_id`, `product_id`, `emp_id`, `lob_id`, `segment_id` | Opaque identifiers — use only for `GROUP BY`, `COUNT(DISTINCT)` or `JOIN` |
| `pan_number`, `client_pan`, `isin`, `co_code`, `mstar_id` | Identifiers, not measures |
| `tier`, `product_type`, `asset_class`, `sub_asset_class`, `category`, `sector_name`, `mcap_type` | Categories — `COUNT` or `GROUP BY` only |
| `transaction_type`, `revenue_type`, `account_type`, `credit_rating` | Enums — `COUNT` or `GROUP BY` only |
| `as_on_date`, `valuation_date`, `transaction_date`, `sell_date` | Dates — `MIN`/`MAX` only where meaningful; an average date is not |
| `row_hash`, `source_table` | Change-detection and lineage — never aggregated or joined |

### 6.2 Fields That Require Specific Aggregation Rules

| Field | Allowed | Notes |
|---|---|---|
| `client_aum.aum_value` | `SUM` per client-month | **Must** sum across the client's LOBs and pin to one `as_on_date` |
| `aum_equity` / `aum_fixed_income` / `aum_alternatives` | `SUM` | These **decompose** `aum_value`; adding them to it double-counts |
| `client_holdings.current_value`, `invested_value` | `SUM` per client | Collapse duplicate account rows first |
| `unrealized_gain` | Derived only | VARCHAR as stored; see T1 |
| `client_realized_gain.realized_gain` | `SUM` per client, per instrument, per FY | Correctly typed; a gain belongs to the FY of its `sell_date` |
| `inflow` / `outflow` | `SUM` per client-period | Never mix the two in one raw `SUM`; net is `inflow − outflow` |
| `revenue_amount` | `SUM` per client, employee or `revenue_type` | Always group by `revenue_type` before comparing fee kinds |
| percentage columns (`allocation_pct`, `pct_of_portfolio`) | `SUM` within one client (= 100%); `AVG` across clients | Cross-client `SUM` is invalid |
| `dim_mf_returns_history.return_*` | `AVG` across funds | Cast first (T4); prefer value-weighting when the question implies a book view. Pin to the latest `return_date` unless the history is the answer (G8). Already net of the expense ratio (§5) — do not deduct it again |
| `expense_ratio` | `AVG` | Plan-and-option grain means a scheme appears several times with different values |

### 6.3 XIRR Aggregation Rules

Not applicable here — XIRR is not computable (§3.1). If a cash-flow series is added:

- **Never pool** all clients' cash flows into a single XIRR. XIRR is non-linear and pooling distorts it.
- Compute XIRR **per client**, then report the distribution: `MIN`, `P25`, `MEDIAN`, `P75`, `MAX`.
- For a cohort ("XIRR for all Ultra HNI clients"), present the distribution — do **not** average the
  individual XIRRs arithmetically unless explicitly asked, and caveat it when you do.
- Portfolio-size-weighted average XIRR is acceptable **only** when explicitly requested.

### 6.4 COUNT Rules

| Use case | Correct aggregation |
|---|---|
| How many clients? | `COUNT(DISTINCT client_id)` with the status filter |
| How many clients hold X? | `COUNT(DISTINCT h.client_id)` — a client holding several matching instruments counts once |
| How many positions? | `COUNT(*)` on the pinned `client_holdings` date |
| How many clients per tier? | `COUNT(DISTINCT id) GROUP BY tier` |
| How many transactions? | `COUNT(*)` on `client_transactions`, never date-pinned |
| Book AUM distribution | `SUM(aum_value) GROUP BY client_id` on one `as_on_date`, then histogram |

### 6.5 Default Interpretations When the Question Does Not Say

Users rarely spell out the ranking measure. Do not ask them to and do not pick your own — apply the
default below, and **state the measure you used** in the answer. An explicit measure in the question
always wins over the default.

| Phrase | Default measure | How to compute it |
|---|---|---|
| "top / biggest / largest / best **clients**", "my top 10 clients" | **AUM** | `SUM(client_aum.aum_value)` per client, summed across the client's LOBs, pinned to the latest `as_on_date`. This is the default whenever no measure is named. |
| "top **families**" | **AUM** | Same, grouped on `family_name`. |
| "top **employees / RMs / bankers / staff**" | **Revenue booked** | `SUM(client_revenue.revenue_amount)` attributed through `emp_id`, over the stated period (FY2026 if none is stated). |
| "top **AMCs / products / funds**" | **Turnover** | `SUM(client_transactions.amount)` over the stated period. |
| "**portfolio value**" said explicitly | **Holdings value** | `SUM(client_holdings.current_value)` on the pinned holdings date — a *different* number from AUM, on a different date (§3.7). Only use this route when the question says portfolio/position value rather than AUM. |
| "top **client**" (singular) | **1** | Singular means one row, not a list. |
| "top **clients**" (plural) with no number | **10** | Return ten and say that you defaulted to ten. |

**Ties.** Order by the measure descending, then by the entity's **name** ascending, so the result is
deterministic.

**When N exceeds what exists**, return everything that qualifies and say how many there were. Do not
pad the list, and do not treat a short result as a failure.

**"Each X" lists only the members that have rows.** "How many clients sit in each sub-line of
business?" returns the 7 sub-lines that have clients, not all 8 with a zero for `Hybrid Schemes`.
This extends C2 from time periods to dimensions, and follows §7: an empty cohort is a legitimate
absence, and padding it manufactures rows nobody asked for. Say how many members were empty if it
matters. An explicit "including those with none" overrides this.

**"Book average" is value-weighted; "the average client" is equal-weighted.** "The book's share of X",
"book average allocation" and any book-level view pool the whole book, so large clients dominate —
pooled, the book is Liquid 26.02 / Category III 14.63 / Bank FD 12.05 / Large Cap 11.79 %. "The
average client", "the typical client" and "on average a client holds" take the simple mean of each
client's own percentages, where every client counts once — Bank FD 28.31 / Large Cap 19.17 /
Liquid 14.73 / Mid Cap 9.77 %. The §6.2 rule that percentage columns are `AVG`-ed across clients is
the second of these, not the first.

**Sector allocation is a share of the whole portfolio.** The denominator is the client's full book,
with the untagged part shown explicitly as its own bucket — never silently rescaled to the
sector-tagged subset. About 80% of book value carries no sector (§5), so the two differ by a lot:
Ram Krishnan's Oil & Gas is 4.46% of his portfolio but 24.29% of his tagged holdings. Name the
untagged bucket for what it is — mutual funds, bonds, fixed deposits, AIF and PMS, not funds alone.

**A family or cohort instrument list is one row per instrument.** "For the Krishnan Family, list all
bonds held…" returns each bond once, aggregated across the members who hold it — 9 rows, not the 21
member-bond rows. Break it out per member only where the question says "by member", "per client" or
"who holds it".

**When the measure is computable but the KPI is not.** A question can name a cohort you *can* resolve
and then ask for something the warehouse cannot produce — "give XIRR for top 10 clients" is the
common case. Resolve the cohort by the rule above, then decline the KPI specifically: name the ten
clients and the AUM that ranked them, state that XIRR is not computable here and why (§3.1), and do
**not** substitute a holding-period or point-to-point return in its place. Declining the whole
request as if the cohort were also unknown is wrong — half the question was answerable.

---

## 7. Response Guidelines

- Cite the **table** and **column** you used when the answer depends on a modelling choice.
- Return **only what was asked** — no extra context columns, and never echo a filter value back as a column.
- **Never emit** `pan_number`, `client_pan`, `account_number`, `ifsc_code`, `dp_id`, `email` or `mobile`.
  They may be used as an input filter or counted, but the values must not appear in an answer.
- When a KPI cannot be computed from the schema, **say so and name what is missing** — do not
  approximate it with a different measure under the same label.
- An empty result is a legitimate answer. State it as "none matched" rather than as a failure, and do
  not relax the question's filters to manufacture rows.
- When a figure rests on a thin window (§4.5), state the window alongside the number.
- Amounts are **INR (₹)**; do not convert currencies unless asked.
- **Never invent a live market level.** "Current market details", the level of an index or today's
  macro backdrop is answered from the **latest close in `dim_cmot_index_prices`** (12 days to
  2026-05-19), with that date stated — never from memory and never from the wall clock (C1). Where no
  such series exists at all, as for a **volatility index**, decline. Investment **doctrine** — what a
  60/40 allocation is like, how drawdown behaves — may be answered from general knowledge, said
  plainly to be general knowledge and not drawn from the database.
- **State the tolerance behind any audit or "break" count.** A reconciliation figure is meaningless
  without one: `~₹1` on a recomputed `quantity × price` (T5) and **1 percentage point** on allocations
  that should total 100 (T8). Name it alongside the count.
- **Write the scope filter even where it currently removes nothing.** S1, S2 and §4.6 may exclude zero
  rows today, but the filter is still correct practice and guards against future data changes.

**Absent from this warehouse entirely** — decline rather than approximate: investment goals and
targets, risk scores and risk profiles, Sharpe ratio, volatility, standard deviation, portfolio health
scores, tax-rule tables, credit-card activity, advisor seniority bands, client mandates, geopolitical
relevance tagging, cash-movement provenance (no counterparty, bank-transfer or funding-source
attribute), and per-fund look-through — so **indirect** sector exposure through a fund is not
computable, only direct holdings.

