# Multi-step Comparative SQL Rulebook

This file studies only the workbook rows where `query_type = Multi-step Comparative`.
It uses the ground-truth SQL as evidence for how the benchmark author translated
question text into computation. The purpose is to guide V4 decomposition and
validation with general rules, not to hardcode individual answers.

Source workbook: `C:\Users\AMAN KUMAR SINGH\Desktop\financial\query_specs_improevemnt\improvement1\dataset\verification_results_v2_sql_correct_442.xlsx`

## Scope

- Rows analyzed: 56
- SQL rows using `WITH` CTEs: 56
- Rows with investor-level CTE aggregation: 56
- Rows with conditional `CASE` metric logic: 24
- Rows where final metrics average pre-aggregated CTE outputs: 56

## Core Translation Rules

1. Multi-step comparative SQL usually creates a two-stage computation.
   Fact/event sources are first reduced to `investor_id` in CTEs, then the final
   query compares investor groups such as risk tolerance or time horizon.

2. The final comparison group is explicit in both `SELECT ... AS group_value`
   and the final `GROUP BY`. V4 should require the intent decomposition's
   comparison entity or dimension to match this final output grain.

3. When a question compares multiple fact metrics, the SQL avoids raw fact-to-fact
   joins. It joins pre-aggregated investor-level CTEs, which prevents row
   multiplication.

4. Final group metrics often use `AVG(cte.metric)` over investor-level metrics.
   That means phrases like average holding value by risk tolerance are usually
   interpreted as average of each investor's total holding value, not average of
   raw holdings.

5. Metric names have benchmark-specific formulas, but they are reusable semantic
   formulas rather than question-specific answers. Examples include holding gain
   as `SUM(current_value - cost)`, allocation concentration as `MAX(allocation_pct)`,
   scenario change as `AVG(new_allocation_pct - current_allocation_pct)`, and
   rebalancing gap as `AVG(target_allocation_pct - current_allocation_pct)`.

6. Cash-flow metrics use signed amount rules. Net cash flow is `SUM(amount)`,
   inflow is positive amount only, and outflow is the negative of negative amounts.
   Date-scoped cash-flow metrics use `CASE` inside the investor-level aggregation.

7. The SQL uses inner joins for required sources in these rows. The implied
   eligibility is investors that have all required metric sources, after each
   source has been reduced to investor grain.

## Source Frequency

| SQL table | Meaning | Count |
| --- | --- | --- |
| ATOM_ENTITY_INVESTOR_PROFILE_001 | investor profile / comparison dimension | 56 |
| ATOM_ENTITY_INVESTMENT_GOAL_001 | investment goal fact | 27 |
| ATOM_ENTITY_PORTFOLIO_HEALTH_001 | portfolio health metric | 26 |
| ATOM_EVENT_CASH_FLOW_001 | cash-flow event fact | 24 |
| ATOM_EVENT_SCENARIO_REBALANCING_001 | scenario rebalancing event fact | 21 |
| ATOM_ENTITY_PORTFOLIO_HOLDING_001 | portfolio holding fact | 17 |
| ATOM_EVENT_REBALANCING_ACTION_001 | rebalancing action event fact | 17 |
| ATOM_ENTITY_SECTOR_ALLOCATION_001 | sector allocation fact | 13 |

## Final Grouping Frequency

| Final group by | Count |
| --- | --- |
| p.risk_tolerance | 16 |
| p.time_horizon | 16 |
| p.category | 16 |
| p.segment | 8 |

## Common Table Combinations

