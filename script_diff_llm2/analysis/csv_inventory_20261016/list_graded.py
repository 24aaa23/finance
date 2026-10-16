"""List every audited graded CSV with a run heading and strict match rate."""
from pathlib import Path
import csv,json,collections
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
csv.field_size_limit(100_000_000)
files=json.loads((OUT/'inventory.json').read_text())['files']
models={'gpt_oss_120b':'GPT-OSS 120B','deepseek_v3_2':'DeepSeek V3.2','gemma_3_27b_it':'Gemma 3 27B IT','qwen3_coder_480b':'Qwen3 Coder 480B'}
legacy_models={'deepseek.v3.2-abhinav':'DeepSeek V3.2','google.gemini-3.6-flash-aman':'Gemini 3.6 Flash','google.gemma-3-27b-it-aman':'Gemma 3 27B IT','mistral.mistral-large-3-675b-instruct-aman':'Mistral Large 3 675B','nvidia.nemotron-super-3-120b-aman':'Nemotron Super 3 120B','openai.gpt-oss-120b-aman':'GPT-OSS 120B','qwen.qwen3-coder-480b-a35b-instruct-aman':'Qwen3 Coder 480B','qwen.qwen3-vl-235b-a22b-instruct-aman':'Qwen3 VL 235B'}

def title(rel):
    p=Path(rel);parts=p.parts;name=p.name
    if parts[0]=='analysis':return 'Derived backend-pattern analysis of the GPT-OSS 442-question semantic-fix training report (not an independent run)'
    if parts[0]=='historical_models':
        model=legacy_models.get(parts[1],parts[1]);mode=parts[2];split=parts[3]
        grader='GPT-5.6 Sol direct regrade' if 'direct_llm_gpt_5_6_sol' in name else 'GPT-OSS grader check' if 'gptoss_grader_check' in name else 'original grading (grader not identified by filename)'
        return f'Historical {model}, {mode} mode, {split} split — {grader}'
    if 'improvement10_models' in parts:
        return f'Improvement 10 SQL-only — {models.get(parts[3],parts[3])}, four-worker run; grader 2 / GPT-5 mini'
    if 'improvement11_gpt_oss_120b' in parts:return 'Improvement 11 KG-only — Azure GPT-OSS 120B, eight-worker continuation; grader 2 / GPT-5 mini (partial grading)'
    if 'neowealth_hybrid' in parts:
        if 'merged_full_context_repairs' in parts:return 'NeoWealth Gemini hybrid — final combined adaptive result after full-context repairs'
        if 'merged_context_repairs' in parts:return 'NeoWealth Gemini hybrid — combined original run and initial context error repairs'
        return 'NeoWealth Gemini hybrid — 321 previously PARTIAL/MISMATCH questions retried with all 22 context documents'
    if 'v5_test1000' in parts:
        model=models.get(parts[3],parts[3]);context='with context' if parts[4]=='with_context' else 'without context'
        variant='early run_01' if parts[5]=='run_01' else 'reliability_v6_01'
        grader='grader 3 / GPT-5 mini' if 'grader3' in name else 'grader 2 / GPT-5 mini'
        return f'Main hybrid — {model}, {context}, {variant}; {grader}'
    if parts[0]=='outputs':
        if 'test1000' in parts:
            if 'context_v5_01' in parts:return 'GPT-OSS hybrid context_v5_01 — '+('GPT-5 mini grading' if 'mini' in name else 'Terra grading, five-row fragment')
            for version in ('v1_20261003','v2_20261003','v4','v5'):
                if 'generic_no_rules_'+version in parts:return f'GPT-OSS generic no-rules hybrid {version} — Terra grading'
            if any(x.startswith('rerun_20261003') for x in parts):return 'GPT-OSS early rerun 2026-10-03 02:31:43 — Terra, partial report'
            if 'rerun_grader2' in name:return 'GPT-OSS original 1,000-query rerun — grader 2 file'
            return 'GPT-OSS original 1,000-query test — direct LLM Terra grading'
        train={
            'graded_openai_gpt_oss_120b_all_final605_terra.csv':'Original final605 training variant — Terra',
            'graded_openai_gpt_oss_120b_all_train_442_ab2_regraded.csv':'442-question training ab2 variant — regraded',
            'graded_openai_gpt_oss_120b_all_train_442_ab2_terra.csv':'442-question training ab2 variant — Terra',
            'graded_openai_gpt_oss_120b_all_train_442_semantic_ab_terra.csv':'442-training semantic ablation — 30-row fragment, Terra',
            'graded_openai_gpt_oss_120b_all_train_442_semanticfix_terra.csv':'442-question training semantic fix — Terra',
            'graded_openai_gpt_oss_120b_all_train_442_semanticfix_v2_terra.csv':'442-question training semantic fix v2 — Terra',
            'graded_openai_gpt_oss_120b_all_train_442_terra.csv':'Original 442-question training run — Terra',
            'graded_openai_gpt_oss_120b_all_train_442_terra_ab1.csv':'442-training ab1 variant — 78-row fragment, Terra',
            'graded_openai_gpt_oss_120b_all_train_442_terra_ab14.csv':'442-question training ab14 variant — Terra',
            'graded_pipeline_605_fast_terra.csv':'605-question fast training variant — Terra',
            'graded_pipeline_605_final_direct_llm_terra.csv':'605-question final training run — direct LLM Terra',
            'graded_pipeline_605_final_semantic_terra.csv':'605-question final semantic training variant — Terra',
            'graded_pipeline_605_final_terra.csv':'605-question final training run — Terra'}
        return 'GPT-OSS '+train.get(name,name)
    return rel

