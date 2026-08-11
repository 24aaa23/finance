# Methodology for Generating 535 SQL-Grounded Benchmark Questions

## 3.1 Overview of the 535-Question Generation Approach

The benchmark questions were created to evaluate a wealth-management Knowledge Graph (KG) question-answering pipeline. The main objective was not only to create natural language questions, but to create questions that have deterministic SQL-based ground-truth answers.

The generation process used three main sources of information:

1. Seed question patterns from `Questions.md`
2. Actual SQLite database schema and table information
3. Controlled generation requirements such as category, difficulty level, query type, and number of tables used

The final raw generation produced 535 SQL-grounded questions across 8 major question categories. Each question was paired with:

- natural language question
- category
- difficulty
- query type
- tables used
- number of tables used
- executable SQLite SQL query
- SQL-derived ground-truth answer

This makes the benchmark useful for comparing the KG/AOP pipeline output against reliable SQLite answers.

---

## 3.2 Data Sources Used for Question Generation

### 3.2.1 Seed Question File

The manually prepared file `Questions.md` was used as the initial source of question patterns. It contained example business questions grouped into different reasoning categories.

The file included patterns such as:

- investor status checks
- batch status queries
- enrichment and context queries
- at-risk and critical detection
- scoring and quantitative analysis
- reference intelligence and business rules
- temporal and transaction queries
- multi-step comparative queries

These seed questions guided the style, intent, and business meaning of the generated benchmark questions.

### 3.2.2 SQLite Database

The actual SQLite database used for grounding was:

```text
wealthmanagement_tables-main/raw_data_sample/wealth_management_diverse.db
```

The database contained the following 8 main tables:

| Table name | Main purpose |
|---|---|
| `ATOM_ENTITY_INVESTOR_PROFILE_001` | Investor profile, segment, risk tolerance, and demographic context |
| `ATOM_ENTITY_INVESTMENT_GOAL_001` | Investor goals, goal progress, target amount, shortfall, and goal timeline |
| `ATOM_ENTITY_PORTFOLIO_HEALTH_001` | Portfolio health score, risk score, liquidity score, and diversification score |
| `ATOM_ENTITY_PORTFOLIO_HOLDING_001` | Investor holdings, asset class, investment name, value, and return |
| `ATOM_ENTITY_SECTOR_ALLOCATION_001` | Sector allocation and concentration information |
| `ATOM_EVENT_CASH_FLOW_001` | Deposits, withdrawals, SIP activity, transaction amount, and transaction date |
| `ATOM_EVENT_REBALANCING_ACTION_001` | Buy, sell, hold, and rebalancing action recommendations |
| `ATOM_EVENT_SCENARIO_REBALANCING_001` | Scenario-based rebalancing triggered by market or macro events |

The LLM was instructed to use only available tables and columns from this database. This helped ensure that each generated SQL query could be executed directly on the SQLite database.

---

## 3.3 Category-Wise Question Plan

The 535 raw questions were generated across 8 categories.

| Question category | Number of questions | Main reasoning focus |
|---|---:|---|
| Investor status checks | 70 | Direct investor-level status, profile, goal, portfolio, and holding checks |
| Batch status queries | 40 | Group-level filtering, cohort analysis, and status summaries |
| Enrichment and context queries | 65 | Adding context from related tables around an investor, goal, portfolio, or transaction |
| At-risk and critical detection | 70 | Detecting risk, exceptions, poor performance, missing values, and urgent cases |
| Scoring and quantitative analysis | 65 | Numeric scoring, aggregation, ranking, totals, averages, and financial metrics |
| Reference intelligence and rules | 55 | Business-rule validation, allowed values, compliance checks, and consistency rules |
| Temporal and transaction queries | 65 | Date-based, monthly, transaction, cash-flow, SIP, and rebalancing history questions |
| Multi-step comparative queries | 105 | Multi-hop comparative questions using aggregation, joins, ranking, and cross-table reasoning |
| **Total** | **535** |  |

---

