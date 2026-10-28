"""Unit tests for answer sanitization and normalization (Phase Hardening)."""

import pytest
from app.services.rag.sanitizer import sanitize_answer


def test_sanitize_answer_removes_standard_doc_chunk_marker():
    raw = "The vacation allowance is 25 days [Doc: handbook.txt, Chunk: 0]."
    expected = "The vacation allowance is 25 days."
    assert sanitize_answer(raw) == expected


def test_sanitize_answer_removes_doc_chunk_with_quotes():
    raw = 'The standard handbook is Version 1.4 [Doc: "NFS Operational Handbook", Chunk: 12].'
    expected = "The standard handbook is Version 1.4."
    assert sanitize_answer(raw) == expected


def test_sanitize_answer_removes_multiple_markers():
    raw = (
        "- Rule 1 applies to production [Doc: NFS, Chunk: 0].\n"
        "- Rule 2 was superseded [Doc: NFS, Chunk: 47].\n"
        "- Exception for Highlands [Doc: KB.docx, Chunk: 38, 47]."
    )
    expected = (
        "- Rule 1 applies to production.\n"
        "- Rule 2 was superseded.\n"
        "- Exception for Highlands."
    )
    assert sanitize_answer(raw) == expected


def test_sanitize_answer_removes_chunk_only_marker():
    raw = "Refer to the pilot guidelines [Chunk: 47] for details."
    expected = "Refer to the pilot guidelines for details."
    assert sanitize_answer(raw) == expected

    raw2 = "Under the pilot rule [Chunks: 1, 2, 3]."
    expected2 = "Under the pilot rule."
    assert sanitize_answer(raw2) == expected2


def test_sanitize_answer_removes_fencing_tags():
    raw = "Some introductory text [Document: handbook.txt (ID: 123, Chunk: 0)] with answer [/Document]."
    expected = "Some introductory text with answer."
    assert sanitize_answer(raw) == expected


def test_sanitize_answer_preserves_legitimate_brackets_and_markdown():
    # Markdown links with Document/Documentation label must NOT be touched
    raw_md1 = "Visit [Google Documentation](https://google.com) for more details."
    assert sanitize_answer(raw_md1) == raw_md1

    raw_md2 = "See the [Document Guide](https://internal.corp/docs) for full details."
    assert sanitize_answer(raw_md2) == raw_md2

    # Words starting with Doc such as Docker must NOT be touched
    raw_docker = "Deploy using [Docker container v2] image."
    assert sanitize_answer(raw_docker) == raw_docker

    # Code arrays and indexing must NOT be touched
    raw_code = "Use `arr[0]` or `matrix[i][j]` when accessing elements."
    assert sanitize_answer(raw_code) == raw_code

    # Technical references and standards
    raw_rfc = "Refer to [RFC 2616] and [ISO 27001] standard guidelines."
    assert sanitize_answer(raw_rfc) == raw_rfc

    # Numerical brackets and list notes
    raw_brackets = "See items [1], [2], or [Note: approved by sec team]."
    assert sanitize_answer(raw_brackets) == raw_brackets

    # Version tags
    raw_ver = "Release tag is [v1.4.0]."
    assert sanitize_answer(raw_ver) == raw_ver


def test_sanitize_answer_removes_source_and_context_tags():
    raw = "[Context] Facts are: [Source: handbook.pdf] PTO is 20 days [Chunk 3]. [/Context]"
    expected = "Facts are: PTO is 20 days."
    assert sanitize_answer(raw) == expected


def test_sanitize_answer_edge_cases():
    assert sanitize_answer(None) == ""
    assert sanitize_answer("") == ""
    assert sanitize_answer("   ") == ""
    clean_text = "Standard answer without any markers."
    assert sanitize_answer(clean_text) == clean_text
