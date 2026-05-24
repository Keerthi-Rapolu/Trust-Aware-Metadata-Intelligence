"""
tests/conftest.py  — shared pytest fixtures for Phase 1 + Phase 2 tests.

Key fixtures
------------
sample_manifest   : dict   — loaded from data/sample_manifest.json
mock_embed_fn     : callable(str) -> list[float]
                    Deterministic 384-dim embedding that NEVER calls Ollama.
                    Safe for CI and offline test runs.
glossary          : dict   — loaded from data/glossary.json
graph             : MetadataGraph  — built from sample_manifest + lineage edges
"""

import hashlib
import json
import random
from pathlib import Path

import pytest

from ingestion.manifest_ingestor  import ManifestIngestor
from ingestion.lineage_parser     import LineageParser
from ingestion.graph_store        import MetadataGraph

_MANIFEST_PATH = Path(__file__).parent.parent / "data" / "sample_manifest.json"
_GLOSSARY_PATH = Path(__file__).parent.parent / "data" / "glossary.json"


@pytest.fixture(scope="session")
def sample_manifest() -> dict:
    """Load the development sample manifest once per test session."""
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def mock_embed_fn():
    """
    Deterministic 384-dim embedding function seeded by MD5(text).
    Does NOT call Ollama or any network resource — safe for all tests.
    """
    def _embed(text: str) -> list:
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (10 ** 9)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(384)]

    return _embed


@pytest.fixture(scope="session")
def glossary() -> dict:
    """Load the business glossary from data/glossary.json once per session."""
    with open(_GLOSSARY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def graph(sample_manifest) -> MetadataGraph:
    """
    Build a MetadataGraph from the sample manifest, including:
      - model nodes (with completeness, domain, tags)
      - lineage edges (explicit_fk + lineage_dependency)
    Ready for use by Phase 2 reasoning components.
    """
    ingestor = ManifestIngestor()
    parser   = LineageParser()

    records = ingestor.extract_all(sample_manifest)
    edges   = parser.extract_edges(sample_manifest)

    mg = MetadataGraph()
    mg.add_model_nodes(records)

    for edge in edges:
        mg.graph.add_edge(
            edge["upstream"],
            edge["downstream"],
            edge_type    = edge["edge_type"],
            left_column  = edge.get("left_column"),
            right_column = edge.get("right_column"),
        )

    return mg