## 3.4 Difficulty and Query-Type Control

Each generated question was labelled with a difficulty level.

The difficulty labels used were:

- Easy
- Medium
- Hard
- Advanced
- Expert

Each question was also assigned a query type. The query type describes the reasoning or SQL pattern required to answer the question.

The query types included:

- Direct Retrieval
- Filtered List
- Categorical Aggregation
- Comparative
- Ranking
- Temporal
- Multi-Relational
- Rule-Based Detection
- Composite Reasoning
- Critical Exception Detection
- Reference Compliance
- Exception Detection
- Multi-step Comparative

These labels were added so that the benchmark could test different types of pipeline behavior. For example, a direct retrieval question checks whether the system can find a simple fact, while a multi-step comparative question checks whether the system can traverse multiple linked entities and perform reasoning.

---

## 3.5 Table-Hop and Multi-Table Coverage

Each question was also labelled by the number of tables required to answer it.

| Number of tables used | Meaning |
|---:|---|
| 1 table | Simple direct lookup or single-table aggregation |
| 2 tables | Basic join between two related entities |
| 3 tables | Moderate multi-hop reasoning |
| 4 tables | Complex cross-entity reasoning |
| 5+ tables | High multi-hop KG-style reasoning |

This was important because the KG pipeline is expected to show more value when the question requires multi-hop traversal. Therefore, the generated benchmark intentionally included many 3-table, 4-table, and 5-table questions.

---

## 3.6 General Prompt Template Used for Generation

The following prompt template describes the common instruction used for generating the SQL-grounded questions.

```text
You are generating SQL-grounded benchmark questions for a wealth-management knowledge graph question-answering pipeline.

Use the following inputs:
1. Seed question examples from Questions.md
2. SQLite database schema and table descriptions
3. Required question category: <CATEGORY_NAME>
4. Required number of questions: <N>
5. Required difficulty mix: Easy, Medium, Hard, Advanced, and Expert where applicable
6. Required query types: Direct Retrieval, Filtered List, Categorical Aggregation, Comparative, Ranking, Temporal, Multi-Relational, Rule-Based Detection, Composite Reasoning, and Multi-step Comparative
7. Required table coverage: include 1-table, 2-table, 3-table, 4-table, and 5-table questions wherever suitable

For every generated question, return:
- question_id
- natural language question
- category
- difficulty
- query_type
- tables_used
- number_of_tables_used
- executable SQLite SQL query
- expected ground-truth answer from SQL execution

Rules:
- Use only existing tables and columns from the supplied SQLite schema.
- The SQL must be valid SQLite.
- The question must be answerable from the database.
- Avoid duplicate questions.
- Prefer realistic wealth-management business questions.
- For KG evaluation, include more multi-hop questions where the answer requires traversing multiple related tables.
- Keep the SQL deterministic so the result can be used as ground truth.
```

---

## 3.7 Category-Wise Prompts, Seed Examples, and Generated Outputs

### 3.7.1 Investor Status Checks

#### Seed questions from `Questions.md`

```text
What is the goal status for investor INV001?
What is the portfolio health status for investor INV001?
What is the risk score for investor INV001?
Show me the profile of investor INV001.
What is the risk tolerance of investor INV001?
```

#### Category-specific prompt

```text
Generate investor status check questions using the wealth-management SQLite schema.

The questions should ask about individual investors and their profile, goals, portfolio health, risk tolerance, holdings, sector allocation, cash flow, or rebalancing status.

Create a mix of:
- simple one-table questions
- two-table relationship questions
- multi-table KG-style questions

For each question, provide:
- question
- difficulty
- query_type
- tables_used
- number_of_tables_used
- executable SQLite SQL
- ground-truth answer from SQL execution

Use realistic investor identifiers from the database and avoid duplicate questions.
```

#### Example generated output

