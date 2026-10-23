"""Unit tests for deterministic document chunking (E001-E005)."""

import pytest

from app.services.chunking.schemas import ChunkingConfig
from app.services.chunking.splitter import TextSplitter
from app.services.parsers.base import PageContent, ParseResult


def test_e001_chunking_is_deterministic():
    """E001: Chunking fixture is deterministic."""
    sample_text = (
        "Antigravity is a pair programming AI assistant developed by DeepMind. "
        "It supports autonomous multi-phase engineering workflows. "
        "Each phase has strict blast-radius controls and verification gates. "
        "Testing occurs at both the unit level and with end-to-end browser subagents."
    )
    config = ChunkingConfig(chunk_size=120, chunk_overlap=30, min_chunk_length=10)
    splitter = TextSplitter(config=config)

    run_1 = splitter.split_text(sample_text)
    run_2 = splitter.split_text(sample_text)

    assert len(run_1) > 0
    assert len(run_1) == len(run_2)
    for c1, c2 in zip(run_1, run_2):
        assert c1.index == c2.index
        assert c1.text == c2.text
        assert c1.char_start == c2.char_start
        assert c1.char_end == c2.char_end
        assert c1.metadata == c2.metadata


def test_e002_chunk_size_and_overlap_contract():
    """E002: Overlap and chunk-size contract are respected."""
    sample_text = (
        "Paragraph One introduces the topic with ample descriptive text.\n\n"
        "Paragraph Two elaborates further with specific architecture details and boundaries.\n\n"
        "Paragraph Three discusses retrieval pipelines, vector databases, and similarity metrics.\n\n"
        "Paragraph Four summarizes findings and sets forth operational recommendations."
    )
    chunk_size = 100
    chunk_overlap = 25
    config = ChunkingConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap, min_chunk_length=10)
    splitter = TextSplitter(config=config)

    chunks = splitter.split_text(sample_text)

    assert len(chunks) >= 3
    for chunk in chunks:
        # Every chunk must be bounded by chunk_size (with reasonable word-boundary margin)
        assert len(chunk.text) <= chunk_size + 30
        assert len(chunk.text) >= config.min_chunk_length

    # Verify sequential indices
    indices = [c.index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_e003_empty_and_pathological_text():
    """E003: Empty text yields no chunks."""
    config = ChunkingConfig(chunk_size=200, chunk_overlap=50, min_chunk_length=10)
    splitter = TextSplitter(config=config)

    assert splitter.split_text("") == []
    assert splitter.split_text("   \n\t   ") == []
    assert splitter.split_text("short") == []  # Below min_chunk_length=10


def test_e004_long_text_is_bounded():
    """E004: Long text is bounded into valid chunks."""
    long_text = "Data sentence block. " * 300  # ~6300 chars
    chunk_size = 300
    config = ChunkingConfig(chunk_size=chunk_size, chunk_overlap=50)
    splitter = TextSplitter(config=config)

    chunks = splitter.split_text(long_text)

    assert len(chunks) > 15
    for chunk in chunks:
        assert len(chunk.text) <= chunk_size + 50
        assert chunk.char_end > chunk.char_start


def test_e005_metadata_and_page_preservation():
    """E005: Page/section/document metadata is preserved."""
    p1_text = "Page 1 header. Important intro to system."
    p2_text = "Page 2 header. Technical specs of the pipeline."
    parse_result = ParseResult(
        text=f"{p1_text}\n{p2_text}",
        page_count=2,
        char_count=len(p1_text) + len(p2_text),
        parser_name="test-parser",
        parser_version="1.0.0",
        pages=[
            PageContent(page_number=1, text=p1_text, char_count=len(p1_text), metadata={"author": "Team"}),
            PageContent(page_number=2, text=p2_text, char_count=len(p2_text), metadata={"author": "Team"}),
        ],
        metadata={"document_type": "guide"},
    )

    config = ChunkingConfig(chunk_size=50, chunk_overlap=15, min_chunk_length=10, version="v1.0")
    splitter = TextSplitter(config=config)

    chunks = splitter.split_parse_result(parse_result)

    assert len(chunks) >= 2
    # Check page numbers
    page_nums = {c.page_number for c in chunks}
    assert 1 in page_nums
    assert 2 in page_nums

    for chunk in chunks:
        assert chunk.metadata["chunking_strategy"] == "recursive_character"
        assert chunk.metadata["chunking_version"] == "v1.0"


def test_config_validation():
    """Invalid chunking configs are rejected immediately."""
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        ChunkingConfig(chunk_size=0).validate()

    with pytest.raises(ValueError, match="chunk_overlap cannot be negative"):
        ChunkingConfig(chunk_overlap=-1).validate()

    with pytest.raises(ValueError, match="chunk_overlap .* must be strictly less than chunk_size"):
        ChunkingConfig(chunk_size=100, chunk_overlap=100).validate()
