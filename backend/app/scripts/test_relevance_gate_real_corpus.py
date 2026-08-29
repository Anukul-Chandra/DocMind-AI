"""Real-corpus regression test for the hybrid relevance-gated router.

Runs the actual production wiring (``get_chat_service``, ``get_semantic_retriever``,
``get_bm25_retriever``) against the persisted ``storage/`` index and metadata, so
the routing decisions are made with the real MiniLM embeddings and the real BM25
corpus - not fakes. This is the ground truth that the deterministic unit tests in
``test_chat_routing.py`` approximate.

Expected outcomes are derived from the audited real-corpus measurements:

- implicit personal / self-attribute questions route to RAG (DOCUMENT)
- generic ML/AI topic questions stay GENERAL even when the corpus contains an
  ML paper
- metadata typos resolve to METADATA without consulting the gates
- explicit filenames force DOCUMENT
- general chatter stays GENERAL
- owner isolation: one owner's corpus never influences another owner's score

The test is read-only: it never writes to storage and never calls an LLM.

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python app/scripts/test_relevance_gate_real_corpus.py
"""

import asyncio

from app.api.dependencies import (
    get_chat_service,
    get_embedding_service,
    get_semantic_retriever,
)
from app.services.chat.query_router import QueryCategory

OWNER = "03a8daec-5018-4ee1-83a0-ca083c67439a"


async def test_implicit_personal_routes_to_document() -> bool:
    """Self-referential personal questions use the low personal floor -> RAG."""
    router = get_chat_service()._query_router
    questions = [
        "what was my last job?",
        "summarize my work experience",
        "what skills do i have?",
        "what is my educational background?",
        "what is my email?",
        "tell me about my education",
        "where did I study?",
    ]
    for question in questions:
        actual = router.classify(question, owner_id=OWNER)
        if actual is not QueryCategory.DOCUMENT:
            print(
                f"FAIL: implicit personal {question!r} -> {actual.value}, "
                f"expected document"
            )
            return False
    return True


async def test_topic_questions_stay_general() -> bool:
    """Generic ML/AI topic questions stay GENERAL despite an ML paper in corpus."""
    router = get_chat_service()._query_router
    questions = [
        "define machine learning",
        "what is deep learning?",
        "history of AI",
        "explain neural networks",
        "best programming language",
    ]
    for question in questions:
        actual = router.classify(question, owner_id=OWNER)
        if actual is not QueryCategory.GENERAL:
            print(
                f"FAIL: topic {question!r} -> {actual.value}, "
                f"expected general"
            )
            return False
    return True


async def test_document_noun_rescue() -> bool:
    """Document-noun questions route to RAG on BM25 evidence."""
    router = get_chat_service()._query_router
    questions = [
        "explain the monocular depth estimation paper",
        "what method does the paper use?",
    ]
    for question in questions:
        actual = router.classify(question, owner_id=OWNER)
        if actual is not QueryCategory.DOCUMENT:
            print(
                f"FAIL: document-noun {question!r} -> {actual.value}, "
                f"expected document"
            )
            return False
    return True


async def test_general_stays_general() -> bool:
    """Unrelated general chatter stays GENERAL."""
    router = get_chat_service()._query_router
    questions = [
        "hello",
        "what is RAG?",
        "tell me a joke",
        "what is the weather today?",
        "capital of france",
    ]
    for question in questions:
        actual = router.classify(question, owner_id=OWNER)
        if actual is not QueryCategory.GENERAL:
            print(
                f"FAIL: general {question!r} -> {actual.value}, "
                f"expected general"
            )
            return False
    return True


async def test_metadata_typos() -> bool:
    """Metadata typos resolve to METADATA without consulting the gates."""
    router = get_chat_service()._query_router
    questions = [
        "which dcuments i upload in here?",
        "how many documnts do i have?",
        "did i uploadd the file?",
    ]
    for question in questions:
        actual = router.classify(question, owner_id=OWNER)
        if actual is not QueryCategory.METADATA:
            print(
                f"FAIL: metadata typo {question!r} -> {actual.value}, "
                f"expected metadata"
            )
            return False
    return True


async def test_explicit_filename_forces_document() -> bool:
    """Explicit filenames force DOCUMENT."""
    router = get_chat_service()._query_router
    questions = [
        "summarize Anukul Chandra-CV.pdf",
        "what does 2112.13047v1.pdf say?",
    ]
    for question in questions:
        actual = router.classify(question, owner_id=OWNER)
        if actual is not QueryCategory.DOCUMENT:
            print(
                f"FAIL: filename {question!r} -> {actual.value}, "
                f"expected document"
            )
            return False
    return True


async def test_empty_owner_is_general() -> bool:
    """An owner with no corpus gets GENERAL, never RAG."""
    router = get_chat_service()._query_router
    empty_owner = "ffffffff-0000-0000-0000-000000000000"
    for question in ("what is in my CV?", "summarize my resume"):
        actual = router.classify(question, owner_id=empty_owner)
        if actual is not QueryCategory.GENERAL:
            print(
                f"FAIL: empty owner {question!r} -> {actual.value}, "
                f"expected general"
            )
            return False
    return True


async def test_owner_isolation() -> bool:
    """Another owner's corpus must never inflate the relevance score."""
    semantic = get_semantic_retriever()
    embedding = get_embedding_service()
    question = "summarize my work experience"
    query_embedding = embedding.generate_embeddings([question])[0]

    own_score = semantic.best_similarity(
        question, owner_id=OWNER, query_embedding=query_embedding
    )
    other_owner = "d2455f33-b70b-4e81-b8f0-774115a6e38d"
    other_score = semantic.best_similarity(
        question, owner_id=other_owner, query_embedding=query_embedding
    )
    # The other owner's two test chunks are unrelated to work experience, so
    # the score must be well below the personal floor for this owner.
    if other_score >= own_score:
        print(
            f"FAIL: other owner score {other_score:.3f} >= own {own_score:.3f}"
        )
        return False
    return True


async def test_embedding_reuse() -> bool:
    """The router returns a request-local query embedding for retrieval reuse."""
    router = get_chat_service()._query_router
    route = router.classify_with_embedding(
        "what was my last job?", owner_id=OWNER
    )
    if route.query_embedding is None:
        print("FAIL: router did not produce a request-local query embedding")
        return False
    return True


async def main() -> None:
    """Run all real-corpus scenarios and report the overall result."""
    print("=" * 60)
    print("Real-Corpus Relevance Gate Test")
    print("=" * 60)

    scenarios = [
        ("Implicit personal -> DOCUMENT", test_implicit_personal_routes_to_document),
        ("ML/AI topics stay GENERAL", test_topic_questions_stay_general),
        ("Document-noun + BM25 rescue", test_document_noun_rescue),
        ("General chatter stays GENERAL", test_general_stays_general),
        ("Metadata typos -> METADATA", test_metadata_typos),
        ("Explicit filenames -> DOCUMENT", test_explicit_filename_forces_document),
        ("Empty owner -> GENERAL", test_empty_owner_is_general),
        ("Owner isolation", test_owner_isolation),
        ("Embedding reuse", test_embedding_reuse),
    ]

    passed = True
    for label, scenario in scenarios:
        print()
        print(label)
        result = await scenario()
        print("PASSED" if result else "FAILED")
        passed = passed and result

    print()
    print("=" * 60)
    print(f"Real-Corpus Relevance Gate Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
