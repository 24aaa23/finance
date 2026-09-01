This directory contains canonical SQL assets for the shared pipeline.

- `wealth_management_diverse/asset.yaml`
  - logical entry point for the SQLite benchmark asset
  - tells the runtime where the physical database lives

- `wealth_management_diverse/schema_notes.yaml`
  - human-readable notes about the physical SQLite schema
  - intended to make the SQL side discoverable without reading code first

The historical experiment directories still keep the physical `.db` file so
older runners continue to work. The canonical runtime reads the SQL asset
manifest from this folder.
