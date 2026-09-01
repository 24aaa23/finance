#!/usr/bin/env python3
import csv
import html
import json
from pathlib import Path


BASE = Path(__file__).resolve().parent
FILES = [
    "Gemma_vs_QwenOld_DAG_SPARQL.csv",
    "Pipeline_Retest_Report_gemma4_12b_all.csv",
    "Pipeline_Retest_Report_gemma4_e4b_all.csv",
]


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    headers = [h.strip() for h in rows[0]]
    return headers, rows[1:]


datasets = {}
for name in FILES:
    path = BASE / name
    if path.exists():
        headers, rows = read_csv(path)
        datasets[name] = {"headers": headers, "rows": rows}

html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CSV Viewer</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f7f8fa;
    --panel: #ffffff;
    --text: #1f2937;
    --muted: #667085;
    --border: #d0d5dd;
    --accent: #1264a3;
    --header: #eef4ff;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #101418;
      --panel: #171c22;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --border: #343b45;
      --accent: #7cc4ff;
      --header: #1d2a38;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
  }}
  .toolbar {{
    position: sticky;
    top: 0;
    z-index: 10;
    display: grid;
    gap: 10px;
    grid-template-columns: minmax(220px, 1fr) minmax(180px, 320px);
    padding: 12px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
  }}
  select, input, button {{
    min-height: 36px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    background: var(--panel);
    color: var(--text);
    font: inherit;
  }}
  .meta {{
    padding: 10px 12px;
    color: var(--muted);
  }}
  .columns {{
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 0 12px 10px;
  }}
  .columns label {{
    white-space: nowrap;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 8px;
    background: var(--panel);
  }}
  .table-wrap {{
    height: calc(100vh - 138px);
    overflow: auto;
    border-top: 1px solid var(--border);
  }}
  table {{
    border-collapse: separate;
    border-spacing: 0;
    min-width: 100%;
  }}
  th, td {{
    border-right: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    max-width: 360px;
    min-width: 140px;
    padding: 8px 10px;
    text-align: left;
    vertical-align: top;
  }}
  th {{
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--header);
    font-weight: 650;
  }}
  td {{
    background: var(--panel);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }}
  td.long {{
    max-height: 160px;
    overflow: auto;
  }}
  tr.hidden, .col-hidden {{
    display: none;
  }}
  @media (max-width: 700px) {{
    .toolbar {{ grid-template-columns: 1fr; }}
    .table-wrap {{ height: calc(100vh - 180px); }}
  }}
</style>
</head>
<body>
  <div class="toolbar">
    <select id="fileSelect" aria-label="CSV file"></select>
    <input id="search" type="search" placeholder="Search rows">
  </div>
  <div class="meta" id="meta"></div>
  <div class="columns" id="columns"></div>
  <div class="table-wrap">
    <table id="table"></table>
  </div>
<script>
const DATASETS = {json.dumps(datasets)};
const fileSelect = document.getElementById('fileSelect');
const search = document.getElementById('search');
const columns = document.getElementById('columns');
const table = document.getElementById('table');
const meta = document.getElementById('meta');
let active = Object.keys(DATASETS)[0];
let visible = new Set();

for (const name of Object.keys(DATASETS)) {{
  const option = document.createElement('option');
  option.value = name;
  option.textContent = name;
  fileSelect.appendChild(option);
}}

function renderColumns(headers) {{
  columns.replaceChildren();
  visible = new Set(headers.map((_, index) => index));
  headers.forEach((header, index) => {{
    const label = document.createElement('label');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = true;
    checkbox.addEventListener('change', () => {{
      checkbox.checked ? visible.add(index) : visible.delete(index);
      table.querySelectorAll(`[data-col="${{index}}"]`).forEach(cell => {{
        cell.classList.toggle('col-hidden', !checkbox.checked);
      }});
    }});
    label.append(checkbox, ' ', header || `Column ${{index + 1}}`);
    columns.appendChild(label);
  }});
}}

function renderTable() {{
  const dataset = DATASETS[active];
  const headers = dataset.headers;
  const rows = dataset.rows;
  meta.textContent = `${{rows.length}} rows, ${{headers.length}} columns`;
  renderColumns(headers);
  table.replaceChildren();
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  headers.forEach((header, index) => {{
    const th = document.createElement('th');
    th.dataset.col = index;
    th.textContent = header || `Column ${{index + 1}}`;
    headRow.appendChild(th);
  }});
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  rows.forEach(row => {{
    const tr = document.createElement('tr');
    tr.dataset.search = row.join(' ').toLowerCase();
    headers.forEach((_, index) => {{
      const td = document.createElement('td');
      td.dataset.col = index;
      const value = row[index] || '';
      td.textContent = value;
      if (value.length > 160) td.classList.add('long');
      tr.appendChild(td);
    }});
    tbody.appendChild(tr);
  }});
  table.appendChild(tbody);
  filterRows();
}}

function filterRows() {{
  const needle = search.value.trim().toLowerCase();
  table.querySelectorAll('tbody tr').forEach(row => {{
    row.classList.toggle('hidden', needle && !row.dataset.search.includes(needle));
  }});
}}

fileSelect.addEventListener('change', () => {{
  active = fileSelect.value;
  search.value = '';
  renderTable();
}});
search.addEventListener('input', filterRows);
renderTable();
</script>
</body>
</html>
"""

(BASE / "csv_viewer.html").write_text(html_doc, encoding="utf-8")
print(BASE / "csv_viewer.html")