rows=[]
for record in files:
    if record['kind']!='graded':continue
    p=ROOT/record['path'];counter=collections.Counter();n=0
    with p.open(newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            n+=1
            label=r.get('Original Grade') or r.get('Graded Status') or r.get('New Status') or ''
            counter[str(label).strip().upper()]+=1
    rows.append({'id':f'G{len(rows)+1:02}','heading':title(record['path']),'path':record['path'],
                 'absolute_path':str(p),'rows':n,'matches':counter['MATCH'],'match_accuracy_percent':round(counter['MATCH']*100/n,2) if n else None,
                 'partials':counter['PARTIAL'],'mismatches':counter['MISMATCH'],'other_rows':n-counter['MATCH']-counter['PARTIAL']-counter['MISMATCH']})
with (OUT/'all_graded_csvs.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
lines=['# All graded CSVs — run descriptions and match accuracy','',
       f'**{len(rows)} graded CSVs** under `script_diff_llm2`, including one derived analysis extract. No files changed or deleted.',
       '', '**Accuracy = MATCH rows / all rows currently saved in that file × 100.** PARTIAL and errors are not matches; grader errors remain in the denominator. Partial reports are not full-benchmark accuracy. Historical graders, datasets and modes differ, so these percentages are not a controlled ranking. Descriptions use folder/filename identity; unknown historical graders are explicitly marked.','',
       'The NeoWealth final combined accuracy is adaptive recovery, not a single-pass full-context experiment. The 321-row result is a selected failure subset. The backend-pattern extract is derived analysis, not a new run.','',
       '| ID | One-line run heading | MATCH / saved rows | Match accuracy |','|---|---|---:|---:|']
for r in rows:lines.append(f"| {r['id']} | [{r['heading']}]({r['absolute_path']}) | {r['matches']}/{r['rows']} | {r['match_accuracy_percent']:.2f}% |")
lines+=['','## File-by-file paths','']
for r in rows:
    lines += [f"### {r['id']} — {r['heading']}",'',f"**Match accuracy: {r['match_accuracy_percent']:.2f}% ({r['matches']}/{r['rows']}).** PARTIAL: {r['partials']}; MISMATCH: {r['mismatches']}; other/error statuses: {r['other_rows']}.",'',f"[Open graded CSV]({r['absolute_path']})",'',f"`{r['path']}`",'']
(OUT/'ALL_GRADED_RESULTS.md').write_text('\n'.join(lines)+'\n')
print('Created',len(rows),'graded-file descriptions with recomputed accuracy.')
for r in rows:print(r['id'],r['heading'],f"{r['matches']}/{r['rows']}",f"{r['match_accuracy_percent']:.2f}%")
