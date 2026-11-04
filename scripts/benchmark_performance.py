"""Reproducible local RAG benchmark.

This benchmark does not call Groq or fabricate provider token/latency data.
It compares the pre-optimization TF-IDF work (fit per query) with the
optimized indexed retriever over the same fixed queries and knowledge base.
"""

import json
import os
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from rag.retrieval import (  # noqa: E402
    MIN_RELEVANCE_SCORE,
    clear_cache,
    load_articles,
    retrieve,
)


QUERIES = [
    ("refund_policy refund What is your refund policy?", "refund_policy"),
    ("refund_timeline billing How long does a refund take?", "refund_timeline"),
    ("wrong_item order I received a damaged item.", "wrong_item"),
    ("delivery_delay order My shipment is delayed.", "delivery_delay"),
    ("payment_failure billing My payment was deducted but the order failed.", "payment_failure"),
    ("cancel_order order Can I cancel my order?", "cancel_order"),
]


def percentile(values, percentile):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, int(len(ordered) * percentile) - 1))
    return round(ordered[index], 3)


def summarize(values):
    return {
        "count": len(values),
        "average_ms": round(statistics.mean(values), 3),
        "median_ms": percentile(values, 0.5),
        "p95_ms": percentile(values, 0.95),
    }


def baseline_retrieve(query, intent):
    articles = load_articles()
    corpus = []
    for article in articles:
        title = article.get("title", "")
        tags = " ".join(article.get("tags", []))
        corpus.append(
            f"{title} {title} {tags} {tags} {article.get('text', '')}"
        )
    vectorizer = TfidfVectorizer(
        stop_words="english", ngram_range=(1, 2), sublinear_tf=True
    )
    matrix = vectorizer.fit_transform(corpus + [query])
    scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    preferred = {
        "refund": {"KB-108"},
        "refund_policy": {"KB-108"},
        "refund_timeline": {"KB-108"},
        "refund_issue": {"KB-108", "KB-102"},
        "payment_failure": {"KB-102"},
        "wrong_item": {"KB-101"},
        "delivery_delay": {"KB-107"},
        "cancel_order": {"KB-105"},
    }.get(intent, set())
    ranked = []
    for index, score in enumerate(scores):
        article = articles[index]
        article_id = article.get("id", "KB-UNKNOWN")
        if intent == "change_of_mind_return" or (
            preferred and article_id not in preferred
        ):
            continue
        title_tag_tokens = set(
            re.findall(
                r"[a-z0-9]+",
                (
                    article.get("title", "")
                    + " "
                    + " ".join(article.get("tags", []))
                ).lower(),
            )
        )
        adjusted = float(score) + min(
            len(query_tokens & title_tag_tokens) * 0.025, 0.10
        )
        if article_id in preferred:
            adjusted += 0.12
        if adjusted >= MIN_RELEVANCE_SCORE:
            ranked.append((adjusted, article_id))
    ranked.sort(reverse=True)
    return [article_id for _, article_id in ranked[:3]]


def measure(call, repetitions):
    durations = []
    outputs = []
    for _ in range(repetitions):
        started = time.perf_counter()
        outputs.append(call())
        durations.append((time.perf_counter() - started) * 1000)
    return summarize(durations), outputs


def main():
    repetitions = int(os.getenv("AEGIS_BENCHMARK_REPETITIONS", "10"))
    baseline = {}
    optimized = {}
    quality_matches = []

    clear_cache()
    for query, intent in QUERIES:
        baseline_stats, baseline_outputs = measure(
            lambda q=query, i=intent: baseline_retrieve(q, i), repetitions
        )
        baseline[query] = baseline_stats
        clear_cache()
        optimized_stats, optimized_outputs = measure(
            lambda q=query, i=intent: retrieve(q, intent=i), repetitions
        )
        optimized[query] = optimized_stats
        optimized_ids = [
            item.get("id") for item in optimized_outputs[-1]
        ]
        quality_matches.append(baseline_outputs[-1] == optimized_ids)

    concurrent_queries = QUERIES * max(2, min(8, repetitions))
    clear_cache()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(
            executor.map(
                lambda item: retrieve(item[0], intent=item[1]),
                concurrent_queries,
            )
        )
    concurrent_duration = (time.perf_counter() - started) * 1000

    output = {
        "benchmark": {
            "dataset": str(ROOT / "data" / "knowledge_base" / "articles.json"),
            "query_count": len(QUERIES),
            "repetitions_per_query": repetitions,
            "provider_calls": 0,
            "token_usage": None,
            "scope": "local TF-IDF retrieval and cache; no Groq calls",
        },
        "baseline": baseline,
        "optimized": optimized,
        "retrieval_quality": {
            "top_k_ids_exact_match_rate": round(
                sum(quality_matches) / len(quality_matches), 3
            )
        },
        "concurrency": {
            "request_count": len(concurrent_queries),
            "workers": 8,
            "total_ms": round(concurrent_duration, 3),
            "average_ms": round(concurrent_duration / len(concurrent_queries), 3),
        },
    }

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    json_path = reports / "performance_benchmark.json"
    json_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    markdown = [
        "# AegisSupport performance evaluation",
        "",
        "Generated by `scripts/benchmark_performance.py` using the fixed knowledge-base query set.",
        "No Groq requests or fabricated token measurements are included.",
        "",
        f"- Retrieval top-k exact-match rate: {output['retrieval_quality']['top_k_ids_exact_match_rate']:.1%}",
        f"- Concurrent optimized retrieval: {output['concurrency']['request_count']} requests, {output['concurrency']['workers']} workers, {output['concurrency']['total_ms']} ms total",
        "- Token usage: unavailable because this benchmark intentionally makes zero provider calls.",
        "",
        "## Per-query measurements",
        "",
        "| Query | Baseline avg/median/p95 ms | Optimized avg/median/p95 ms |",
        "|---|---:|---:|",
    ]
    for query, _ in QUERIES:
        before = baseline[query]
        after = optimized[query]
        markdown.append(
            f"| {query} | {before['average_ms']}/{before['median_ms']}/{before['p95_ms']} | "
            f"{after['average_ms']}/{after['median_ms']}/{after['p95_ms']} |"
        )
    markdown.extend(
        [
            "",
            "## Interpretation",
            "",
            "The optimized retriever reuses a fitted TF-IDF index and caches repeated query results with TTL and bounded size. "
            "The exact-match rate compares returned article IDs with the pre-optimization implementation on the same inputs.",
            "Groq inference latency and token consumption require a separately authorized provider benchmark and are therefore reported as unavailable here.",
        ]
    )
    (reports / "PERFORMANCE_EVALUATION.md").write_text(
        "\n".join(markdown) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
