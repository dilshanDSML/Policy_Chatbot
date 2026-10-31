# PolicyBot sample data and eval kit

All content is fictional (Acme Technologies Pvt. Ltd.). Amounts use "Rs." because standard PDF fonts have no rupee sign.

## Files

| File | Type | What it tests |
|---|---|---|
| `documents/01_leave_policy_v1.docx` | DOCX, headings, 1 table | Section chunking, table parsing, part-time rules |
| `documents/01_leave_policy_v2.docx` | DOCX | Incremental indexing: only section 2.1 (Casual Leave) differs from v1 |
| `documents/02_travel_expense_policy.pdf` | PDF, headings, 1 table | PDF parsing, hotel-limit table, citations with page numbers |
| `documents/03_it_security_policy.docx` | DOCX | Passwords, laptops, data rules |
| `documents/04_code_of_conduct.pdf` | PDF | Notice period, harassment, gifts |
| `eval/dataset.json` | JSON | 10 in-scope, 5 not-in-docs, 3 off-topic, 2 multi-turn |
| `eval/incremental_test.json` | JSON | Expected result of uploading v1 then v2 |
| `eval/groq_judge.py` | Python | Groq as the DeepEval judge |
| `eval/bot_adapter.py` | Python | `ask_bot()` to wire to the pipeline |
| `eval/run_deepeval.py` | Python | Runs the 5 metrics and the refusal checks |

## Test the incremental indexing

1. Upload all documents, using `01_leave_policy_v1.docx` for the leave policy.
2. Upload `01_leave_policy_v2.docx` as a new version of the same document.
3. Expected log: 1 chunk added, 1 chunk deactivated, all others skipped. If your chunker merges short sections, the merged chunk that contains section 2.1 is the one that changes.
4. Ask "Can I carry forward my unused casual leaves to next year?" before and after v2. The answer must change from No to Yes (up to 5), which also proves the cache was cleared.

The document header is identical in v1 and v2 on purpose. Set the version and effective date in the upload form, not in the file.

## Run the evaluation

1. Copy `eval/` into the project and implement `ask_bot()` in `eval/bot_adapter.py`. It must return the answer and the retrieved chunk texts.
2. `export GROQ_API_KEY=...`
3. Check the setup without the bot or the judge: `python eval/run_deepeval.py --dry-run`
4. Run each retrieval config, then compare:

```
python eval/run_deepeval.py --config vector_only
python eval/run_deepeval.py --config hybrid
python eval/run_deepeval.py --config hybrid_rerank
python eval/run_deepeval.py --compare
```

Results go to `eval/results/` (per-case scores with the judge's reasons, averages, pass rates, refusal accuracy, and `comparison.md`).

The expected answers match both versions of the leave policy, so the dataset works with v1 or v2 uploaded.