| Table combination | Count |
| --- | --- |
| ATOM_ENTITY_INVESTMENT_GOAL_001 + ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_ENTITY_PORTFOLIO_HEALTH_001 | 4 |
| ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_ENTITY_PORTFOLIO_HEALTH_001 + ATOM_ENTITY_PORTFOLIO_HOLDING_001 | 4 |
| ATOM_ENTITY_INVESTMENT_GOAL_001 + ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_EVENT_CASH_FLOW_001 | 4 |
| ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_ENTITY_PORTFOLIO_HOLDING_001 + ATOM_ENTITY_SECTOR_ALLOCATION_001 | 4 |
| ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_EVENT_CASH_FLOW_001 + ATOM_EVENT_REBALANCING_ACTION_001 | 4 |
| ATOM_ENTITY_INVESTMENT_GOAL_001 + ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_EVENT_SCENARIO_REBALANCING_001 | 4 |
| ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_EVENT_REBALANCING_ACTION_001 + ATOM_EVENT_SCENARIO_REBALANCING_001 | 4 |
| ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_EVENT_CASH_FLOW_001 + ATOM_EVENT_SCENARIO_REBALANCING_001 | 4 |
| ATOM_ENTITY_INVESTMENT_GOAL_001 + ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_ENTITY_PORTFOLIO_HEALTH_001 + ATOM_ENTITY_PORTFOLIO_HOLDING_001 | 3 |
| ATOM_ENTITY_INVESTMENT_GOAL_001 + ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_EVENT_CASH_FLOW_001 + ATOM_EVENT_REBALANCING_ACTION_001 | 3 |
| ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_ENTITY_PORTFOLIO_HEALTH_001 + ATOM_EVENT_REBALANCING_ACTION_001 + ATOM_EVENT_SCENARIO_REBALANCING_001 | 3 |
| ATOM_ENTITY_INVESTOR_PROFILE_001 + ATOM_ENTITY_SECTOR_ALLOCATION_001 + ATOM_EVENT_CASH_FLOW_001 + ATOM_EVENT_SCENARIO_REBALANCING_001 | 3 |

## How To Use This In V4

For multi-step comparative questions, add a SQL-style interpretation contract
between intent decomposition and execution decomposition:

```json
{
  "comparison_dimension": "risk_tolerance | time_horizon | ...",
  "base_metric_sources": ["goal", "holding", "cash", "rebalance", "scenario"],
  "metric_formulas": ["SUM(current_value-cost)", "AVG(progress_pct)", "..."],
  "source_grain_before_join": "investor_id",
  "final_output_grain": "comparison_dimension",
  "eligibility_join_policy": "inner join required investor-level metric sources",
  "filter_scope": "inside source CTE for raw filters, HAVING/final filter for aggregate filters"
}
```

The LLM should still infer the meaning. The deterministic validator should only
check structural consistency:

- every requested metric has a source and formula;
- each multi-row fact source is aggregated to investor grain before cross-source joins;
- the final group matches the comparison dimension;
- aggregate thresholds are applied after aggregation;
- raw filters are applied inside the relevant source CTE;
- cash-flow sign and date-window logic are explicit when requested.

## Per-question CSV

The full per-question extraction is saved in:

`multistep_sql_interpretation.csv`

## Sample Rows

### MC-019

Question: Across risk_tolerance, how do goal progress, health risk, and liquidity compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.risk_tolerance; final metric averages investor-level CTE outputs

Metric rules: goal progress: AVG(progress_pct) at investor grain; goal shortfall: AVG(shortfall) at investor grain; goal sharpe: AVG(avg_sharpe_ratio) at investor grain; goal volatility: AVG(avg_volatility_pct) at investor grain; time to goal: AVG(time_to_goal_months) at investor grain

```sql
WITH goal AS ( SELECT investor_id, COUNT(*) AS goal_count, AVG(progress_pct) AS avg_progress_pct, AVG(shortfall) AS avg_shortfall, AVG(avg_sharpe_ratio) AS avg_sharpe_ratio, AVG(avg_volatility_pct) AS avg_volatility_pct, AVG(time_to_goal_months) AS avg_time_to_goal_months FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investor_id ) SELECT p.risk_tolerance AS group_value, ROUND(AVG(goal.avg_progress_pct),2) AS avg_progress_pct, ROUND(AVG(h.risk_score),2) AS avg_risk_score, ROUND(AVG(h.liquidity_score),2) AS avg_liquidity_score FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN goal ON goal.investor_id=p.investor_id JOIN ATOM_ENTITY_PORTFOLIO_HEALTH_001 h ON h.investor_id=p.investor_id GROUP BY p.risk_tolerance
```
### MC-020

Question: Across risk_tolerance, how do holding gain, health risk, and diversification compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.risk_tolerance; final metric averages investor-level CTE outputs

Metric rules: holding gain: SUM(current_value - cost) at investor grain; holding value: SUM(current_value) at investor grain; holding return: AVG(returns_pct) at investor grain; dividends: SUM(dividends) at investor grain; taxes paid: SUM(taxes_paid) at investor grain

