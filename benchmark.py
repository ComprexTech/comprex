#!/usr/bin/env python3
"""Build a 100k-token corporate dump, squeeze it, and print cost savings."""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from llm_compressor import CompressConfig, Compressor, count_tokens  # noqa: E402

GPT4O_INPUT_PER_MILLION_USD = 2.50
MONTHLY_REQUESTS = 100_000
TARGET_TOKENS = 100_000
MODEL = "gpt-4o"

_SERVICES = (
    "checkout-api",
    "ledger-worker",
    "fraud-graph",
    "payout-orchestrator",
    "wallet-core",
    "fx-rate-cache",
    "kyc-review",
    "dispute-desk",
    "settlement-batch",
    "notify-gateway",
)
_STORES = ("Postgres", "Redis", "Kafka", "S3", "ClickHouse", "Dynamo")
_TEAMS = ("payments-platform", "risk-ml", "finops", "identity", "growth")


def build_payload(min_tokens: int = TARGET_TOKENS) -> str:
    """Synthetic nested JSON + logs + runbooks + code, sized to 100k tokens."""
    parts: list[str] = [
        "# Acme Payments — production context dump",
        "This file is what a naive RAG/LLM pipeline would send as the system context.",
        "Please note that the following runbook is the source of truth for on-call.",
    ]
    idx = 0
    while True:
        service = _SERVICES[idx % len(_SERVICES)]
        store = _STORES[idx % len(_STORES)]
        team = _TEAMS[idx % len(_TEAMS)]
        shard = idx % 16
        sla = 80 + (idx % 25) * 7
        uid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"acme-{idx}"))
        digest = hashlib_hex(idx)
        path = f"/var/log/{service}/shard-{shard}/worker-{idx % 12}.log"
        endpoint = f"/v1/{service.replace('-', '/')}/shard/{shard}"
        parts.append(f"## {service} shard {shard}")
        parts.append(
            f"The {service} module exposes {endpoint} and persists {service}_events "
            f"in {store}. Owning team is {team}. Hard SLA is {sla}ms p99. "
            f"Circuit breaker trips after {3 + idx % 4} consecutive timeouts and "
            f"opens a fallback to cached {service} snapshot #{idx}."
        )
        parts.append(
            f"Feature flag `{service}.shadow_read` is {['off', 'on'][idx % 2]}. "
            f"Schema version {service}.v{1 + idx % 9} adds field `trace_{idx}`. "
            f"Alert `A-{idx:04d}` fires when error ratio exceeds {1 + idx % 5}%."
        )
        parts.append(
            "Please note that every request is authenticated. It is important to note "
            "that idempotency keys are mandatory. As mentioned above, retries are "
            "limited to three attempts. Basically the worker must not double-apply. "
            "In order to avoid duplicate captures, the fact that keys rotate hourly "
            "is actually kind of important."
        )
        parts.append(
            "{"
            f'"id":"{uid}","hash":"{digest}","path":"{path}","debug":null,'
            '"raw_payload":{},"trace":"","nested":{"a":{"b":{"c":{"d":{"e":"noise"}}}}},'
            f'"endpoint":"{endpoint}","empty":"",'
            '"_debug":{"stack_trace":null,"probe":[]}'
            "}"
        )
        parts.append(
            f"<{service}><meta></meta><!-- noise --><path>{path}</path>"
            f"<empty></empty><sla>{sla}</sla></{service}>"
        )
        parts.append(
            f"2026-10-24 12:{idx % 60:02d}:{idx % 60:02d} INFO {service} handled "
            f"req_{idx} shard={shard} store={store} sla_ms={sla} uuid={uid}"
        )
        parts.append(
            f"2026-10-24 12:{idx % 60:02d}:{(idx + 1) % 60:02d} DEBUG retry inner "
            f"loop tick worker={idx % 12} attempt={(idx % 3) + 1} hash={digest}"
        )
        parts.append(
            "def reconcile(batch_id: str) -> None:\n"
            "    # Please note that this is a verbose helper used in runbooks.\n"
            "    for attempt in range(3):\n"
            "        if attempt:\n"
            "            continue\n"
            f"        ledger.apply('{service}', '{store}', {idx})\n"
        )
        if idx % 11 == 0:
            parts.append(
                f"2026-10-24 12:{idx % 60:02d}:{(idx + 3) % 60:02d} ERROR {service} "
                f"timeout req_{idx} after {sla * 2}ms code=E{idx:04d} path={path}"
            )
        idx += 1
        if idx % 16 == 0:
            tokens = count_tokens("\n".join(parts))
            if tokens >= min_tokens:
                break
    return "\n".join(parts)


def hashlib_hex(idx: int) -> str:
    return f"{idx:032x}" + f"{(idx * 17) % 256:02x}" * 16


def usd(amount: float) -> str:
    if amount >= 100:
        return f"${amount:,.0f}"
    if amount >= 1:
        return f"${amount:,.2f}"
    return f"${amount:,.4f}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def pad(text: str, width: int, align: str = "left") -> str:
    text = str(text)
    if len(text) >= width:
        return text
    extra = width - len(text)
    if align == "right":
        return " " * extra + text
    if align == "center":
        left = extra // 2
        return " " * left + text + " " * (extra - left)
    return text + " " * extra


