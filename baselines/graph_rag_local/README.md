# GraphRAG local-retrieval baseline

This baseline builds a local SQLite/FTS index from the RDF graph. Every
question retrieves a bounded RDF neighborhood and makes one answer-generation
call over that evidence. It does not use Fuseki.

From the repository root:

```bash
python baselines/graph_rag_local/run_pipeline.py build-index
python baselines/graph_rag_local/run_pipeline.py run
```

The index and resumable output are written under `output/`. The final
1,000-question graded report is in `../results/`.
