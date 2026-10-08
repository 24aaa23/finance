# NeoWealth — Business & Domain Rules

This folder is the complete, final rule set for querying the NeoWealth data warehouse correctly.

## Contents

| File / folder | What it is |
|---|---|
| `01_domain_and_business_rules.md` | The rule book: domain overview, client/product classification, KPI definitions (XIRR, AUM, gains, drawdown, allocation, benchmark comparison, revenue), data-quality and grain/join/type checks, aggregation rules, default interpretations, and response guidelines. |
| `02_column_reference/` | One reference file per table (21 tables) describing every column: its meaning, type, nullability, and how it relates to other tables. |

## How to use this

Read `01_domain_and_business_rules.md` first — it is organised by topic and is meant to be read in order.
Use `02_column_reference/` alongside it when you need the precise definition of a specific column or table.

Currency is INR (₹); the query engine is DuckDB. Before running any query, apply the session settings noted at
the top of `01_domain_and_business_rules.md`.