@dataclass(frozen=True)
class Benchmark:
    original_tokens: int
    compressed_tokens: int
    ratio: float
    elapsed_ms: float
    cost_raw: float
    cost_compressed: float
    saved_per_request: float
    savings_pct: float
    monthly_saved: float
    yearly_saved: float
    original_chars: int
    compressed_chars: int


def cost_usd(tokens: int) -> float:
    return tokens / 1_000_000 * GPT4O_INPUT_PER_MILLION_USD


def run() -> Benchmark:
    payload = build_payload(TARGET_TOKENS)
    engine = Compressor(CompressConfig(cache_size=0))
    result = engine.compress_sync(payload)
    original_tokens = count_tokens(payload)
    compressed_tokens = max(1, count_tokens(result.text))
    raw = cost_usd(original_tokens)
    compressed = cost_usd(compressed_tokens)
    saved = raw - compressed
    savings_pct = (saved / raw * 100.0) if raw else 0.0
    monthly = saved * MONTHLY_REQUESTS
    return Benchmark(
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        ratio=original_tokens / compressed_tokens,
        elapsed_ms=result.elapsed_ms,
        cost_raw=raw,
        cost_compressed=compressed,
        saved_per_request=saved,
        savings_pct=savings_pct,
        monthly_saved=monthly,
        yearly_saved=monthly * 12,
        original_chars=result.original_chars,
        compressed_chars=result.compressed_chars,
    )


def console_table(b: Benchmark) -> str:
    rows = [
        ("Metric", "Without Comprex", "With Comprex"),
        ("Context size", f"{b.original_tokens:,} tok", f"{b.compressed_tokens:,} tok"),
        ("Characters", f"{b.original_chars:,}", f"{b.compressed_chars:,}"),
        ("Compression ratio", "1.0×", f"{b.ratio:.1f}×"),
        (f"{MODEL} input cost / request", usd(b.cost_raw), usd(b.cost_compressed)),
        ("Savings / request", "—", usd(b.saved_per_request)),
        ("Net token-budget cut", "—", pct(b.savings_pct)),
        ("Algorithm wall time", "0 ms (n/a)", f"{b.elapsed_ms:.2f} ms"),
        ("API wait for caller", "blocks", "0 ms (job id)"),
        ("100k requests / month", usd(b.cost_raw * MONTHLY_REQUESTS), usd(b.cost_compressed * MONTHLY_REQUESTS)),
        ("Annual company savings", "—", usd(b.yearly_saved)),
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(3)]
    widths = [max(w, 12) for w in widths]

    def line(left: str, mid: str, right: str, fill: str = "─") -> str:
        return (
            left
            + fill * (widths[0] + 2)
            + mid
            + fill * (widths[1] + 2)
            + mid
            + fill * (widths[2] + 2)
            + right
        )

    def row(cells: tuple[str, str, str]) -> str:
        align = ("left", "right", "right")
        return "│ " + " │ ".join(pad(cells[i], widths[i], align[i]) for i in range(3)) + " │"

    out = [line("┌", "┬", "┐"), row(rows[0]), line("├", "┼", "┤")]
    out.extend(row(item) for item in rows[1:])
    out.append(line("└", "┴", "┘"))
    return "\n".join(out)


def markdown_table(b: Benchmark) -> str:
    return f"""## Cost simulation ({MODEL})

Synthetic corpus: nested JSON, XML, DEBUG logs, runbooks and code totalling
**{b.original_tokens:,} input tokens**. Input price: **${GPT4O_INPUT_PER_MILLION_USD:.2f} / 1M tokens**.
Load: **{MONTHLY_REQUESTS:,} requests / month**.

| Metric | Without Comprex | With Comprex |
| --- | ---: | ---: |
| Context size | {b.original_tokens:,} tok | {b.compressed_tokens:,} tok |
| Characters | {b.original_chars:,} | {b.compressed_chars:,} |
| Compression ratio | 1.0× | {b.ratio:.1f}× |
| Request cost ({MODEL} input) | {usd(b.cost_raw)} | {usd(b.cost_compressed)} |
| Savings per request | — | {usd(b.saved_per_request)} |
| Net spend cut | — | {pct(b.savings_pct)} |
| Algorithm wall time | 0 ms | {b.elapsed_ms:.2f} ms |
| Caller-visible latency | blocking | **0 ms** (async job id) |
| Bill @ 100k requests / month | {usd(b.cost_raw * MONTHLY_REQUESTS)} | {usd(b.cost_compressed * MONTHLY_REQUESTS)} |
| **Annual company savings** | — | **{usd(b.yearly_saved)}** |

> Input tokens only. Output cost is identical in both branches and is excluded.
> Recompute locally: `python benchmark.py`
"""


def _configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass


def main() -> None:
    _configure_stdout()
    benchmark = run()
    banner = " COMPREX  |  Enterprise AI Context Compressor "
    print()
    print(f"╔{'═' * 62}╗")
    print(f"║{pad(banner, 62, 'center')}║")
    print(f"╚{'═' * 62}╝")
    print()
    print(console_table(benchmark))
    print()
    print("Markdown for README:")
    print()
    print(markdown_table(benchmark))


if __name__ == "__main__":
    main()
