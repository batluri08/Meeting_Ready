# Evaluation

How we prove it is safe to run: score briefings against a hand-written answer key, plant problems in the
data, and attack it. Run from `backend`:

```
uv run python -m eval.run           # offline: free, deterministic (also part of the test suite)
uv run python -m eval.run --live    # Opus 5.5 + Haiku 5.5, about $1
```

Results are saved to `backend/eval/results/latest-<mode>.json` and shown on the app's Evaluation page.

## What is tested, step by step

| Step | Test |
|---|---|
| Ingestion and client matching | The 16 planted problems in [DATA.md](DATA.md) |
| Search | 22 hand-labelled questions: hit@1, hit@5, recall@5, MRR |
| Rules and numbers | Flags match the answer key; every cited SQL re-runs to the same rows; key figures recomputed from the raw CSVs |
| Writer and verifier | 47-fact answer key ([eval/gold](../backend/eval/gold)); every sentence cited; RAGAS-style faithfulness judged by Haiku |
| Access and privacy | Analyst outputs, prompts and logs scanned for restricted data and personal names |
| Chat | 4 trick questions (leak every client, "admin mode", DROP TABLE, look-alike client); answer relevancy vs ideal answers |
| Failure | One agent forced to fail: its section says unavailable, the rest completes |

## Latest live results (23/23 checks, 16/16 problems handled)

| Check | Target | Result |
|---|---|---|
| Sentences with a valid citation | 100% | 249/249 |
| Unsupported sentences shown | 0 | 0 |
| Cited SQL re-runs to the same rows | 100% | 117/117 |
| Importance flags match the answer key | exact | 10, none on background clients |
| Answer-key facts found | 100% | 47/47 |
| Wrong merges / missed aliases | 0 | 0 / 0 |
| Restricted or personal data leaks | 0 | 0 |
| Prompt-injection successes | 0 | 0 |
| Conflicts flagged | all | 4/4 |
| Claims supported by their source (RAGAS, Haiku judge) | ≥ 95% | 97% (399/412) |
| Chat answer relevancy | ≥ 90% of ideal | 98% |
| Briefing search: right document in top 5 | ≥ 95% | 100% (recall@5 99%) |
| Chat search: right document first | ≥ 90% | 96% (MRR 0.977) |
| Time and cost per briefing | tracked | 58 s, $0.18 |

Offline mode: 21/21 (the two RAGAS checks need a model).

## Search: why hybrid for briefings, reranker for chat

| Method | Right doc first | Recall@5 | Time |
|---|---|---|---|
| Keyword only (BM25) | 95% | 91% | 1 ms |
| Meaning only (vectors) | 86% | 97% | 32 ms |
| **Hybrid (briefings)** | 86% | **99%** | 32 ms |
| **Hybrid + Jina reranker (chat)** | **96%** | 96% | 0.9 s |

A briefing gathers many passages, so recall matters most; chat answers one question, so the first result
matters most.

## In production

Offline evaluation as a CI gate on every change; live evaluation on every prompt, model or tool change;
RAGAS judge on a 5% sample of real briefings; analyst edits and approvals grow the answer key.
