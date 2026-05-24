"""
retrieval/

Phase 4 — Composite Retrieval Ranking

Modules
-------
lineage_scorer.py    : Lineage proximity scoring via MetadataGraph hop distances
glossary_matcher.py  : Enterprise glossary overlap between query and candidate models
embedding_ranker.py  : Composite 5-factor retrieval scoring engine
semantic_retriever.py: High-level retrieval interface wiring the composite ranker

Design reference: EXPANSION_DESIGN.md §10 — Retrieval Ranking Logic
"""
