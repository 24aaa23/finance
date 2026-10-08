# Business rules

This is the configurable rules input for the supplied wealth-management schema.
It contains business definitions and configurable policies.
Explicit definitions, periods, thresholds and populations in the user's
question take precedence. These rules override older conflicting domain defaults.

## R1. Cash-flow signs

The documented storage convention is signed amount: inflows are positive and
outflows are negative. Inflows include Deposit, SIP, Interest Credit, Tax Refund,
Dividend Reinvestment and Lump Sum; Withdrawal and Redemption are outflows.
Net cash flow = `SUM(amount)`. Do not re-sign already signed values by type.
Outflow magnitude = `-SUM(amount)` or `SUM(ABS(amount))` over the requested outflow
type. XIRR uses the investor-perspective sign transform `-amount`; it is distinct
from the storage convention.

## R2. Outflow presentation

"Total Withdrawal amount" or "amount withdrawn" denotes a positive magnitude,
`-SUM(amount)` for documented signed withdrawals. Net-flow questions retain sign.

## R3. Ranking

Top/bottom rankings use the requested score direction and a deterministic
secondary natural entity ID ascending, unless the question gives another
tie-break. Use actual documented ID fields, such as holding_id or investor_id.

## R4. Missing ranked scores

A NULL score is missing, not an extreme value. Exclude missing scores from
highest/lowest rankings with `IS NOT NULL`. This policy concerns rankings;
proportion denominators follow R11.

## R5. Averaging grain

For cohort averages grouped by investor attributes, the documented default is
per-investor aggregation followed by the average across investors. Do not mix
per-investor and row-pooled weights silently. An explicit question requesting
observation-weighted averages overrides this default.

## R6. Joins and population

Join only sources required by the question, its metric operands and connections.
Preserve the requested population. Optional child metrics use left joins from
the investor profile; explicit required participation must still be enforced.
Every stated filter or existence condition must be represented. Do not add
unrequested child tables that change the population.

## R7. Allocation concentration

Allocation concentration for an investor = `MAX(allocation_pct)` over that
investor's ATOM_ENTITY_SECTOR_ALLOCATION_001 records. A cohort's average
concentration = per-investor MAX, then AVG across investors. The metric denotes
the largest single-sector share. Use the question's stated definition when given.

## R8. Composite metrics

Use documented formulas; do not invent mixed-scale sums. Per-investor components:

| Symbol | Definition | Source |
| --- | --- | --- |
| RS, LS, DS, GM | risk, liquidity, diversification, goal-match scores | ATOM_ENTITY_PORTFOLIO_HEALTH_001.risk_score, liquidity_score, diversification_score, goal_match_pct |
| CONC | MAX(allocation_pct) | ATOM_ENTITY_SECTOR_ALLOCATION_001 |
| VOL | AVG(avg_volatility_pct) | ATOM_ENTITY_INVESTMENT_GOAL_001 |
| SHORT | SUM(shortfall), where shortfall = target_amount - current_value | ATOM_ENTITY_INVESTMENT_GOAL_001 |
| AVGSHORT | AVG(shortfall) | ATOM_ENTITY_INVESTMENT_GOAL_001 |
| GAIN | SUM(current_value - cost) | ATOM_ENTITY_PORTFOLIO_HOLDING_001 |
| HVAL | SUM(current_value) | ATOM_ENTITY_PORTFOLIO_HOLDING_001 |
| NCF | SUM(amount), signed, for the period stated in the question | ATOM_EVENT_CASH_FLOW_001 |
| REB | SUM(amount) | ATOM_EVENT_REBALANCING_ACTION_001 |
| SCEN_delta_sum | SUM(new_allocation_pct - current_allocation_pct) | ATOM_EVENT_SCENARIO_REBALANCING_001 |

`risk_pressure_score = RS + (100 - LS) + (100 - DS)` is the single official
definition. Its scale is 0-300; missing any component gives NULL and excludes the
investor from that score's eligible population. Older five-term definitions are
superseded.

`combined_gain_and_ncf = GAIN + NCF` (INR).
`combined_ncf_and_reb = NCF + REB` (INR).
`combined_holding_value_and_shortfall = HVAL + SHORT` (INR).

Normalized indices use the population with all required components present.
For each component x, `normalized(x) = (x - min_pop(x)) / (max_pop(x) - min_pop(x))`.
Guard the zero-range denominator; do not invent an undocumented zero-range policy.
Normalized components are in [0,1]; the index is 100 times their equal-weighted
mean. A reducing component enters as `1 - normalized(x)`.

`quantitative_burden_index = 100 * mean(normalized(SHORT), 1 - normalized(GAIN), 1 - normalized(NCF), normalized(risk_pressure_score))`.
`transaction_rebalance_index = 100 * mean(normalized(NCF), normalized(REB), normalized(SCEN_delta_sum))`.
`temporal_pressure_index = 100 * mean(normalized(NCF(period)), normalized(REB), 1 - normalized(AVGSHORT), normalized(SCEN_delta_sum))`.

Use only the period and threshold stated in the question or a separately
documented general policy. Do not import a threshold or time window from another
question. Scenario-change aggregation for these indices is SUM.

## R9. Return weighting

"Average return" uses equal-weighted AVG(returns_pct) at the documented
per-investor-first grain. Explicit portfolio/overall/value-weighted return uses
the documented current_value/cost weighting. Honor the question's wording.

## R10. Aggregation guardrails

Do not sum or average IDs, dates or enums. Count investors using
COUNT(DISTINCT investor_id). Average goal_match_pct and other health scores at
the documented investor grain; do not sum them unless explicitly defined.

## R11. Share denominators

"Share of investors in the group with metric > X" uses the full requested cohort
as denominator: AVG(CASE WHEN metric > X THEN 1 ELSE 0 END). A missing metric does
not meet the condition and remains in that denominator, unless the question
explicitly defines a different population.

## Additional documented policy

PPF lock-in is 15 years, overriding an older conflicting two-year default.