```sql
WITH holding AS ( SELECT investor_id, COUNT(*) AS holding_count, SUM(current_value) AS total_holding_value, SUM(current_value-cost) AS total_holding_gain, AVG(returns_pct) AS avg_returns_pct, SUM(dividends) AS total_dividends, SUM(taxes_paid) AS total_taxes_paid FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 GROUP BY investor_id ) SELECT p.risk_tolerance AS group_value, ROUND(AVG(holding.total_holding_gain),2) AS avg_holding_gain, ROUND(AVG(h.risk_score),2) AS avg_risk_score, ROUND(AVG(h.diversification_score),2) AS avg_diversification_score FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN holding ON holding.investor_id=p.investor_id JOIN ATOM_ENTITY_PORTFOLIO_HEALTH_001 h ON h.investor_id=p.investor_id GROUP BY p.risk_tolerance
```
### MC-021

Question: Across risk_tolerance, how do cash-flow net amount, goal progress, and shortfall compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.risk_tolerance; final metric averages investor-level CTE outputs; conditional CASE is part of metric definition

Metric rules: goal progress: AVG(progress_pct) at investor grain; goal shortfall: AVG(shortfall) at investor grain; net cash flow: SUM(amount) at investor grain; cash inflow: SUM positive amount, else 0; cash outflow: -SUM negative amount, else 0; 2025 cash flow: CASE date window before investor aggregation

```sql
WITH cash AS ( SELECT investor_id, COUNT(*) AS transaction_count, SUM(amount) AS net_cash_flow, SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS inflow_amount, -SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS outflow_amount, SUM(CASE WHEN date >= '2025-01-01' AND date < '2026-01-01' THEN amount ELSE 0 END) AS net_cash_flow_2025 FROM ATOM_EVENT_CASH_FLOW_001 GROUP BY investor_id ) , goal AS (SELECT investor_id, AVG(progress_pct) AS avg_progress_pct, AVG(shortfall) AS avg_shortfall FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investor_id) SELECT p.risk_tolerance AS group_value, ROUND(AVG(cash.net_cash_flow),2) AS avg_net_cash_flow, ROUND(AVG(goal.avg_progress_pct),2) AS avg_progress_pct, ROUND(AVG(goal.avg_shortfall),2) AS avg_shortfall FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN cash ON cash.investor_id=p.investor_id JOIN goal ON goal.investor_id=p.investor_id GROUP BY p.risk_tolerance
```
### MC-022

Question: Across risk_tolerance, how do allocation concentration, holding return, and holding value compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.risk_tolerance; final metric averages investor-level CTE outputs

Metric rules: holding gain: SUM(current_value - cost) at investor grain; holding value: SUM(current_value) at investor grain; holding return: AVG(returns_pct) at investor grain; dividends: SUM(dividends) at investor grain; taxes paid: SUM(taxes_paid) at investor grain; allocation concentration: MAX(allocation_pct) at investor grain; allocation average: AVG(allocation_pct) at investor grain; sector investment: SUM(total_investment) at investor grain

```sql
WITH alloc AS ( SELECT investor_id, COUNT(*) AS allocation_count, MAX(allocation_pct) AS max_allocation_pct, AVG(allocation_pct) AS avg_allocation_pct, SUM(total_investment) AS total_sector_investment FROM ATOM_ENTITY_SECTOR_ALLOCATION_001 GROUP BY investor_id ) , holding AS ( SELECT investor_id, COUNT(*) AS holding_count, SUM(current_value) AS total_holding_value, SUM(current_value-cost) AS total_holding_gain, AVG(returns_pct) AS avg_returns_pct, SUM(dividends) AS total_dividends, SUM(taxes_paid) AS total_taxes_paid FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 GROUP BY investor_id ) SELECT p.risk_tolerance AS group_value, ROUND(AVG(alloc.max_allocation_pct),2) AS avg_max_allocation_pct, ROUND(AVG(holding.avg_returns_pct),2) AS avg_returns_pct, ROUND(AVG(holding.total_holding_value),2) AS avg_holding_value FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN alloc ON alloc.investor_id=p.investor_id JOIN holding ON holding.investor_id=p.investor_id GROUP BY p.risk_tolerance
```
### MC-023

Question: Across risk_tolerance, how do rebalancing amount, cash flow, and transaction count compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.risk_tolerance; final metric averages investor-level CTE outputs; conditional CASE is part of metric definition

Metric rules: net cash flow: SUM(amount) at investor grain; cash inflow: SUM positive amount, else 0; cash outflow: -SUM negative amount, else 0; 2025 cash flow: CASE date window before investor aggregation; rebalancing gap: AVG(target_allocation_pct - current_allocation_pct) at investor grain; rebalancing amount: SUM(amount) at investor grain