| Field | Example |
|---|---|
| Question | What is the name of investor INV-001? |
| Difficulty | Easy |
| Query type | Direct Retrieval |
| Tables used | `ATOM_ENTITY_INVESTOR_PROFILE_001` |
| Number of tables used | 1 |
| SQL | `SELECT investor_name FROM ATOM_ENTITY_INVESTOR_PROFILE_001 WHERE investor_id = 'INV-001';` |

Another example:

| Field | Example |
|---|---|
| Question | What are the risk tolerance and time horizon of investor INV-002? |
| Difficulty | Easy |
| Query type | Direct Retrieval |
| Tables used | `ATOM_ENTITY_INVESTOR_PROFILE_001` |
| Number of tables used | 1 |
| SQL | `SELECT risk_tolerance, time_horizon FROM ATOM_ENTITY_INVESTOR_PROFILE_001 WHERE investor_id = 'INV-002';` |

---

### 3.7.2 Batch Status Queries

#### Seed questions from `Questions.md`

```text
Show goal projections for all investors.
Which investors are at risk of missing their goals?
Show investors with moderate or at-risk portfolio status.
Which portfolios are in critical health condition?
Show risk assessment for all high-value investors.
Which investors have urgent rebalancing needs?
```

#### Category-specific prompt

```text
Generate batch status questions over groups of investors.

The questions should analyze multiple investors together. Include filters, group-level summaries, cohort analysis, status lists, and aggregation.

Use tables such as:
- investor profile
- investment goal
- portfolio health
- portfolio holding
- cash flow
- rebalancing action
- scenario rebalancing

For each question, provide executable SQLite SQL and metadata including difficulty, query_type, tables_used, and number_of_tables_used.
```

#### Example generated output

| Field | Example |
|---|---|
| Question | Which investor profiles are missing both risk tolerance and category? |
| Difficulty | Easy |
| Query type | Filtered List |
| Tables used | `ATOM_ENTITY_INVESTOR_PROFILE_001` |
| Number of tables used | 1 |
| SQL | `SELECT investor_id, investor_name FROM ATOM_ENTITY_INVESTOR_PROFILE_001 WHERE (risk_tolerance IS NULL OR TRIM(risk_tolerance) = '') AND (category IS NULL OR TRIM(category) = '');` |

Another example:

| Field | Example |
|---|---|
| Question | Which investment goals have progress above 250%? |
| Difficulty | Easy |
| Query type | Filtered List |
| Tables used | `ATOM_ENTITY_INVESTMENT_GOAL_001` |
| Number of tables used | 1 |
| SQL | `SELECT goal_id, investor_id, investment_goal, progress_pct FROM ATOM_ENTITY_INVESTMENT_GOAL_001 WHERE progress_pct > 250;` |

---

### 3.7.3 Enrichment and Context Queries

#### Seed questions from `Questions.md`

```text
Show enriched goals with investor context for INV001.
Show goals with recommended allocation strategies.
Show complete portfolio view with all context for investor INV001.
Show holdings with segment and sector intelligence.
Show transactions with investor context and goal linkage.
Show investor INV001 with risk limits, goal recommendations, and product suitability.
```

#### Category-specific prompt

```text
Generate enrichment and context questions.

The questions should enrich a base entity with additional information from related tables. For example, combine investor profile with goals, holdings, sector allocation, portfolio health, cash flow, and rebalancing information.

Focus on questions that test whether the KG pipeline can move from one entity to related entities and return a richer context.

Return each generated question with:
- natural language question
- difficulty
- query_type
- tables_used
- number_of_tables_used
- valid SQLite SQL
- ground-truth answer
```

#### Example generated output

| Field | Example |
|---|---|
| Question | What distinct risk-tolerance context values are available in investor profiles? |
| Difficulty | Easy |
| Query type | Direct Retrieval |
| Tables used | `ATOM_ENTITY_INVESTOR_PROFILE_001` |
| Number of tables used | 1 |
| SQL | `SELECT DISTINCT risk_tolerance FROM ATOM_ENTITY_INVESTOR_PROFILE_001 WHERE risk_tolerance IS NOT NULL AND TRIM(risk_tolerance) <> '';` |

