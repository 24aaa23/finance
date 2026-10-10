"""Render separate descriptive analyses from the read-only summary."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
S=json.loads((Path(__file__).parent/'summary.json').read_text())
R=S['runs'];P=S['pairs'];DOC=ROOT/'docs'
MODELS={'gpt_oss_120b':'GPT-OSS 120B','deepseek_v3_2':'DeepSeek V3.2','gemma_3_27b_it':'Gemma 3 27B IT','qwen3_coder_480b':'Qwen3 Coder 480B'}
ORDER=list(MODELS)
def table(head,rows):
 return '| '+' | '.join(head)+' |\n| '+' | '.join(['---']*len(head))+' |\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in rows)+'\n'
def pct(n,d=1000):return f'{100*n/d:.1f}%'
def run(f,m,c='with_context'):return R[f'{f}/{m}/{c}']
def accuracy_rows(f,models,conditions):
 rows=[]
 for m in models:
  for c in conditions:
   r=run(f,m,c);g=r['grades'];success=r['raw_statuses'].get('PIPELINE_SUCCESS',0)
   rows.append([MODELS[m],c.replace('_',' '),g.get('MATCH',0),g.get('PARTIAL',0),g.get('MISMATCH',0),1000-sum(g.get(x,0) for x in ['MATCH','PARTIAL','MISMATCH']),pct(g.get('MATCH',0)),pct(success)])
 return table(['Model','Condition','MATCH','PARTIAL','MISMATCH','Other labels','Match rate','Execution success'],rows)
def types(f,models,c='with_context'):
 names=list(run(f,models[0],c)['types'])
 rows=[]
 for t in names:
  n=run(f,models[0],c)['types'][t]['n']
  rows.append([t,n,*[pct(run(f,m,c)['types'][t]['match'],n) for m in models]])
 return table(['Query type','Questions',*[MODELS[m] for m in models]],rows)
intro='''Snapshot: 8 October 2026. These reports analyze existing completed experiments; no raw answers or grader labels were modified. Accuracy means full MATCH divided by all 1,000 benchmark questions; PARTIAL does not count as a match. PIPELINE_SUCCESS means operational execution, not semantic correctness. Grader 2 using GPT-5 mini is the common evaluation basis. Other labels include execution and grading failures and are not one homogeneous category. Current incomplete Azure experiments and the newly added decomposition retries are outside this analysis.\n\n'''
a='# Improvement10: results, findings and limitations\n\n'+intro
a+='''## 1. What this experiment tests

Improvement10 is a domain-conditioned SQL pipeline. Its original workflow combines query understanding, retrieval-oriented specifications/decomposition, SQL retrieval, intermediate processing and a Python Final Spec for final composition/calculation. An agent compiles the supplied domain prompt, business-rules addendum and table YAML documents; consultation can also access original documents. All four model experiments use context. There is no completed Improvement10 without-context control in this comparison.

The original snapshot is commit `9ce5a6d99c96f3c17dda0b98ec8edc0c11bd2380`. Model/provider and path adapters are external. These are the existing `run_01/parallel_workers4` results, not the newer Improvement10/11 hybrid derivative.

## 2. Overall performance

'''+accuracy_rows('improvement10',ORDER,['with_context'])
a+='''GPT-OSS is the strongest aggregate model here, followed by DeepSeek, Qwen and Gemma. The gap is 3.7 percentage points between GPT-OSS and DeepSeek, 7.7 points between GPT-OSS and Qwen, and 46.2 points between GPT-OSS and Gemma. This describes these runs, not intrinsic model capability or an effect of parameter count alone.

Grading remains incomplete in a narrower sense: every output contains 1,000 rows, but 5 GPT-OSS, 4 DeepSeek, 2 Gemma and 22 Qwen rows have GRADER_API_ERROR. If every unresolved API-error row became a match, the respective upper bounds would be 78.6%, 74.8%, 32.1% and 72.6%. These bounds leave the aggregate ranking unchanged. OTHER and CRASH are separate statuses and are not assumed recoverable grading errors.

## 3. Execution reliability and semantic correctness

'''
rows=[]
for m in ORDER:
 r=run('improvement10',m);st=r['raw_statuses'];n=st.get('PIPELINE_SUCCESS',0)
 rows.append([MODELS[m],n,st.get('FINAL_SPEC_ERROR',0),st.get('QUERY_SPEC_ERROR',0),st.get('DECOMPOSITION_ERROR',0),st.get('CRASH',0),pct(r['matches_among_successes'],n)])
a+=table(['Model','Executed','Final Spec failures','QuerySpec failures','Decomposition failures','Crashes','MATCH among executed'],rows)
a+='''Final Spec is the major execution bottleneck. Gemma fails there on 429 questions, and on another 41 at QuerySpec/decomposition. Even a simple retrieval can fail because the generated processing plan uses invalid dataset names, unsupported operations or fields that were not preserved in intermediate datasets. This is a structured-plan compatibility problem, not evidence that Gemma cannot retrieve a name from SQL.

GPT-OSS executes 97.4% of questions, but only 80.2% of those executions receive MATCH. For this model, most remaining loss is in the meaning, population or output of executable plans. DeepSeek and Qwen also have substantial executed-but-not-matching outputs. A successful Python plan can still implement the wrong calculation.

Gemma has two bottlenecks: 47% of queries do not execute successfully, and only 60.2% of successful executions match. Fixing plan validity alone would not remove all its errors. Conditional rates include unresolved grading errors and select different successful subsets for each model.

## 4. Query-type trends

'''+types('improvement10',ORDER)
a+='''Straightforward tasks are not uniformly easy across models. DeepSeek answers all 34 direct-retrieval questions correctly, and GPT-OSS answers 32. Gemma answers only two, with inspected failures showing Final Spec/schema errors. Thus complexity of the orchestration contract can dominate simplicity of the user's question.

Ranking is a relative strength: GPT-OSS matches 62/65 and DeepSeek 61/65. A plausible explanation is that a well-defined metric, sort direction and limit provide a clearer execution target than a multi-stage comparison. This is an interpretation; the table alone does not identify the cause.

Multi-step comparative questions are a persistent weakness: GPT-OSS matches 14/55, DeepSeek 20/55, Qwen 30/55 and Gemma 1/55. They demand correct population selection, intermediate grain and ordered computations. More individually plausible steps create more opportunities to lose fields or change aggregation meaning. Qwen leads this category despite ranking below GPT-OSS overall.

Temporal questions show another specialization: DeepSeek and Qwen each match 39/40, GPT-OSS 33/40 and Gemma 10/40. Reference compliance is less reliable across all models. Small categories, particularly the 15-question Comparative group, should not support broad population-level conclusions.

## 5. Expert questions and partial answers

'''
a+=table(['Model','Expert MATCH / 127','Expert match rate','Expert PARTIAL'],[[MODELS[m],run('improvement10',m)['difficulty']['Expert']['match'],pct(run('improvement10',m)['difficulty']['Expert']['match'],127),run('improvement10',m)['difficulty']['Expert']['partial']] for m in ORDER])
a+='''Qwen has the highest Expert match rate, 59.1%, although GPT-OSS has the highest overall rate. GPT-OSS reaches 50.4%, DeepSeek 41.7% and Gemma 3.9%. Aggregate accuracy therefore conceals substantial model specialization and severe difficulty-specific failure.

DeepSeek has 155 PARTIAL labels, more than its 97 MISMATCH labels. Many partial outputs may be nearer a complete answer, but PARTIAL is not a calibrated measure of distance from correctness. Inspected grader explanations repeatedly mention duplicate investors and missing requested fields. In other cases the correct row appears among unrelated rows. These errors suggest entity grain, filter placement and projection completeness as useful diagnostic targets.

## 6. Concrete failure mechanisms

These examples are evidence-backed illustrations, not a frequency-coded taxonomy:

- **Lost fields between stages:** Qwen's WM125-1T-002 fails because final projection references risk_tolerance/time_horizon absent from the selected input. Gemma's WM125-1T-001 also combines invalid dataset naming with a missing investor_name field.
- **Incorrect aggregate contract:** DeepSeek's WM125-2T-028 fails because investor_count does not preserve outer count_distinct. Gemma's WM125-1T-003 attempts an aggregate without a nonempty aggregation list.
- **Wrong final grain:** GPT-OSS's ARC125-3T-009 fails Final Spec because grouping differs from the interpreted investor_id/investor_name grain.
- **Row multiplication:** DeepSeek's WM125-3T-026 includes all required investors but duplicates two; Gemma and Qwen also have repeated-investor partials. Joins over multiple child records can multiply rows when final entity uniqueness is not preserved.
- **Filters not applied to the final output:** GPT-OSS's WM125-1T-023 includes the correct investor's scores plus many unrelated rows. Correct retrieval somewhere inside the plan is insufficient if final composition ignores the intended population.

These explain why additional execution retries are not a complete solution: deterministic structural validation, explicit dataset interfaces, population preservation and final output grain matter.

## 7. Runtime, tokens and efficiency

Timing uses summed per-question elapsed seconds, not four-worker wall-clock throughput. Startup compilation and grading are excluded. Token latency below is non-streaming request duration per reported output token; it includes prompt processing, network and queueing, and is not isolated decoding latency.

'''
prices={'gpt_oss_120b':(.15,.60),'deepseek_v3_2':(.28,.42),'gemma_3_27b_it':(.27,.45)}
rows=[]
for m in ORDER:
 r=run('improvement10',m);t=r['tokens'];ms=t['latency_s']*1000/t['output']
 cost=f"${(t['input']*prices[m][0]+t['output']*prices[m][1])/1e9:.6f}" if m in prices else 'Not priced'
 rows.append([MODELS[m],f"{r['mean_seconds']:.3f}",f"{t['calls']/1000:.2f}",f"{t['input']/1000:,.0f}",f"{t['output']/1000:,.0f}",f"{19.702643890678292 if m=='qwen3_coder_480b' else ms:.3f}",cost,f"{r['efficiency']:.6f}"])
a+=table(['Model','Seconds/question','Calls/question','Input tokens/question','Output tokens/question','Request ms/output token','Illustrative cost/question','MATCH / summed second'],rows)
a+='''Costs apply the previously supplied input/output rates per million tokens: GPT-OSS $0.15/$0.60, DeepSeek $0.28/$0.42 and Gemma $0.27/$0.45. They are illustrative normalized estimates, not verified Bedrock invoices. They exclude grading and context preparation. Qwen has no supplied pricing assumption; no cost is invented.

Qwen's token-latency estimate uses the 994 rows with complete reported usage; its full-run elapsed-time efficiency includes all 1,000 rows. Six failed calls have missing token usage, so its recorded token totals are incomplete. The other three runs record no missing-usage calls. Recorded cached-input counts should be considered when translating this normalization into actual provider charges.

Qwen is fastest end to end in this set. GPT-OSS and DeepSeek take about one minute per question on average, while Gemma takes about 80 seconds despite being the smallest model. Gemma averages 8.70 calls/question versus 7.03 GPT-OSS and 6.88 DeepSeek, consistent with greater repair/plan burden. This does not prove calls are the only cause; provider throughput and token generation differ too. Model-request time accounts for nearly all recorded per-question processing time, making inference a more promising latency target than SQLite execution.

## 8. Context provenance and limitations

The context is intentionally database-specific and richer than the main pipeline's terminology-only active pack. However, the supplied business-rules addendum contains evaluation-related corrections, benchmark references and observed cohort information. The existing [context audit](improvement10_context_leakage_audit.md) found no direct reference-answer injection in the inspected planner path, but did identify benchmark-contamination risk and propagation of evaluation-related content into actual compiled rules. The results should not be described as a clean, independently authored business-context experiment.

Other limits are one run per model, one repeatedly used wealth-management development benchmark, unresolved grader errors, model-specific compiled packs, cloud-provider timing effects and no no-context control. No unseen-domain transfer, statistical superiority or causal benefit of business rules follows from this experiment alone. Large-model size does not guarantee correct structured-plan generation, and local privacy does not follow merely from using open weights through a hosted API.

The strongest defensible finding is that Improvement10 works well with GPT-OSS and DeepSeek, but its generated multi-stage processing/Final Spec interfaces are a substantial failure surface, especially for Gemma. Complex comparisons and final row semantics remain weaknesses even where execution succeeds.
'''
(DOC/'improvement10_results_analysis.md').write_text(a)

b='# Main hybrid pipeline: results, findings and limitations\n\n'+intro
b+='''## 1. Scope and architecture

This analysis uses the six completed `reliability_v6_01` experiments: GPT-OSS, DeepSeek and Gemma, each without and with context. Kimi's with-context run is incomplete and the Qwen hybrid outputs have no completed grader-2 report in this comparison; neither is treated as a complete accuracy experiment.

The main pipeline forms a question-dependent DAG of backend subqueries and set operations. Node-local QuerySpec defines the requested computation; SQL/SPARQL performs node calculations, and bindings/set operators coordinate results. Unlike Improvement10's final Python composition plan, much computation is pushed into a backend query. The KG is derived from the same SQL database, so these are alternative representations of shared data.

These historical runs predate the newly implemented three decomposition repairs. Their results cannot be used to claim those repairs improved accuracy. The newer Azure SQL-only and baseline-derived hybrid runs are different, still incomplete experiments.

## 2. Overall performance

'''+accuracy_rows('main_hybrid',ORDER[:3],['without_context','with_context'])
b+='''DeepSeek without context has the highest observed match rate, 80.6%. GPT-OSS remains near 79% in both conditions. Gemma reaches roughly 61%, materially below the larger models. DeepSeek's lead over GPT-OSS without context is 17 questions; without repeated runs this small gap should not be described as stable superiority.

The 1,000-row reports contain one grader API error for GPT-OSS with context and six grader API errors plus one token-output error for Gemma with context. Even if all seven Gemma grading failures became matches, its with-context rate would only rise to 61.6%. Execution failures are included in the denominator; percentages do not silently discard hard questions.

## 3. Context effect: turnover rather than consistent improvement

'''
b+=table(['Model','New MATCH with context','Lost MATCH with context','Both MATCH','Net change'],[[MODELS[m],P[f'context/{m}']['gain'],P[f'context/{m}']['loss'],P[f'context/{m}']['both_match'],P[f'context/{m}']['gain']-P[f'context/{m}']['loss']] for m in ORDER[:3]])
b+='''GPT-OSS gains 67 matches and loses 66, producing an almost unchanged total while 133 question outcomes change. DeepSeek gains 68 and loses 91; Gemma gains 22 and loses 26. Context is therefore not consistently improving this benchmark. Independent generation and grader variation also contribute, so these transitions are associations, not proof that each change was caused by context.

The actual active context matters: previously inspected run states show four GPT-OSS terminology entries, five DeepSeek entries and one Gemma entry. Operational formulas/defaults were not automatically active, and phase0_business_rules.md was quarantined as evaluation-scoped. This is chiefly an experiment with model-specific terminology, not a complete business-rule integration experiment.

Sparse terminology can help map a phrase to the right field, but it does not necessarily establish signed-amount meaning, average-of-averages, entity uniqueness or a multi-stage metric definition. This is a plausible explanation for weak aggregate gains, not a measured causal attribution. Different preparation models also produce different packs, confounding answering capability with context preparation.

## 4. Query-type and difficulty trends

The following table shows without-context / with-context match rates.

'''
rows=[]
for t,d in run('main_hybrid',ORDER[0],'without_context')['types'].items():
 n=d['n'];rows.append([t,n,*[' / '.join(pct(run('main_hybrid',m,c)['types'][t]['match'],n) for c in ['without_context','with_context']) for m in ORDER[:3]]])
b+=table(['Query type','Questions',*[MODELS[m] for m in ORDER[:3]]],rows)
b+='''Direct retrieval is strong for all three models, including Gemma. The difficult categories involve more semantic decisions: composite reasoning, multi-step comparisons and reference compliance. DeepSeek matches 38/55 multi-step comparative questions without context, compared with GPT-OSS 13/55 and Gemma 14/55. GPT-OSS is relatively stronger on ranking and exception detection.

Context helps some categories and hurts others. GPT-OSS composite reasoning increases from 94 to 107 matches, while categorical aggregation falls from 181 to 174 and temporal from 37 to 33. There is no general conclusion that context helps harder questions. Gemma remains at 10/40 temporal matches in both conditions. The query type identifies where to investigate, not the specific cause of every error.

'''
b+=table(['Model','Expert without context / 127','Expert with context / 127'],[[MODELS[m],f"{run('main_hybrid',m,'without_context')['difficulty']['Expert']['match']} ({pct(run('main_hybrid',m,'without_context')['difficulty']['Expert']['match'],127)})",f"{run('main_hybrid',m,'with_context')['difficulty']['Expert']['match']} ({pct(run('main_hybrid',m,'with_context')['difficulty']['Expert']['match'],127)})"] for m in ORDER[:3]])
b+='''Expert questions remain materially weaker than the aggregate rate. Difficulty labels need not be monotonic because their query-type compositions differ; the evidence supports an Expert-group weakness, not a fixed accuracy penalty for every increase in difficulty.

## 5. Execution failures versus wrong executable answers

'''
rows=[]
for m in ORDER[:3]:
 for c in ['without_context','with_context']:
  r=run('main_hybrid',m,c);n=r['raw_statuses']['PIPELINE_SUCCESS'];contracts=sum(v for k,v in r['failure_stages'].items() if 'Query_Spec_Contract' in k)
  rows.append([MODELS[m],c.replace('_',' '),contracts,1000-n-contracts,n-r['matches_among_successes'],pct(r['matches_among_successes'],n)])
b+=table(['Model','Condition','QuerySpec contract failures','Other raw failures','Executed but not MATCH','MATCH among executed'],rows)
b+='''Gemma's contract failures dominate its execution losses: 192 without context and 189 with context. GPT-OSS has 66/73 such failures and DeepSeek 40/69. A contract failure prevents useful execution; it is different from an executed result graded wrong. GPT-OSS with context has an additional node exception, so its 74 DAG_NODE_ERROR labels are not all QuerySpec contract failures.

DeepSeek loses 29 successful executions with context, exactly alongside the increase from 40 to 69 contract failures; its conditional match rate stays near 86.3%. The observed regression is concentrated in executable specification formation, rather than a large collapse in correctness among executed answers. This arithmetic is descriptive and does not establish why context caused a failure.

## 6. Semantic error patterns

Previously inspected rows and current stage statistics support these mechanisms:

- **Population ownership:** filtering investor profiles by stated goal is not equivalent to filtering all child goal records by that goal type. GPT-OSS WM125-2T-026 illustrates narrowing the records averaged beyond the intended population.
- **Aggregation grain:** counting qualifying rows, counting distinct investors and counting one per grouped investor produce different answers. Gemma's WM125-2T-028/029 examples return investor_count=1 across many rows rather than one total count.
- **Staged measures:** averaging investor-level averages differs from averaging all child rows. Ratios, normalization and ranking can also require explicitly ordered stages.
- **Duplicates:** GPT-OSS WM125-3T-023/026 partial outputs include repeated investor keys. DISTINCT must follow the requested answer grain; indiscriminate deduplication would be wrong for event-level answers.
- **Signed amounts:** re-signing already signed cash flows or subtracting signed outflows can change totals. Definitions need source support rather than question-specific patches.
- **Validation of a mistaken specification:** a query can pass pre-scan validation and return rows matching QuerySpec while QuerySpec itself misrepresents the question. Shape agreement is weaker than semantic correctness.

These are examples, not exhaustive causal counts. Grader explanations also require scrutiny: earlier audits found some partial judgments despite matching entity sets or row multisets. Long outputs, ordering and reference formatting can affect model evaluation. This does not justify relabelling partials wholesale.

## 7. How much hybrid composition actually happens

'''
rows=[]
for m in ORDER[:3]:
 for c in ['without_context','with_context']:
  r=run('main_hybrid',m,c);be=r['node_backends'];rows.append([MODELS[m],c.replace('_',' '),be.get('SQL',0),be.get('KG',0),be.get('KG+SQL',0),r['single_node']])
b+=table(['Model','Condition','SQL only','KG only','Both SQL and KG','Single-node plans'],rows)
b+='''Most recorded plans use SQL, and most contain a single node. Gemma's plans are all SQL; GPT-OSS uses both backends on only 13/7 questions and DeepSeek on 9/9. These are recorded plans, including failed execution, not a guarantee that every backend completed.

A single node is legitimate when one backend can answer the whole question, especially because the KG is derived from SQL. However, these aggregate scores provide limited evidence of successful cross-backend composition. They do not demonstrate that decomposition into multiple agents caused the accuracy advantage.

Historical logs recorded 324/294 fallback events for GPT-OSS, 29/28 for DeepSeek and 3/3 for Gemma, without/with context. Some logs contain resumed attempts, so these are events, not exact unique-query counts. Empty/rejected decompositions do not necessarily mean malformed DAG topology: scope checks can reject proposals before DAG construction. The newly added retry loop addresses those rejected plans; it has not yet been evaluated in the completed runs analyzed here.

## 8. Runtime and measurement limits

'''
rows=[]
for m in ORDER[:3]:
 for c in ['without_context','with_context']:
  r=run('main_hybrid',m,c);rows.append([MODELS[m],c.replace('_',' '),f"{r['mean_seconds']:.3f}",f"{r['efficiency']:.6f}"])
b+=table(['Model','Condition','Mean seconds/question','MATCH / summed execution second'],rows)
b+='''Context increases recorded mean elapsed time by about 3.0% for GPT-OSS, 7.7% for DeepSeek and 27.4% for Gemma. The data do not separate added prompt processing, different node plans, repairs and endpoint variation. Gemma is not the fastest simply because it is smaller.

The historical full hybrid CSVs do not contain model token usage or generation-only timing. Their absent token columns are missing measurements, not zero usage. Later 40-question measurements are samples, not full-run totals; some contained approximately 600-second request stalls. They should not be compared directly to Improvement10's full-run token telemetry as though both were identical measurements. The existing [six-run analysis](six_run_results_analysis.md) gives those sample estimates and sensitivity caveats.

Efficiency here is MATCH divided by summed question elapsed time, following the specified definition. It does not measure wall-clock throughput under parallel workers, and excludes grading and startup context compilation.

## 9. Limitations and defensible findings

The main constraints are one run per condition, one repeatedly analyzed development dataset, sparse/model-dependent context, unresolved grading errors, unequal category sizes, no clean causal decomposition control and few genuinely mixed-backend plans. The composition interface passes values/columns and entity sets; it is not a general arbitrary cross-backend row-join engine. Complicated measures still rely on correctly generated SQL/SPARQL or supported compiler patterns.

No unseen-domain transfer, universal financial-database support or privacy guarantee follows from these results. The KG and SQL share source data, and cloud-hosted open weights still transmit prompts to a provider. Improvement10 context-provenance problems should not be transferred automatically to the main pipeline, but repeated benchmark-driven development also limits held-out generalization claims for the main pipeline.

The evidence supports strong observed accuracy for GPT-OSS and DeepSeek, substantial dependence on query type and specification reliability, a large Gemma gap, and no consistent aggregate benefit from the current terminology context. The priorities are correct population/grain/staged semantics, typed specification reliability and evaluation stability. Additional DAG repairs are a reasonable experiment, not an established improvement.
'''
(DOC/'main_hybrid_results_analysis.md').write_text(b)

c='# Improvement10 versus the main hybrid pipeline: brief comparison\n\n'+intro
c+='''Question IDs, question text and reference-answer text match exactly for the paired GPT-OSS, DeepSeek and Gemma comparisons. All use grader 2 with GPT-5 mini. This makes descriptive question-level comparison possible, but context, execution design, prompt contracts and runtime conditions differ, so this is not an isolated KG/decomposition ablation.

'''
rows=[]
for m in ORDER[:3]:
 a=run('improvement10',m);wo=run('main_hybrid',m,'without_context');wi=run('main_hybrid',m)
 rows.append([MODELS[m],pct(a['grades']['MATCH']),pct(wo['grades']['MATCH']),pct(wi['grades']['MATCH']),f"{(wo['grades']['MATCH']-a['grades']['MATCH'])/10:+.1f} pp",f"{(wi['grades']['MATCH']-a['grades']['MATCH'])/10:+.1f} pp"])
c+=table(['Model','Improvement10','Main without context','Main with context','Main without minus I10','Main with minus I10'],rows)
c+='''The strongest practical gain is Gemma: +29.4 points without context and +29.0 with context. Its execution success also improves from 53.0% to roughly 80%. That is consistent with reducing the fragile generated Python Final Spec interface, although many other changes prevent a causal attribution. Because Gemma uses SQL for all main-pipeline questions, its improvement cannot be credited to actual KG execution.

DeepSeek gains 6.2 points without context and 3.9 with context. Its execution success is slightly lower in the main pipeline (93.5%/90.6% versus 93.9%), but MATCH among successful executions increases from 79.1% to about 86.3%. Its improvement therefore reflects better observed correctness among executable answers, not simply more executions.

GPT-OSS gains only 0.8/0.9 points. Execution success falls from 97.4% to 93.3%/92.4%, while conditional correctness improves from 80.2% to 84.6%/85.5%. Stricter node-local contracts and changed computation paths trade some executability for stronger observed answers among successes; the net accuracy gain is small and should not be advertised as a decisive architecture victory.

Paired without-context comparisons show 107 gains versus 99 losses for GPT-OSS, 158 versus 96 for DeepSeek and 365 versus 71 for Gemma. The systems have complementary strengths; replacing the old pipeline does not improve every question.

The main pipeline has lower recorded mean elapsed time for each shared model: GPT-OSS 33–34 seconds versus 60, DeepSeek 46–50 versus 59, and Gemma 53–68 versus 80. Timing includes failures, endpoint conditions and different planning work; it is not a controlled speedup measurement. Full-run cost cannot be compared fairly because historical main-hybrid token usage was not logged.

Architecturally, Improvement10 retrieves and composes datasets using a generated Python calculation plan; the main pipeline expresses computations in backend queries and coordinates them through an outer DAG. Both already include decomposition. Their contexts are different treatments: Improvement10 uses rich domain/rule/YAML documents with identified contamination risk; completed main-context runs activate sparse terminology and quarantine the evaluation-scoped rules document.

The paper can report the main pipeline's descriptive improvements and reduced sensitivity to Gemma's Final Spec failures. It should not claim that KG composition, business rules or decomposition alone caused those improvements. To establish those claims, use matched context, source data, model/provider, grader and repeated runs, plus explicit backend/decomposition ablations.

Detailed separate reports: [Improvement10](improvement10_results_analysis.md) and [main hybrid](main_hybrid_results_analysis.md).
'''
(DOC/'pipeline_results_comparison.md').write_text(c)
# Provenance tables keep each report directly traceable to actual CSVs.
for file,family in [('improvement10_results_analysis.md','improvement10'),('main_hybrid_results_analysis.md','main_hybrid')]:
 p=DOC/file
 text=p.read_text()+'\n## Artifact provenance\n\nCounts were recomputed by `analysis/completed_experiments_20261008/summarize.py`. Input file hashes, detailed status counts, per-type counts and paired transitions are saved in `analysis/completed_experiments_20261008/summary.json`.\n\n'
 for key,r in R.items():
  if key.startswith(family+'/'):text+=f"- {key}: [raw](../{r['raw_path']}) and [grader 2](../{r['graded_path']}).\n"
 p.write_text(text)
print('Wrote three reports under',DOC)