```sql
WITH cash AS ( SELECT investor_id, COUNT(*) AS transaction_count, SUM(amount) AS net_cash_flow, SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS inflow_amount, -SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS outflow_amount, SUM(CASE WHEN date >= '2025-01-01' AND date < '2026-01-01' THEN amount ELSE 0 END) AS net_cash_flow_2025 FROM ATOM_EVENT_CASH_FLOW_001 GROUP BY investor_id ) , reb AS ( SELECT investor_id, COUNT(*) AS rebalance_action_count, SUM(amount) AS total_rebalance_amount, AVG(target_allocation_pct-current_allocation_pct) AS avg_rebalance_gap FROM ATOM_EVENT_REBALANCING_ACTION_001 GROUP BY investor_id ) SELECT p.risk_tolerance AS group_value, ROUND(AVG(cash.net_cash_flow),2) AS avg_net_cash_flow, ROUND(AVG(cash.transaction_count),2) AS avg_transaction_count, ROUND(AVG(reb.total_rebalance_amount),2) AS avg_rebalance_amount FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN cash ON cash.investor_id=p.investor_id JOIN reb ON reb.investor_id=p.investor_id GROUP BY p.risk_tolerance
```
### MC-024

Question: Across risk_tolerance, how do scenario change, goal progress, and volatility compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.risk_tolerance; final metric averages investor-level CTE outputs

Metric rules: goal progress: AVG(progress_pct) at investor grain; goal volatility: AVG(avg_volatility_pct) at investor grain; scenario change: AVG(new_allocation_pct - current_allocation_pct) at investor grain; max scenario change: MAX(new_allocation_pct - current_allocation_pct) at investor grain

```sql
WITH goal AS (SELECT investor_id, AVG(progress_pct) AS avg_progress_pct, AVG(avg_volatility_pct) AS avg_volatility_pct FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investor_id), scen AS ( SELECT investor_id, COUNT(*) AS scenario_count, AVG(new_allocation_pct-current_allocation_pct) AS avg_scenario_change, MAX(new_allocation_pct-current_allocation_pct) AS max_scenario_change FROM ATOM_EVENT_SCENARIO_REBALANCING_001 GROUP BY investor_id ) SELECT p.risk_tolerance AS group_value, ROUND(AVG(scen.avg_scenario_change),2) AS avg_scenario_change, ROUND(AVG(goal.avg_progress_pct),2) AS avg_progress_pct, ROUND(AVG(goal.avg_volatility_pct),2) AS avg_volatility_pct FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN goal ON goal.investor_id=p.investor_id JOIN scen ON scen.investor_id=p.investor_id GROUP BY p.risk_tolerance
```
### MC-025

Question: Across risk_tolerance, how do scenario change, rebalancing gap, and rebalancing amount compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.risk_tolerance; final metric averages investor-level CTE outputs

Metric rules: net cash flow: SUM(amount) at investor grain; rebalancing gap: AVG(target_allocation_pct - current_allocation_pct) at investor grain; rebalancing amount: SUM(amount) at investor grain; scenario change: AVG(new_allocation_pct - current_allocation_pct) at investor grain; max scenario change: MAX(new_allocation_pct - current_allocation_pct) at investor grain

```sql
WITH reb AS ( SELECT investor_id, COUNT(*) AS rebalance_action_count, SUM(amount) AS total_rebalance_amount, AVG(target_allocation_pct-current_allocation_pct) AS avg_rebalance_gap FROM ATOM_EVENT_REBALANCING_ACTION_001 GROUP BY investor_id ) , scen AS ( SELECT investor_id, COUNT(*) AS scenario_count, AVG(new_allocation_pct-current_allocation_pct) AS avg_scenario_change, MAX(new_allocation_pct-current_allocation_pct) AS max_scenario_change FROM ATOM_EVENT_SCENARIO_REBALANCING_001 GROUP BY investor_id ) SELECT p.risk_tolerance AS group_value, ROUND(AVG(scen.avg_scenario_change),2) AS avg_scenario_change, ROUND(AVG(reb.avg_rebalance_gap),2) AS avg_rebalance_gap, ROUND(AVG(reb.total_rebalance_amount),2) AS avg_rebalance_amount FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN reb ON reb.investor_id=p.investor_id JOIN scen ON scen.investor_id=p.investor_id GROUP BY p.risk_tolerance
```
### MC-026