Another example:

| Field | Example |
|---|---|
| Question | What distinct time-horizon context values are available in investor profiles? |
| Difficulty | Easy |
| Query type | Direct Retrieval |
| Tables used | `ATOM_ENTITY_INVESTOR_PROFILE_001` |
| Number of tables used | 1 |
| SQL | `SELECT DISTINCT time_horizon FROM ATOM_ENTITY_INVESTOR_PROFILE_001 WHERE time_horizon IS NOT NULL AND TRIM(time_horizon) <> '';` |

---

### 3.7.4 At-Risk and Critical Detection

#### Seed questions from `Questions.md`

```text
Which investors are at risk of missing their goals?
Which goals are unlikely to be achieved without changes?
Which portfolios are in critical health condition?
Which investors have equity allocation exceeding their risk tolerance limit?
Which investors have urgent rebalancing needs?
Which investors have poor SIP adherence?
```

#### Category-specific prompt

```text
Generate at-risk and critical detection questions.

The questions should identify investors, goals, holdings, portfolios, cash-flow records, or rebalancing events with warning signs.

Use conditions such as:
- low goal progress
- high risk score
- poor liquidity
- low diversification
- negative holding returns
- excessive allocation concentration
- missing profile context
- urgent rebalancing actions
- unusual or critical scenario triggers

Include multi-table questions wherever possible because these are useful for KG multi-hop evaluation.
```

#### Example generated output

| Field | Example |
|---|---|
| Question | Which portfolio-health records have risk_score above 80? |
| Difficulty | Easy |
| Query type | Filtered List |
| Tables used | `ATOM_ENTITY_PORTFOLIO_HEALTH_001` |
| Number of tables used | 1 |
| SQL | `SELECT portfolio_health_id, investor_id, risk_score FROM ATOM_ENTITY_PORTFOLIO_HEALTH_001 WHERE risk_score > 80;` |

Another example:

| Field | Example |
|---|---|
| Question | Which portfolio holdings have returns_pct below -20? |
| Difficulty | Easy |
| Query type | Filtered List |
| Tables used | `ATOM_ENTITY_PORTFOLIO_HOLDING_001` |
| Number of tables used | 1 |
| SQL | `SELECT holding_id, investor_id, investment_name, returns_pct FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 WHERE returns_pct < -20;` |

---

### 3.7.5 Scoring and Quantitative Analysis

#### Seed questions from `Questions.md`

```text
What is the goal achievability score for investor INV002?
What additional monthly contribution is needed for goal achievement?
What is the investment discipline score for investor INV001?
What is the risk score for investor INV001?
What is the portfolio health score for investor INV001?
What is the total portfolio value for investor INV001 by Sector?
What is the total cash inflow for investor INV002 this year?
How many investors have a conservative risk profile?
```

#### Category-specific prompt

```text
Generate scoring and quantitative analysis questions.

Questions should ask for numeric scores, totals, averages, minimums, maximums, rankings, percentages, comparisons, and calculated wealth-management metrics.

Use SQL operations such as:
- COUNT
- SUM
- AVG
- MIN
- MAX
- ROUND
- GROUP BY
- ORDER BY
- CASE-based scoring bands

Include both single-table metric questions and multi-table quantitative reasoning questions.
```

#### Example generated output

| Field | Example |
|---|---|
| Question | What are the minimum, maximum, and average returns_pct across all holdings? |
| Difficulty | Easy |
| Query type | Direct Retrieval |
| Tables used | `ATOM_ENTITY_PORTFOLIO_HOLDING_001` |
| Number of tables used | 1 |
| SQL | `SELECT ROUND(MIN(returns_pct),2) AS min_returns_pct, ROUND(MAX(returns_pct),2) AS max_returns_pct, ROUND(AVG(returns_pct),2) AS avg_returns_pct FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001;` |

Another example:

| Field | Example |
|---|---|
| Question | What are the average risk_score, liquidity_score, diversification_score, and goal_match_pct across all portfolio-health records? |
| Difficulty | Easy |
| Query type | Direct Retrieval |
| Tables used | `ATOM_ENTITY_PORTFOLIO_HEALTH_001` |
| Number of tables used | 1 |
| SQL | `SELECT ROUND(AVG(risk_score),2) AS avg_risk_score, ROUND(AVG(liquidity_score),2) AS avg_liquidity_score, ROUND(AVG(diversification_score),2) AS avg_diversification_score, ROUND(AVG(goal_match_pct),2) AS avg_goal_match_pct FROM ATOM_ENTITY_PORTFOLIO_HEALTH_001;` |

---

### 3.7.6 Reference Intelligence and Rules

#### Seed questions from `Questions.md`

```text
What is the maximum equity allocation for conservative investors?
Which products are suitable for aggressive risk tolerance?
What is the volatility threshold for moderate risk profile?
Show asset allocation limits for all risk tolerance levels.
What is the recommended equity allocation for retirement during accumulation phase?
What products are suitable for emergency fund?
What is the lock-in period for ELSS?
Which investment types qualify for Section 80C deduction?
```

#### Category-specific prompt

```text
Generate reference intelligence and compliance questions.

Questions should test whether database records follow expected business rules, allowed values, required fields, category consistency, risk tolerance logic, and reference-style constraints.

Include:
- direct rule-style questions
- allowed-value checks
- missing-context checks
- consistency checks between investor profile and holdings
- compliance or exception detection questions

Return executable SQLite SQL and metadata for each question.
```

#### Example generated output

| Field | Example |
|---|---|
| Question | Using the allowed risk_tolerance values Conservative, Moderate, and Aggressive, which investor profiles have a risk_tolerance outside the allowed list? |
| Difficulty | Easy |
| Query type | Reference Compliance |
| Tables used | `ATOM_ENTITY_INVESTOR_PROFILE_001` |
| Number of tables used | 1 |
| SQL | `SELECT investor_id, investor_name, risk_tolerance FROM ATOM_ENTITY_INVESTOR_PROFILE_001 WHERE risk_tolerance IS NOT NULL AND TRIM(risk_tolerance) <> '' AND risk_tolerance NOT IN ('Conservative', 'Moderate', 'Aggressive');` |

Another example:

| Field | Example |
|---|---|
| Question | Using the required profile context rule that risk_tolerance must be present, which investor profiles have missing risk_tolerance? |
| Difficulty | Easy |
| Query type | Reference Compliance |
| Tables used | `ATOM_ENTITY_INVESTOR_PROFILE_001` |
| Number of tables used | 1 |
| SQL | `SELECT investor_id, investor_name, risk_tolerance FROM ATOM_ENTITY_INVESTOR_PROFILE_001 WHERE risk_tolerance IS NULL OR TRIM(risk_tolerance) = '';` |

---

### 3.7.7 Temporal and Transaction Queries

#### Seed questions from `Questions.md`

```text
Show all deposits made by investor INV001 in the last month.
What is the total cash inflow for investor INV002 this year?
What rebalancing actions are needed for investor INV001?
Show all buy recommendations.
List all sell actions for investor INV002.
What scenario-based rebalancing was triggered for investor INV001?
Show all rebalancing triggered by market volatility.
What sectors were affected by scenario-based rebalancing for INV002?
```

#### Category-specific prompt

```text
Generate temporal and transaction questions.

Questions should involve dates, months, transaction history, deposits, withdrawals, SIP activity, rebalancing dates, scenario dates, and time-based summaries.

Include:
- date filtering
- monthly aggregation
- transaction type grouping
- net cash-flow calculation
- rebalancing history
- scenario-triggered action analysis
- joins with investor profile, goals, and portfolio data

Use valid SQLite date/string functions where required.
```

#### Example generated output

