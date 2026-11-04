
import json
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config import RAG_CACHE_MAX_ENTRIES, RAG_CACHE_TTL_SECONDS
from observability import increment, observe

KB_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "knowledge_base"
    / "articles.json"
).resolve()

# Minimum score is deliberately conservative. Calibrate against your
# own knowledge base before using this as a production confidence gate.
MIN_RELEVANCE_SCORE = 0.025
_index_lock = threading.Lock()
_cache_lock = threading.Lock()
_indexed_mtime = None
_indexed_articles = []
_indexed_matrix = None
_indexed_vectorizer = None
_retrieval_cache = OrderedDict()


def load_articles():
    try:
        data = json.loads(KB_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _build_index(articles):
    corpus = []
    for article in articles:
        title = article.get("title", "")
        body = article.get("text", "")
        tags = " ".join(article.get("tags", []))
        corpus.append(f"{title} {title} {tags} {tags} {body}")
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    return vectorizer, vectorizer.fit_transform(corpus)


def _get_index():
    global _indexed_mtime, _indexed_articles, _indexed_matrix, _indexed_vectorizer
    try:
        modified = KB_PATH.stat().st_mtime_ns
    except OSError:
        return [], None, None
    if modified == _indexed_mtime:
        return _indexed_articles, _indexed_matrix, _indexed_vectorizer
    with _index_lock:
        if modified != _indexed_mtime:
            articles = load_articles()
            try:
                vectorizer, matrix = _build_index(articles)
            except ValueError:
                vectorizer, matrix = None, None
            _indexed_articles = articles
            _indexed_vectorizer = vectorizer
            _indexed_matrix = matrix
            _indexed_mtime = modified
            with _cache_lock:
                _retrieval_cache.clear()
        return _indexed_articles, _indexed_matrix, _indexed_vectorizer


def _retrieve_uncached(query, k=3, min_score=MIN_RELEVANCE_SCORE, intent=None):
    query = (query or "").strip()
    articles, matrix, vectorizer = _get_index()

    if not query or not articles or matrix is None or vectorizer is None:
        return []

    intent_name = str(intent or "").lower()
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    if intent_name == "change_of_mind_return":
        return []

    try:
        query_vector = vectorizer.transform([query])
        scores = cosine_similarity(query_vector, matrix).ravel()
    except ValueError:
        return []

    ranked = []
    for index, score in enumerate(scores):
        article = articles[index]
        article_id = article.get("id", "KB-UNKNOWN")
        # A change-of-mind request has no supporting article in the current
        # corpus. Do not let the generic "return" tag on KB-101 become a
        # misleading answer.
        if intent_name == "change_of_mind_return" and article_id == "KB-101":
            continue
        preferred = {
            "refund": {"KB-108"},
            "refund_policy": {"KB-108"},
            "refund_timeline": {"KB-108"},
            "refund_issue": {"KB-108", "KB-102"},
            "payment_failure": {"KB-102"},
            "wrong_item": {"KB-101"},
            "delivery_delay": {"KB-107"},
            "cancel_order": {"KB-105"},
        }.get(intent_name, set())
        if preferred and article_id not in preferred:
            continue
        title = article.get("title", "")
        tags = article.get("tags", [])
        title_tag_tokens = _tokens(title + " " + " ".join(tags))

        # Small lexical boost for matching the policy title/tags.
        overlap = len(query_tokens & title_tag_tokens)
        adjusted_score = float(score) + min(overlap * 0.025, 0.10)
        if article_id in preferred:
            adjusted_score += 0.12
        elif preferred:
            adjusted_score -= 0.04

        if adjusted_score < min_score:
            continue

        ranked.append({
            "id": article_id,
            "title": title,
            "text": article.get("text", ""),
            "score": round(adjusted_score, 3),
        })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:max(1, min(k, 5))]


def retrieve(query, k=3, min_score=MIN_RELEVANCE_SCORE, intent=None):
    normalized_query = (query or "").strip()
    key = (
        normalized_query.lower(),
        str(intent or "").lower(),
        int(k),
        float(min_score),
    )
    now = time.monotonic()
    with _cache_lock:
        cached = _retrieval_cache.get(key)
        if cached and now - cached[0] <= RAG_CACHE_TTL_SECONDS:
            _retrieval_cache.move_to_end(key)
            increment("rag.cache_hit")
            return [dict(item) for item in cached[1]]
        if cached:
            _retrieval_cache.pop(key, None)
    started = time.perf_counter()
    result = _retrieve_uncached(
        normalized_query, k=k, min_score=min_score, intent=intent
    )
    with _cache_lock:
        _retrieval_cache[key] = (time.monotonic(), result)
        _retrieval_cache.move_to_end(key)
        while len(_retrieval_cache) > RAG_CACHE_MAX_ENTRIES:
            _retrieval_cache.popitem(last=False)
    increment("rag.cache_miss")
    observe("rag.retrieval", (time.perf_counter() - started) * 1000)
    return [dict(item) for item in result]


def clear_cache() -> None:
    with _cache_lock:
        _retrieval_cache.clear()


def cache_info() -> dict:
    with _cache_lock:
        return {"entries": len(_retrieval_cache), "max_entries": RAG_CACHE_MAX_ENTRIES}


def run(query, intent=None):
    started = time.perf_counter()
    docs = retrieve(query, intent=intent)

    event = {
        "agent": "Knowledge Retrieval Agent",
        "action": "Retrieve and rank relevant support policies using TF-IDF",
        "output": (
            f"Retrieved {len(docs)} relevant article(s): "
            + (", ".join(d["id"] for d in docs) if docs else "no reliable match")
        ),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "status": "success" if docs else "warning",
    }
    return docs, event
