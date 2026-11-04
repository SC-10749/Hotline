# Northstar Logistics RAG Evaluation

This is a real-model evaluation run using the Northstar Logistics fixture document,
SiliconFlow `BAAI/bge-m3` embeddings, pgvector, and the configured DeepSeek judge/chat model.

## Results

- 5 questions, 2 prompt variants, 10 scored samples, 0 collection errors.
- `current`: faithfulness 0.950, context precision 1.000, answer relevancy 0.777.
- `cited`: faithfulness 0.850, context precision 1.000, answer relevancy 0.745.
- The cited prompt's source-citation output check passed 5/5.

These scores validate the end-to-end path, not broad retrieval quality: the fixture is
small and produced one indexed chunk, so the run does not meaningfully test ranking among
multiple candidate chunks. The runtime `fileId` and generated vectors belonged to a
temporary local database and are not reusable.

## Re-run

1. Configure local model and embedding credentials in the ignored `.env`; never commit them.
2. Start a local pgvector instance and configure `DODO_VECTOR_*` and
   `DODO_VECTOR_DIMENSION=1024`.
3. Upload `eval/fixtures/northstar-logistics/northstar-logistics-policy.md` through the
   Hotline `/file/upload` endpoint and copy the returned `fileId`.
4. Replace `REPLACE_WITH_UPLOADED_FILE_ID` in `eval/fixtures/northstar-logistics/cases.jsonl`
   with that ID, then run:

```powershell
uv run python eval/collect.py --cases eval/fixtures/northstar-logistics/cases.jsonl --prompt current,cited
eval/.venv/Scripts/python.exe eval/score.py --samples "eval/runs/<run-id>/samples.jsonl"
```

The committed report, samples, and scores preserve the completed run. Re-running the
commands produces new outputs and may yield different model-judge scores.