| Field | Example |
|---|---|
| Question | For each month in the cash-flow table, what is the transaction count and net amount? |
| Difficulty | Easy |
| Query type | Temporal |
| Tables used | `ATOM_EVENT_CASH_FLOW_001` |
| Number of tables used | 1 |
| SQL | `SELECT SUBSTR(date,1,7) AS month, COUNT(*) AS transaction_count, ROUND(SUM(amount),2) AS net_amount FROM ATOM_EVENT_CASH_FLOW_001 WHERE date IS NOT NULL GROUP BY SUBSTR(date,1,7) ORDER BY month;` |

Another example:

| Field | Example |
|---|---|
| Question | For each cash-flow type, what is the transaction count and net amount? |
| Difficulty | Easy |
| Query type | Categorical Aggregation |
| Tables used | `ATOM_EVENT_CASH_FLOW_001` |
| Number of tables used | 1 |
| SQL | `SELECT type, COUNT(*) AS transaction_count, ROUND(SUM(amount),2) AS net_amount FROM ATOM_EVENT_CASH_FLOW_001 GROUP BY type;` |

---

### 3.7.8 Multi-Step Comparative Queries

#### Seed questions from `Questions.md`

```text
Show holdings for investors whose portfolio value exceeds the average portfolio value of all.
Find investors who have higher allocation in Technology sector than the average.
List all holdings that have returns higher than the investor's average holding return.
Show investors whose total deposits exceed their total withdrawals in the last year.
Find investors with portfolio health score below average who also have rebalancing actions pending.
Show investors who have made SIP contributions but have below-average goal alignment scores.
List investors whose sector concentration exceeds the maximum allowed for their risk profile.
```

#### Category-specific prompt

```text
Generate multi-step comparative questions.

Questions should require comparison, aggregation, filtering, joins, ranking, and multi-hop reasoning.

Prefer questions that use 3 or more tables because these are important for evaluating knowledge graph traversal.

The generated questions should compare:
- one investor against peer averages
- one sector against average sector exposure
- individual holdings against investor-level average returns
- goal progress against portfolio health
- cash-flow behavior against goal or risk status
- rebalancing actions against portfolio weakness

For every question, provide executable SQLite SQL, difficulty, query_type, tables_used, and number_of_tables_used.
```

#### Example generated output

| Field | Example |
|---|---|
| Question | Within investment goals, how do average progress_pct, average shortfall, and average volatility compare by investment_goal? |
| Difficulty | Easy |
| Query type | Comparative |
| Tables used | `ATOM_ENTITY_INVESTMENT_GOAL_001` |
| Number of tables used | 1 |
| SQL | `SELECT investment_goal, ROUND(AVG(progress_pct),2) AS avg_progress_pct, ROUND(AVG(shortfall),2) AS avg_shortfall, ROUND(AVG(avg_volatility_pct),2) AS avg_volatility_pct FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investment_goal;` |

Another example:

| Field | Example |
|---|---|
| Question | Within portfolio health, how do average risk_score, liquidity_score, and diversification_score compare across goal_match_pct bands? |
| Difficulty | Easy |
| Query type | Comparative |
| Tables used | `ATOM_ENTITY_PORTFOLIO_HEALTH_001` |
| Number of tables used | 1 |
| SQL | `SELECT CASE WHEN goal_match_pct < 33 THEN 'goal_match < 33' WHEN goal_match_pct < 67 THEN 'goal_match 33-66' ELSE 'goal_match >= 67' END AS goal_match_band, ROUND(AVG(risk_score),2) AS avg_risk_score, ROUND(AVG(liquidity_score),2) AS avg_liquidity_score, ROUND(AVG(diversification_score),2) AS avg_diversification_score FROM ATOM_ENTITY_PORTFOLIO_HEALTH_001 GROUP BY goal_match_band;` |

---

## 3.8 Output Format Used for Each Generated Question

Each generated row followed the same structure:

| Field | Description |
|---|---|
| `global_question_id` | Unique question identifier across the full benchmark |
| `source_csv` | Source category file from which the question came |
| `question_id` | Category-level question identifier |
| `question` | Natural language question |
| `category` | Business/reasoning category |
| `difficulty` | Easy, Medium, Hard, Advanced, or Expert |
| `query_type` | SQL/reasoning pattern |
| `tables_used` | Names of database tables used by the SQL query |
| `number_of_tables_used` | Number of tables required to answer the question |
| `sql_query` | Executable SQLite query |
| `ground_truth_answer` | Answer generated by running the SQL query on the database |

---

## 3.9 SQL Execution and Ground-Truth Creation

After question generation, the SQL query for each question was executed against the SQLite database. The returned SQL result was stored as the ground-truth answer.

This step was important because it made the benchmark deterministic. The KG pipeline answer can be compared against the SQL answer to check whether the graph-based reasoning is correct.

The SQL validation process checked:

- whether the SQL query executes successfully
- whether the query uses valid tables
- whether the query uses valid columns
- whether the answer can be produced from the database
- whether the stored ground-truth answer matches SQL execution

---

## 3.10 Cross-Checking and Cleaning

The generated question-SQL pairs can be further cross-checked using another LLM such as Gemini. This second model can be used as a reviewer to detect:

- question-SQL mismatch
- invalid SQL logic
- unrealistic question wording
- incorrect table-count labels
- incorrect difficulty labels
- duplicate or near-duplicate questions
- empty or suspicious ground-truth answers

After review, problematic rows can be corrected, removed, or regenerated.

This gives the following overall lifecycle:

```text
Seed questions from Questions.md
        ↓
Schema-grounded LLM generation
        ↓
535 raw question-SQL pairs
        ↓
SQLite execution
        ↓
SQL-derived ground-truth answers
        ↓
Cross-checking and semantic audit
        ↓
Clean benchmark set for KG/AOP evaluation
```

---

## 3.11 Why This Approach Is Suitable for KG/AOP Evaluation

This approach is useful for KG pipeline evaluation because it tests more than simple SQL lookup.

The benchmark includes:

- simple single-table questions
- two-table relationship questions
- multi-hop questions across three or more tables
- temporal questions
- quantitative scoring questions
- rule-based questions
- risk detection questions
- comparative questions

This variety is important because a KG pipeline should be evaluated on whether it can:

1. identify the correct entity
2. retrieve the correct metadata or primitive
3. traverse related nodes and edges
4. perform multi-hop reasoning
5. generate the correct graph query or equivalent reasoning path
6. return an answer consistent with SQL ground truth

In particular, the multi-table and multi-step comparative questions are valuable because they better represent the kind of linked-entity reasoning where a knowledge graph can provide an advantage over flat table lookup.

---

## 3.12 Paper-Ready Summary Paragraph

The following paragraph can be used directly in the research paper:

```text
We constructed a SQL-grounded benchmark of 535 wealth-management questions using an LLM-assisted generation process. A manually curated set of seed question patterns from Questions.md was used to define the main business intents, including investor status checks, batch status analysis, enrichment queries, risk detection, scoring, reference-rule checks, temporal transaction analysis, and multi-step comparative reasoning. The LLM was provided with the SQLite database schema, table descriptions, category requirements, difficulty labels, query-type requirements, and table-hop constraints. For each generated question, the model produced a natural language question, difficulty label, query type, tables used, number of tables used, executable SQLite SQL, and a ground-truth answer obtained by executing the SQL query on the database. This process produced a benchmark that supports deterministic evaluation of the KG/AOP pipeline by comparing graph-derived answers with SQL-derived ground truth.
```

---

## 3.13 Short Version for Methodology Section

```text
The benchmark was generated using a controlled LLM-assisted process. First, representative seed questions were collected from Questions.md. Second, the LLM was given the actual SQLite schema and table descriptions. Third, questions were generated category-wise with explicit requirements for difficulty, query type, and number of tables used. Fourth, each question was paired with an executable SQLite query. Finally, the SQL was executed on the database to create the ground-truth answer. The resulting raw benchmark contained 535 questions across eight wealth-management reasoning categories.
```

