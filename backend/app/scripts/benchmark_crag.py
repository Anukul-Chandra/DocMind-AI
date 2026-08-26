#!/usr/bin/env python
"""Benchmark: Baseline single-pass RAG vs Adaptive CRAG retrieval.

This is a MEASUREMENT-ONLY script.  It does not change any production logic,
does not generate final LLM answers, and does not modify the corpus.

It compares two retrieval modes over a representative, corpus-grounded query
set:

    MODE A -- BASELINE
        query -> retrieve once -> use retrieved context

    MODE B -- CRAG (current Adaptive CRAG v1)
        query -> retrieve -> evaluate -> (optional rewrite) ->
        retrieve again -> evaluate -> final context selection

Only retrieval + evaluation signals are measured.  Higher retrieval scores
are NOT assumed to equal "correct answers" unless the existing
RetrievalEvaluator semantics say so (GOOD / UNCERTAIN / BAD decisions).  Where
document ground truth can be inferred from the corpus (the owning document of
a grounded query), a relevance proxy is reported; answer-level accuracy is
explicitly NOT measured.

Usage:
    python -m app.scripts.benchmark_crag [--owner OWNER] [--max-queries N]
                                         [--output PATH]

The corpus owner that owns the grounded documents (CV + paper) is used by
default so the queries actually resolve against indexed content.

NOTE on rewrites:
    The real QueryRewriter is used.  If the configured LLM providers are
    unavailable (e.g. model 404s), the rewriter safely falls back to the
    original query and CRAG degenerates to the baseline path.  The script
    reports the rewrite rate honestly and flags this as a limitation rather
    than faking a rewrite.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

# Import order matters: importing app.api.dependencies first executes the
# application's real (working) import graph and avoids a latent circular
# import between the chat and rag packages.
from app.api.dependencies import build_provider_manager, get_retriever
from app.services.rag.crag import CragOrchestrator
from app.services.rag.query_rewriter import QueryRewriter
from app.services.rag.retrieval_evaluator import (
    RetrievalEvaluation,
    RetrievalEvaluator,
    RetrievalQuality,
)
from app.services.retrieval.base import Retriever
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


_QUALITY_RANK = {
    RetrievalQuality.GOOD: 2,
    RetrievalQuality.UNCERTAIN: 1,
    RetrievalQuality.BAD: 0,
}

# Owner that owns the grounded documents (CV + arXiv paper) in the local
# persisted corpus.  Queries are scoped to this owner so retrieval resolves.
CORPUS_OWNER = "03a8daec-5018-4ee1-83a0-ca083c67439a"

CV = "Anukul Chandra-CV.pdf"
PAPER = "2112.13047v1.pdf"

# Representative evaluation set.  `expected_doc` is set only where the owning
# document can be established from the corpus (used for a relevance proxy, not
# as answer ground truth).  Queries with expected_doc=None are out-of-corpus
# or cross-document and intentionally have no retrievable ground truth here.
QUERIES = [
    # 1. Direct document questions
    {"category": "direct-doc", "query": "What is the title of the paper 2112.13047?", "expected_doc": PAPER},
    {"category": "direct-doc", "query": "Who are the authors of the monocular depth estimation paper?", "expected_doc": PAPER},
    # 2. Personal CV questions
    {"category": "cv-personal", "query": "What is Anukul Chandra's email address?", "expected_doc": CV},
    {"category": "cv-personal", "query": "What is Anukul Chandra's phone number?", "expected_doc": CV},
    # 3. Education / work questions
    {"category": "cv-edu-work", "query": "Where did Anukul Chandra study?", "expected_doc": CV},
    {"category": "cv-edu-work", "query": "Which company does Anukul Chandra currently work for?", "expected_doc": CV},
    # 4. Paraphrase
    {"category": "paraphrase", "query": "What school did Anukul go to for his degree?", "expected_doc": CV},
    {"category": "paraphrase", "query": "What organization employs Anukul nowadays?", "expected_doc": CV},
    # 5. Weak initial retrieval (vague)
    {"category": "weak-initial", "query": "Tell me about his background.", "expected_doc": CV},
    {"category": "weak-initial", "query": "Describe his professional experience.", "expected_doc": CV},
    # 6. Terminology variation
    {"category": "terminology", "query": "Does the CV mention retrieval augmented generation or RAG?", "expected_doc": CV},
    {"category": "terminology", "query": "What attention mechanism is used in the depth network?", "expected_doc": PAPER},
    # 7. Unrelated to uploaded documents
    {"category": "unrelated", "query": "What is the weather like today?", "expected_doc": None},
    {"category": "unrelated", "query": "How do I bake a chocolate cake?", "expected_doc": None},
    # 8. No answer exists
    {"category": "no-answer", "query": "What is the GDP of France in 2030?", "expected_doc": None},
    # 9. Initial retrieval should already be strong
    {"category": "strong-initial", "query": "Anukul Chandra email address", "expected_doc": CV},
    {"category": "strong-initial", "query": "self-supervised monocular depth estimation paper", "expected_doc": PAPER},
    # 10. Deliberately difficult
    {"category": "difficult", "query": "Summarize his career trajectory.", "expected_doc": CV},
    {"category": "difficult", "query": "How do his engineering skills relate to the paper's methods?", "expected_doc": None},
]


def best_semantic(chunks: list[dict]) -> float:
    if not chunks:
        return 0.0
    return max(c.get("semantic_score", 0.0) for c in chunks)


def context_signature(chunks: list[dict]) -> tuple:
    sig = []
    for c in chunks:
        key = c.get("id") or (c.get("filename"), c.get("chunk_id"))
        sig.append(key)
    return tuple(sig)


def quality(evaluator: RetrievalEvaluator, query: str, chunks: list[dict]) -> RetrievalQuality:
    return evaluator.evaluate(query, chunks).quality


class CountingRetriever(Retriever):
    """Delegate to the real retriever while recording call count / latency."""

    def __init__(self, delegate: Retriever):
        self._delegate = delegate
        self.calls: list[dict] = []

    def retrieve(self, query, k=5, workspace_id=DEFAULT_WORKSPACE, owner_id="", query_embedding=None):
        t = time.perf_counter()
        result = self._delegate.retrieve(
            query, k=k, workspace_id=workspace_id, owner_id=owner_id, query_embedding=query_embedding
        )
        self.calls.append({
            "query": query,
            "owner_id": owner_id,
            "n": len(result),
            "dt": time.perf_counter() - t,
        })
        return result

    def is_eligible(self, document, workspace_id, owner_id=""):
        return self._delegate.is_eligible(document, workspace_id, owner_id)


class CountingRewriter:
    """Delegate to the real rewriter while recording call count / result."""

    def __init__(self, delegate: QueryRewriter):
        self._delegate = delegate
        self.calls: list[dict] = []

    async def rewrite(self, query: str) -> str:
        t = time.perf_counter()
        result = await self._delegate.rewrite(query)
        self.calls.append({
            "query": query,
            "result": result,
            "dt": time.perf_counter() - t,
        })
        return result


async def run_query(
    crag: CragOrchestrator,
    evaluator: RetrievalEvaluator,
    retriever: CountingRetriever,
    rewriter: CountingRewriter,
    query: str,
    owner_id: str,
    expected_doc,
    query_timeout: float = 60.0,
) -> dict:
    # --- MODE A: baseline single-pass retrieval ---
    retriever.calls = []
    t0 = time.perf_counter()
    baseline = retriever.retrieve(query, owner_id=owner_id, query_embedding=None)
    base_latency = time.perf_counter() - t0
    base_count = len(baseline)
    base_best = best_semantic(baseline)
    base_decision = quality(evaluator, query, baseline)

    # --- MODE B: CRAG (current Adaptive CRAG v1) ---
    rewriter.calls = []
    retriever.calls = []
    t0 = time.perf_counter()
    timed_out = False
    try:
        final = await asyncio.wait_for(
            crag.retrieve(query, owner_id=owner_id, query_embedding=None),
            timeout=query_timeout,
        )
    except asyncio.TimeoutError:
        # Benchmark safeguard: a stuck provider call must not hang the run.
        # Treat as a failed rewrite and fall back to the baseline context.
        timed_out = True
        final = baseline
    crag_latency = time.perf_counter() - t0

    passes = len(retriever.calls)
    rw_calls = list(rewriter.calls)
    rewrite_called = len(rw_calls) > 0
    rewrite_result = rw_calls[0]["result"] if rw_calls else None
    rewrite_changed = bool(rewrite_called and rewrite_result != query)
    second_retrieval = passes >= 2

    final_best = best_semantic(final)
    final_decision = quality(evaluator, query, final)
    changed = context_signature(final) != context_signature(baseline)

    init_rank = _QUALITY_RANK[base_decision]
    fin_rank = _QUALITY_RANK[final_decision]
    improved = fin_rank > init_rank
    degraded = fin_rank < init_rank
    unchanged = fin_rank == init_rank
    add_latency = crag_latency - base_latency

    if expected_doc is not None:
        relevance_hit = any(c.get("filename") == expected_doc for c in final[:5])
    else:
        relevance_hit = None

    return {
        "query": query,
        "category": None,  # filled by caller
        "expected_doc": expected_doc,
        "timed_out": timed_out,
        "baseline_best_score": round(base_best, 4),
        "baseline_count": base_count,
        "baseline_latency": round(base_latency, 4),
        "crag_latency": round(crag_latency, 4),
        "retrieval_passes": passes,
        "evaluations": 1 + (1 if second_retrieval else 0),
        "initial_decision": base_decision.value,
        "final_decision": final_decision.value,
        "rewrite_called": rewrite_called,
        "rewrite_changed": rewrite_changed,
        "rewrite_result": rewrite_result,
        "second_retrieval": second_retrieval,
        "final_best_score": round(final_best, 4),
        "final_context_changed": changed,
        "improved": improved,
        "unchanged": unchanged,
        "degraded": degraded,
        "additional_latency": round(add_latency, 4),
        "relevance_hit": relevance_hit,
    }


def summarize(rows: list[dict]) -> dict:
    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    n = len(rows)
    eligible = [r for r in rows if r["initial_decision"] != RetrievalQuality.GOOD.value]
    improved = sum(1 for r in rows if r["improved"])
    unchanged = sum(1 for r in rows if r["unchanged"])
    degraded = sum(1 for r in rows if r["degraded"])
    rewrite_attempted = sum(1 for r in rows if r["rewrite_called"])
    rewrite_effective = sum(1 for r in rows if r["rewrite_changed"])
    corrective = sum(1 for r in rows if r["second_retrieval"])
    bad_good = sum(
        1 for r in rows
        if r["initial_decision"] == RetrievalQuality.BAD.value and r["final_decision"] == RetrievalQuality.GOOD.value
    )
    uncertain_good = sum(
        1 for r in rows
        if r["initial_decision"] == RetrievalQuality.UNCERTAIN.value and r["final_decision"] == RetrievalQuality.GOOD.value
    )
    bad_bad = sum(
        1 for r in rows
        if r["initial_decision"] == RetrievalQuality.BAD.value and r["final_decision"] == RetrievalQuality.BAD.value
    )
    add_lat = [r["additional_latency"] for r in rows]
    rel_rows = [r for r in rows if r["relevance_hit"] is not None]
    rel_hits = sum(1 for r in rel_rows if r["relevance_hit"])

    return {
        "queries": n,
        "baseline_avg_score": round(mean([r["baseline_best_score"] for r in rows]), 4),
        "crag_avg_final_score": round(mean([r["final_best_score"] for r in rows]), 4),
        "improved": improved,
        "unchanged": unchanged,
        "degraded": degraded,
        "rewrite_attempt_rate": round(rewrite_attempted / n, 4) if n else 0.0,
        "rewrite_effective_rate": round(rewrite_effective / n, 4) if n else 0.0,
        "corrective_retrieval_rate": round(corrective / n, 4) if n else 0.0,
        "bad_to_good": bad_good,
        "uncertain_to_good": uncertain_good,
        "bad_to_bad": bad_bad,
        "avg_baseline_latency": round(mean([r["baseline_latency"] for r in rows]), 4),
        "avg_crag_latency": round(mean([r["crag_latency"] for r in rows]), 4),
        "avg_additional_latency": round(mean(add_lat), 4),
        "max_additional_latency": round(max(add_lat), 4) if add_lat else 0.0,
        "eligible_crag_queries": len(eligible),
        "improvement_rate": round(improved / len(eligible), 4) if eligible else None,
        "grounded_queries": len(rel_rows),
        "grounded_relevance_hits": rel_hits,
        "grounded_relevance_rate": round(rel_hits / len(rel_rows), 4) if rel_rows else None,
    }


def print_report(rows: list[dict], summary: dict, owner_id: str, rewrite_mode: str) -> None:
    print("=" * 70)
    print("CRAG BENCHMARK  (retrieval-only, no LLM answers generated)")
    print("=" * 70)
    print(f"Owner scope       : {owner_id}")
    print(f"Rewrite mode      : {rewrite_mode}")
    print(f"Queries           : {summary['queries']}")
    print()
    print("BASELINE")
    print(f"  Average score      : {summary['baseline_avg_score']}")
    print(f"  Average latency    : {summary['avg_baseline_latency']} s")
    print("CRAG")
    print(f"  Average final score: {summary['crag_avg_final_score']}")
    print(f"  Average latency    : {summary['avg_crag_latency']} s")
    print()
    print(f"Improved : {summary['improved']}")
    print(f"Unchanged: {summary['unchanged']}")
    print(f"Degraded : {summary['degraded']}")
    print()
    print(f"Rewrite attempt rate     : {summary['rewrite_attempt_rate']}")
    print(f"Rewrite effective rate    : {summary['rewrite_effective_rate']}")
    print(f"Corrective retrieval rate : {summary['corrective_retrieval_rate']}")
    print()
    print(f"BAD -> GOOD   : {summary['bad_to_good']}")
    print(f"UNCERTAIN -> GOOD : {summary['uncertain_to_good']}")
    print(f"BAD -> BAD   : {summary['bad_to_bad']}")
    print()
    print(f"Additional latency (avg): {summary['avg_additional_latency']} s")
    print(f"Additional latency (max): {summary['max_additional_latency']} s")
    if summary["improvement_rate"] is not None:
        print(f"CRAG improvement rate (improved / eligible): {summary['improvement_rate']}")
    else:
        print("CRAG improvement rate: n/a (no eligible CRAG queries)")
    if summary["grounded_relevance_rate"] is not None:
        print(f"Grounded relevance hit rate: {summary['grounded_relevance_rate']} "
              f"({summary['grounded_relevance_hits']}/{summary['grounded_queries']})")
    print()
    print("PER-QUERY")
    hdr = f"{'#':>2} {'cat':<12} {'init':<9} {'final':<9} {'rw':<3} {'2nd':<3} {'chg':<3} {'bscr':<6} {'fscr':<6} {'+lat':<7} {'rel':<4}"
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(rows, 1):
        rel = "-" if r["relevance_hit"] is None else ("Y" if r["relevance_hit"] else "n")
        print(f"{i:>2} {r['category']:<12} {r['initial_decision']:<9} {r['final_decision']:<9} "
              f"{'Y' if r['rewrite_called'] else '-':<3} "
              f"{'Y' if r['second_retrieval'] else '-':<3} "
              f"{'Y' if r['final_context_changed'] else '-':<3} "
              f"{r['baseline_best_score']:<6} {r['final_best_score']:<6} "
              f"{r['additional_latency']:<7} {rel:<4}")
    print()
    print("Legend: rw=rewrite attempted, 2nd=second retrieval, chg=final context changed,")
    print("        bscr/fscr=best semantic score (baseline/final), rel=grounded relevance hit")
    print("NOTE: higher semantic score != correct answer. Decisions follow the")
    print("      RetrievalEvaluator (GOOD/UNCERTAIN/BAD). Answer accuracy not measured.")


async def main_async(args) -> dict:
    retriever_real = get_retriever()
    evaluator = RetrievalEvaluator()
    provider_manager = build_provider_manager()
    rewriter_real = QueryRewriter(provider_manager)

    retriever = CountingRetriever(retriever_real)
    rewriter = CountingRewriter(rewriter_real)
    crag = CragOrchestrator(retriever, evaluator, rewriter)

    queries = QUERIES[: args.max_queries] if args.max_queries else QUERIES
    rows = []
    for spec in queries:
        row = await run_query(
            crag, evaluator, retriever, rewriter,
            spec["query"], args.owner, spec["expected_doc"],
            query_timeout=args.query_timeout,
        )
        row["category"] = spec["category"]
        rows.append(row)

    summary = summarize(rows)
    print_report(rows, summary, args.owner, rewrite_mode="real QueryRewriter")

    if args.output:
        out = {
            "owner_id": args.owner,
            "rewrite_mode": "real",
            "summary": summary,
            "queries": rows,
        }
        Path(args.output).write_text(json.dumps(out, indent=2))
        print(f"\nMachine-readable results written to: {args.output}")
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Baseline RAG vs Adaptive CRAG retrieval.")
    parser.add_argument("--owner", default=CORPUS_OWNER, help="Owner scope for retrieval.")
    parser.add_argument("--max-queries", type=int, default=None, help="Limit number of benchmark queries.")
    parser.add_argument(
        "--query-timeout", type=float, default=60.0,
        help="Per-query wall-clock timeout (s) for the CRAG call; a slow/stuck "
             "provider rewrite is treated as a failure and falls back to the "
             "baseline context rather than hanging the run.",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent.parent / "storage" / "logs" / "benchmark_crag_results.json"),
        help="Path to write machine-readable JSON results.",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