Question: Across risk_tolerance, how do cash-flow net amount, scenario change, and scenario count compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.risk_tolerance; final metric averages investor-level CTE outputs; conditional CASE is part of metric definition

Metric rules: net cash flow: SUM(amount) at investor grain; cash inflow: SUM positive amount, else 0; cash outflow: -SUM negative amount, else 0; 2025 cash flow: CASE date window before investor aggregation; scenario change: AVG(new_allocation_pct - current_allocation_pct) at investor grain; max scenario change: MAX(new_allocation_pct - current_allocation_pct) at investor grain

```sql
WITH cash AS ( SELECT investor_id, COUNT(*) AS transaction_count, SUM(amount) AS net_cash_flow, SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS inflow_amount, -SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS outflow_amount, SUM(CASE WHEN date >= '2025-01-01' AND date < '2026-01-01' THEN amount ELSE 0 END) AS net_cash_flow_2025 FROM ATOM_EVENT_CASH_FLOW_001 GROUP BY investor_id ) , scen AS ( SELECT investor_id, COUNT(*) AS scenario_count, AVG(new_allocation_pct-current_allocation_pct) AS avg_scenario_change, MAX(new_allocation_pct-current_allocation_pct) AS max_scenario_change FROM ATOM_EVENT_SCENARIO_REBALANCING_001 GROUP BY investor_id ) SELECT p.risk_tolerance AS group_value, ROUND(AVG(cash.net_cash_flow),2) AS avg_net_cash_flow, ROUND(AVG(scen.avg_scenario_change),2) AS avg_scenario_change, ROUND(AVG(scen.scenario_count),2) AS avg_scenario_count FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN cash ON cash.investor_id=p.investor_id JOIN scen ON scen.investor_id=p.investor_id GROUP BY p.risk_tolerance
```
### MC-027

Question: Across time_horizon, how do goal progress, health risk, and liquidity compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.time_horizon; final metric averages investor-level CTE outputs

Metric rules: goal progress: AVG(progress_pct) at investor grain; goal shortfall: AVG(shortfall) at investor grain; goal sharpe: AVG(avg_sharpe_ratio) at investor grain; goal volatility: AVG(avg_volatility_pct) at investor grain; time to goal: AVG(time_to_goal_months) at investor grain

```sql
WITH goal AS ( SELECT investor_id, COUNT(*) AS goal_count, AVG(progress_pct) AS avg_progress_pct, AVG(shortfall) AS avg_shortfall, AVG(avg_sharpe_ratio) AS avg_sharpe_ratio, AVG(avg_volatility_pct) AS avg_volatility_pct, AVG(time_to_goal_months) AS avg_time_to_goal_months FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investor_id ) SELECT p.time_horizon AS group_value, ROUND(AVG(goal.avg_progress_pct),2) AS avg_progress_pct, ROUND(AVG(h.risk_score),2) AS avg_risk_score, ROUND(AVG(h.liquidity_score),2) AS avg_liquidity_score FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN goal ON goal.investor_id=p.investor_id JOIN ATOM_ENTITY_PORTFOLIO_HEALTH_001 h ON h.investor_id=p.investor_id GROUP BY p.time_horizon
```
### MC-028

Question: Across time_horizon, how do holding gain, health risk, and diversification compare using three related tables?

Authoring rule: pre-aggregate fact/event tables to investor_id; final comparison groups by p.time_horizon; final metric averages investor-level CTE outputs

Metric rules: holding gain: SUM(current_value - cost) at investor grain; holding value: SUM(current_value) at investor grain; holding return: AVG(returns_pct) at investor grain; dividends: SUM(dividends) at investor grain; taxes paid: SUM(taxes_paid) at investor grain

```sql
WITH holding AS ( SELECT investor_id, COUNT(*) AS holding_count, SUM(current_value) AS total_holding_value, SUM(current_value-cost) AS total_holding_gain, AVG(returns_pct) AS avg_returns_pct, SUM(dividends) AS total_dividends, SUM(taxes_paid) AS total_taxes_paid FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 GROUP BY investor_id ) SELECT p.time_horizon AS group_value, ROUND(AVG(holding.total_holding_gain),2) AS avg_holding_gain, ROUND(AVG(h.risk_score),2) AS avg_risk_score, ROUND(AVG(h.diversification_score),2) AS avg_diversification_score FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN holding ON holding.investor_id=p.investor_id JOIN ATOM_ENTITY_PORTFOLIO_HEALTH_001 h ON h.investor_id=p.investor_id GROUP BY p.time_horizon
```
