# Comprex

**Enterprise AI Context Compressor** — the thin layer between your systems and OpenAI / LangChain.

Comprex swallows 100k+ token dumps (logs, nested JSON, runbooks, warehouse extracts) and returns a 15–20× smaller context **without dropping the facts an LLM needs**. Teams routinely cut **90%+ of input-token spend**. No BERT. No GPU. No transformer weights. Pure algorithms + `tiktoken`.

## Why companies buy this

| Pain | Comprex |
| --- | --- |
| GPT-4o input at $2.50 / 1M tokens | Keep 5–7% of the tokens, keep the meaning |
| Multi-megabyte log + JSON payloads | Sliding-window stream, bounded RAM |
| “Just wait for the compressor” | **0 ms caller latency** — job id, background workers |
| LangChain / OpenAI rewrites | Two-line adapters |

## Install

```bash
pip install -e .
pip install -e ".[openai,langchain,dev]"   # optional extras
```

## Two-line adapters

```python
from openai import OpenAI
from llm_compressor.adapters.openai_compat import wrap_openai_client

client = wrap_openai_client(OpenAI())
```

```python
from langchain_openai import ChatOpenAI
from llm_compressor.adapters.langchain_compat import wrap_langchain

llm = wrap_langchain(ChatOpenAI(model="gpt-4o"))
```

## Python API

```python
from llm_compressor import Compressor, CompressConfig, compress_sync

result = compress_sync(open("incident.json", encoding="utf-8").read())
print(result.ratio, result.text)

engine = Compressor(CompressConfig(target_ratio=18.0))
job = engine.submit(huge_dump)          # returns immediately
# later: engine.job(job.job_id).result
```

`Compressor.compress` never blocks the event loop: CPU work runs in `asyncio.to_thread`. HTTP callers get a job id via `asyncio.create_task` while Recursive Token Squeezing runs in the background.

## HTTP API (zero-latency)

```bash
python -m llm_compressor
```

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/health` | liveness |
| `POST` | `/compress` | **202** + `{ "job_id" }` in ~0 ms |
| `POST` | `/compress/messages` | same, OpenAI chat schema |
| `GET` | `/jobs/{job_id}` | poll status + result |
| `GET` | `/docs` | OpenAPI |

```bash
curl -s -X POST localhost:8080/compress \
  -H 'content-type: application/json' \
  -d '{"text":"...100k tokens of logs..."}'
# {"job_id":"...","status":"queued"}
```

## How it squeezes (3 stages)

1. **Syntactic pruning** — drop DEBUG/TRACE, fillers, empty JSON keys; collapse nested JSON/XML.
2. **Adaptive Semantic Quantization** — UUID, hashes, paths, ARNs, IPs become `[u1]` / `[h2]` / `[p3]` with a dynamic substitution map.
3. **Recursive TextRank + BM25** — greedy pack by score, Jaccard de-dupe, 15–20× band enforcement. Giant payloads are processed as a **sliding window** so RSS stays flat.

## Benchmark stub

Run the 100k-token corporate corpus (nested JSON, XML, DEBUG logs, runbooks, code) and paste the table below:

```bash
python benchmark.py
```

<!-- BENCHMARK:START -->
| Metric | Without Comprex | With Comprex |
| --- | ---: | ---: |
| Context size | 101,635 tok | 5,175 tok |
| Characters | 338,441 | 21,597 |
| Compression ratio | 1.0× | **19.6×** |
| Request cost (gpt-4o input @ $2.50 / 1M) | $0.2541 | $0.0129 |
| Savings per request | — | $0.2412 |
| Net spend cut | — | **94.9%** |
| Algorithm wall time | 0 ms | 196.38 ms |
| Caller-visible latency | blocking | **0 ms** (async job id) |
| Bill @ 100,000 requests / month | $25,409 | $1,294 |
| **Annual company savings** | — | **$289,380** |
<!-- BENCHMARK:END -->

Pricing assumption: **gpt-4o input $2.50 per 1M tokens**, **100,000 requests / month**. Output tokens are unchanged and excluded.

## Architecture

```
src/llm_compressor/
  config.py      # stop-words, fillers, DEBUG templates, JSON noise keys
  core.py        # Recursive Token Squeezing + sliding windows + jobs
  api.py         # FastAPI, asyncio.create_task, /compress*
  adapters/      # OpenAI + LangChain
benchmark.py     # 100k-token corpus + annual savings
```

Comprex is extractive: it does not rewrite facts with a generative model. Identifiers, ERROR lines, and runbook headings survive; duplicates, DEBUG chatter, and empty nests do not.
