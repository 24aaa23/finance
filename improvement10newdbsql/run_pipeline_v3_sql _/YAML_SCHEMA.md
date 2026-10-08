# YAML schema input

Planning schema is loaded from `improvement8/table_medatada` by default. Pass
`--yaml-dir PATH` to use another external folder. The same
folder supplies the domain agent's YAML documents. Both `.yaml` and `.yml` files
are supported. The schema loader never opens SQLite or falls back to discovery.

Each physical table needs `identity.id` equal to its exact SQL table name and an
`attributes` list containing exact column names and explicit types. Descriptions,
synonyms, allowed values and derived attributes remain domain documentation;
derived attributes are not added as stored columns.

```yaml
identity:
  id: Accounts
attributes:
  - name: id
    type: string
  - name: amount
    type: decimal
  - name: opened_on
    type: date
```

String and date/time types use TEXT metadata; integer/boolean use INTEGER;
decimal/numeric use NUMERIC; float/real/double use REAL. These are YAML type
mappings, not claims about an inspected database. No DDL is invented.

Constraints are optional explicit top-level declarations:

```yaml
primary_keys: [id]
unique_keys: [[external_id]]
foreign_keys:
  - columns: [owner_id]
    target_table: Owners
    target_columns: [id]
```

All referenced tables and columns must exist in the YAML schema. Only add these
declarations when they are known to be correct. A column can also declare
`nullable: true` or `nullable: false`. Missing constraints/nullability remain
unknown; prose such as "unique identifier" is not interpreted as a constraint.

Files with `identity.subtype: Context` remain knowledge-only by default.
`schema: {physical: true}` explicitly makes one a physical table;
`schema: {physical: false}` excludes any document from the SQL schema. These
documents are still available to the domain agent.

Check files without a database or API call:

```powershell
python "improvement8/run_pipeline_v3_sql _/run.py" --check-inputs --yaml-dir improvement8/table_medatada
```

Knowledge preparation also supports `--yaml-dir` without `--db`. Normal pipeline
runs default to `improvement8/wealth_management_diverse.db` for execution; pass
`--db PATH` to select a replacement database. Schema/document changes invalidate the
knowledge cache automatically; the next preparation/run compiles a fresh pack.
Keep YAML synchronized with the database: the loader cannot detect undocumented
tables, columns or changes in the live database.
