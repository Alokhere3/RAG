"""Unit tests for deterministic citation passage extraction and offset validation.

Covers all 8 mandatory test requirements:
1. A chunk whose relevant passage appears after an unrelated opening passage.
2. A chunk containing multiple unrelated policy statements.
3. A chunk shorter than the preview limit.
4. An empty or whitespace-only chunk.
5. A chunk with no confidently selectable supporting passage.
6. Preservation of the original citation IDs and metadata.
7. API serialization and frontend compatibility.
8. Rejection of invalid or fabricated passage offsets.
"""

import uuid
import pytest
from pydantic import ValidationError

from app.services.rag.citation import (
    extract_citation_snippet,
    extract_claims_for_chunk,
    validate_chunk_passage_offsets,
)
from app.services.rag.schemas import Citation


# Chunk 39 excerpt from NFS_RAG_Test_Knowledge_Base.docx
CHUNK_39_CONTENT = (
    "PROPOSAL dated 20 October 2026: the team is considering increasing model-provider timeout "
    "from 20 to 30 seconds. It has not been approved, has no effective date, and must not be "
    "represented as current policy. PILOT rule effective 15 October 2026: only the Highlands "
    "Field Services pilot may reprocess a document up to two times after an embedding-provider "
    "quota error. This does not change the general retry policy for other regions or teams."
)


def test_1_relevant_passage_after_unrelated_opening():
    """Requirement 1: Chunk whose relevant passage appears after an unrelated opening passage."""
    query = (
        "Does the Highlands Field Services pilot retry rule apply to all teams? "
        "State its scope and effective date, and cite the supporting passage."
    )

    snippet, start, end = extract_citation_snippet(
        content=CHUNK_39_CONTENT,
        query=query,
        max_chars=240,
    )

    # Must NOT begin with the unrelated timeout proposal
    assert not snippet.startswith("PROPOSAL dated 20 October")
    # Must capture the pilot rule
    assert "PILOT rule effective 15 October 2026" in snippet
    assert "Highlands Field Services" in snippet
    # Must preserve exact character boundary in source chunk
    assert start >= 199
    assert CHUNK_39_CONTENT[start:end] in CHUNK_39_CONTENT
    # Ellipsis prefix indicates passage was extracted from later in the chunk
    assert snippet.startswith("... ")


def test_2_multiple_unrelated_policy_statements():
    """Requirement 2: Chunk containing multiple unrelated policy statements."""
    multi_policy_chunk = (
        "1. Remote Work Stipend: Employees receive $500 annually for home office equipment upon manager approval.\n"
        "2. Security Incident Reporting: Any suspected credential leak must be escalated to security@example.com within 1 hour.\n"
        "3. Data Retention Schedule: Temporary scratch files are automatically purged after 14 calendar days."
    )

    # Query targeting Policy 2 (Security)
    query_security = "What is the escalation window and email for suspected credential leaks?"
    snippet_sec, start_sec, end_sec = extract_citation_snippet(multi_policy_chunk, query=query_security, max_chars=180)
    assert "Security Incident Reporting" in snippet_sec
    assert "security@example.com" in snippet_sec
    assert "Remote Work Stipend" not in snippet_sec

    # Query targeting Policy 1 (Remote Work)
    query_remote = "How much is the annual home office stipend?"
    snippet_rem, start_rem, end_rem = extract_citation_snippet(multi_policy_chunk, query=query_remote, max_chars=180)
    assert "Remote Work Stipend" in snippet_rem
    assert "$500" in snippet_rem
    assert "Security Incident" not in snippet_rem


def test_3_chunk_shorter_than_preview_limit():
    """Requirement 3: Chunk shorter than the preview limit."""
    short_content = "Brief operational notice: all maintenance windows occur on Sundays at 02:00 UTC."
    snippet, start, end = extract_citation_snippet(short_content, query="When do maintenance windows occur?", max_chars=200)

    # Shorter than limit: return full content without ellipses
    assert snippet == short_content
    assert start == 0
    assert end == len(short_content)
    assert not snippet.startswith("...")
    assert not snippet.endswith("...")


def test_4_empty_or_whitespace_chunk():
    """Requirement 4: Empty or whitespace-only chunk."""
    assert extract_citation_snippet("", query="anything") == ("", 0, 0)
    assert extract_citation_snippet("   ", query="anything") == ("", 0, 0)
    assert extract_citation_snippet("\n\t  \n", query="anything") == ("", 0, 0)


def test_5_no_confidently_selectable_passage_falls_back_to_prefix():
    """Requirement 5: Chunk with no confidently selectable supporting passage falls back safely."""
    irrelevant_chunk = (
        "Visitor parking regulations: All guest vehicles must register at the reception desk upon arrival. "
        "Parking passes are valid for a maximum of 8 hours and must be visibly displayed on the vehicle dashboard. "
        "Vehicles parked in unauthorized stalls will be towed at the owner's expense."
    )
    # Query completely unrelated to parking with zero matching terms
    unrelated_query = "superconducting qubits quantum entanglement cryogenic dilution"

    snippet, start, end = extract_citation_snippet(irrelevant_chunk, query=unrelated_query, max_chars=120)

    # Fallback must be safe, non-fabricated prefix of chunk with ellipsis
    assert snippet.startswith("Visitor parking regulations")
    assert snippet.endswith("...")
    assert start == 0
    assert end == 120


def test_6_preservation_of_citation_metadata_and_ids():
    """Requirement 6: Preservation of the original citation IDs and metadata."""
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    score = 0.7535
    chunk_idx = 39

    snippet, start, end = extract_citation_snippet(CHUNK_39_CONTENT, query="Highlands pilot retry rule")

    citation = Citation(
        document_id=doc_id,
        document_title="NFS_RAG_Test_Knowledge_Base.docx",
        chunk_id=chunk_id,
        chunk_index=chunk_idx,
        relevance_score=score,
        snippet=snippet,
        char_offset_start=start,
        char_offset_end=end,
    )

    assert citation.document_id == doc_id
    assert citation.chunk_id == chunk_id
    assert citation.chunk_index == 39
    assert citation.relevance_score == 0.7535
    assert citation.document_title == "NFS_RAG_Test_Knowledge_Base.docx"
    assert "PILOT rule" in citation.snippet
    assert citation.char_offset_start == start
    assert citation.char_offset_end == end


def test_7_api_serialization_and_frontend_compatibility():
    """Requirement 7: API serialization and frontend compatibility."""
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    citation = Citation(
        document_id=doc_id,
        document_title="Sample Document",
        chunk_id=chunk_id,
        chunk_index=3,
        relevance_score=0.88,
        snippet="Verified passage excerpt.",
        char_offset_start=50,
        char_offset_end=75,
    )

    data = citation.model_dump(mode="json")

    # Required by frontend CitationItem interface in types/chat.ts:
    # document_id, document_title, chunk_id, chunk_index, relevance_score, snippet
    assert isinstance(data["document_id"], str)
    assert data["document_title"] == "Sample Document"
    assert isinstance(data["chunk_id"], str)
    assert data["chunk_index"] == 3
    assert data["relevance_score"] == 0.88
    assert data["snippet"] == "Verified passage excerpt."
    # Optional offsets serialized cleanly
    assert data["char_offset_start"] == 50
    assert data["char_offset_end"] == 75


def test_8_rejection_of_invalid_or_fabricated_passage_offsets():
    """Requirement 8: Rejection of invalid or fabricated passage offsets."""
    content = "A standard source chunk content for offset validation testing."

    # 1. validate_chunk_passage_offsets helper validation
    assert validate_chunk_passage_offsets(content, 0, 10) is True
    assert validate_chunk_passage_offsets(content, None, None) is True
    # Invalid: negative start
    assert validate_chunk_passage_offsets(content, -1, 10) is False
    # Invalid: end before start
    assert validate_chunk_passage_offsets(content, 20, 10) is False
    # Invalid: end exceeds content length
    assert validate_chunk_passage_offsets(content, 0, len(content) + 50) is False
    # Invalid: half-specified offsets
    assert validate_chunk_passage_offsets(content, 10, None) is False
    assert validate_chunk_passage_offsets(content, None, 10) is False

    # 2. Pydantic model validator validation
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    # Negative offset must raise ValidationError
    with pytest.raises(ValidationError):
        Citation(
            document_id=doc_id,
            document_title="Doc",
            chunk_id=chunk_id,
            chunk_index=0,
            relevance_score=0.9,
            snippet="test",
            char_offset_start=-5,
            char_offset_end=10,
        )

    # Inverted offsets (end < start) must raise ValidationError
    with pytest.raises(ValidationError):
        Citation(
            document_id=doc_id,
            document_title="Doc",
            chunk_id=chunk_id,
            chunk_index=0,
            relevance_score=0.9,
            snippet="test",
            char_offset_start=30,
            char_offset_end=10,
        )

    # Half-specified offsets must raise ValidationError
    with pytest.raises(ValidationError):
        Citation(
            document_id=doc_id,
            document_title="Doc",
            chunk_id=chunk_id,
            chunk_index=0,
            relevance_score=0.9,
            snippet="test",
            char_offset_start=10,
            char_offset_end=None,
        )


# Chunk 47 excerpt from NFS_RAG_Test_Knowledge_Base.docx
CHUNK_47_CONTENT = (
    "Status | Approved for synthetic testing Supersedes | Version 1.3 dated 1 July 2026 "
    "Classification | Internal synthetic test corpus Asset ID | Region | Last inspection | "
    "Open findings | Priority NF-1042 | North | 2026-09-18 | 2 | High NF-1088 | Coast | "
    "2026-09-21 | 0 | Low NF-1173 | Central | 2026-09-29 | 3 | Critical NF-1204 | Highlands | "
    "2026-10-02 | 1 | Medium NF-1249 | North | 2026-10-04 | 4 | High NF-1301 | Coast | "
    "2026-10-07 | 2 | Medium NF-1317 | Central | 2026-10-08 | 0 | Low"
)

# Chunk 0 excerpt from NFS_RAG_Test_Knowledge_Base.docx
CHUNK_0_CONTENT = (
    "NORTHSTAR FIELD SYSTEMS Operational Knowledge Base — Synthetic RAG Test Corpus | "
    "NFS-OPS-HB-014 | Version 1.4 | Effective 1 October 2026 Purpose: This fictional handbook "
    "is a deliberately substantial test corpus for document ingestion, chunking, semantic retrieval, "
    "multi-hop reasoning, exact numeric retrieval, table handling, policy precedence, uncertainty, "
    "citations, and grounded chat. All organizations, names, records, contacts, and figures are invented. "
    "This is not real-world policy."
)


def test_version_and_supersession_statements():
    """Requirement: Version and supersession statement alignment (favors Supersedes over Status table)."""
    query = "what is the handbook version, its effective date, and the version it supersedes?"
    raw_answer = (
        "The handbook is Version 1.4, effective 1 October 2026 [Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 0]. "
        "It supersedes version 1.3 dated 1 July 2026 [Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 47]."
    )

    claims_47 = extract_claims_for_chunk(raw_answer, 47)
    assert len(claims_47) == 1
    assert "supersedes version 1.3 dated 1 July 2026" in claims_47[0]

    snippet, start, end = extract_citation_snippet(
        content=CHUNK_47_CONTENT,
        query=query,
        answer=raw_answer,
        claim=claims_47[0],
        max_chars=240,
    )

    # Must NOT begin with the status table
    assert not snippet.startswith("Status | Approved")
    # Must explicitly show the Supersedes evidence
    assert "Supersedes | Version 1.3 dated 1 July 2026" in snippet
    assert snippet.startswith("... Supersedes | Version 1.3 dated 1 July 2026")
    # Start offset must accurately point to index 40 where Supersedes starts
    assert start == 40
    # Must be exact verbatim substring
    assert CHUNK_47_CONTENT[start:end] in CHUNK_47_CONTENT
    assert validate_chunk_passage_offsets(CHUNK_47_CONTENT, start, end) is True


def test_effective_dates_alignment():
    """Requirement: Effective dates alignment (anchors to Version 1.4 and Effective 1 October 2026)."""
    query = "What is the effective date of handbook version 1.4?"
    raw_answer = (
        "The handbook version is 1.4 and its effective date is 1 October 2026 "
        "[Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 0]."
    )

    claims_0 = extract_claims_for_chunk(raw_answer, 0)
    assert len(claims_0) == 1
    assert "effective date is 1 October 2026" in claims_0[0]

    snippet, start, end = extract_citation_snippet(
        content=CHUNK_0_CONTENT,
        query=query,
        answer=raw_answer,
        claim=claims_0[0],
        max_chars=240,
    )

    # Must NOT begin with the generic title prefix
    assert not snippet.startswith("NORTHSTAR FIELD SYSTEMS")
    # Must highlight the version and effective date
    assert "Effective 1 October 2026" in snippet
    assert "Version 1.4" in snippet
    assert validate_chunk_passage_offsets(CHUNK_0_CONTENT, start, end) is True
    assert CHUNK_0_CONTENT[start:end] in CHUNK_0_CONTENT


def test_multiple_claims_in_one_answer():
    """Requirement: Multiple claims in one answer correctly map to distinct chunks."""
    multi_claim_answer = (
        "- Current handbook is Version 1.4 with effective date 1 October 2026 [Doc: NFS, Chunk: 0]\n"
        "- It supersedes version 1.3 dated 1 July 2026 [Doc: NFS, Chunk: 47]\n"
        "- Under the pilot rule effective 15 October 2026, Highlands field services may reprocess [Doc: NFS, Chunk: 39]"
    )

    # Extract claims per chunk index
    claims_chunk_0 = extract_claims_for_chunk(multi_claim_answer, 0)
    claims_chunk_47 = extract_claims_for_chunk(multi_claim_answer, 47)
    claims_chunk_39 = extract_claims_for_chunk(multi_claim_answer, 39)

    assert any("Version 1.4" in c and "1 October 2026" in c for c in claims_chunk_0)
    assert any("supersedes version 1.3" in c for c in claims_chunk_47)
    assert any("pilot rule effective 15 October 2026" in c for c in claims_chunk_39)

    # Snippet for Chunk 0 anchors on Version 1.4 / Effective date
    snip_0, start_0, end_0 = extract_citation_snippet(
        CHUNK_0_CONTENT, answer=multi_claim_answer, claim=claims_chunk_0[0]
    )
    assert "Version 1.4 | Effective 1 October 2026" in snip_0
    assert not snip_0.startswith("NORTHSTAR FIELD SYSTEMS")

    # Snippet for Chunk 47 anchors on Supersedes
    snip_47, start_47, end_47 = extract_citation_snippet(
        CHUNK_47_CONTENT, answer=multi_claim_answer, claim=claims_chunk_47[0]
    )
    assert snip_47.startswith("... Supersedes | Version 1.3 dated 1 July 2026")
    assert not snip_47.startswith("Status | Approved")

    # Snippet for Chunk 39 anchors on PILOT rule
    snip_39, start_39, end_39 = extract_citation_snippet(
        CHUNK_39_CONTENT, answer=multi_claim_answer, claim=claims_chunk_39[0]
    )
    assert "PILOT rule effective 15 October 2026" in snip_39
    assert not snip_39.startswith("PROPOSAL dated 20 October")


def test_chunks_containing_unrelated_facts():
    """Requirement: Chunks containing unrelated facts isolate the targeted statement."""
    composite_chunk = (
        "Travel Expenses: Meal per diem is capped at $75 per day for domestic travel.\n"
        "Incident Escalation: Priority 1 outages require incident commander assignment within 15 minutes.\n"
        "Hardware Refresh: Developer laptops are scheduled for replacement every 36 months."
    )

    # Targeting Fact 2 (Outage SLA)
    claim_escalation = "Priority 1 outages require incident commander assignment within 15 minutes"
    snip_esc, s_esc, e_esc = extract_citation_snippet(
        composite_chunk, claim=claim_escalation, max_chars=140
    )
    assert "Incident Escalation: Priority 1 outages" in snip_esc
    assert "within 15 minutes" in snip_esc
    assert "Travel Expenses" not in snip_esc
    assert "Hardware Refresh" not in snip_esc
    assert validate_chunk_passage_offsets(composite_chunk, s_esc, e_esc) is True

    # Targeting Fact 3 (Hardware Refresh)
    claim_hardware = "Developer laptops are scheduled for replacement every 36 months"
    snip_hw, s_hw, e_hw = extract_citation_snippet(
        composite_chunk, claim=claim_hardware, max_chars=140
    )
    assert "Hardware Refresh: Developer laptops" in snip_hw
    assert "Travel Expenses" not in snip_hw
    assert "Incident Escalation" not in snip_hw
    assert validate_chunk_passage_offsets(composite_chunk, s_hw, e_hw) is True


def test_fallback_behavior_when_no_reliable_matching_passage():
    """Requirement: Fallback behavior when no reliable matching passage exists."""
    obscure_chunk = (
        "Section 9.4.2 Archival Procedures: Microfiche records stored prior to digital conversion "
        "are cataloged in Annex C, Room 104 under climate-controlled conditions."
    )
    completely_unrelated_claim = "Quantum cryptography key exchange using entanglement distribution"

    snippet, start, end = extract_citation_snippet(
        obscure_chunk, claim=completely_unrelated_claim, max_chars=80
    )

    # Safe fallback to chunk beginning with valid boundaries
    assert start == 0
    assert end <= 80
    assert snippet.startswith("Section 9.4.2 Archival Procedures")
    assert snippet.endswith("...")
    assert validate_chunk_passage_offsets(obscure_chunk, start, end) is True


def test_comma_separated_multi_chunk_citation_parsing():
    """Regression test: Comma-separated multi-chunk citation markers associate claim with all listed chunks."""
    # Case 1: [Doc: KB.docx, Chunk: 38, 47]
    answer_supersedes = (
        "* **Version it supersedes:** Version 1.3 dated 1 July 2026 "
        "[Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 38, 47]"
    )
    claims_38 = extract_claims_for_chunk(answer_supersedes, 38)
    claims_47 = extract_claims_for_chunk(answer_supersedes, 47)

    assert len(claims_38) == 1
    assert len(claims_47) == 1
    assert claims_38 == claims_47
    assert "Version it supersedes:** Version 1.3 dated 1 July 2026" in claims_38[0]

    # Non-cited sub-digits must NOT falsely match
    assert extract_claims_for_chunk(answer_supersedes, 3) == []
    assert extract_claims_for_chunk(answer_supersedes, 8) == []
    assert extract_claims_for_chunk(answer_supersedes, 4) == []
    assert extract_claims_for_chunk(answer_supersedes, 7) == []

    # Case 2: [Doc: KB.docx, Chunk: 39, 1]
    answer_pilot = (
        "* **Application of the Highlands pilot retry rule to other regions:** "
        "No, the pilot rule applies only to the named pilot group (the Highlands Field Services pilot) "
        "and does not change the general retry policy for other regions or teams "
        "[Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 39, 1]."
    )
    claims_39 = extract_claims_for_chunk(answer_pilot, 39)
    claims_1 = extract_claims_for_chunk(answer_pilot, 1)

    assert len(claims_39) == 1
    assert len(claims_1) == 1
    assert claims_39 == claims_1
    assert "No, the pilot rule applies only to the named pilot group" in claims_39[0]

    # Non-cited sub-digits must NOT falsely match
    assert extract_claims_for_chunk(answer_pilot, 9) == []
    assert extract_claims_for_chunk(answer_pilot, 3) == []


def test_single_and_multi_chunk_marker_variants():
    """Verify single-chunk markers and multiple distinct marker tags remain fully supported."""
    single_tag_answer = "Claim with colon tag [Chunk: 47] and space tag [Chunk 38]."
    assert len(extract_claims_for_chunk(single_tag_answer, 47)) == 1
    assert len(extract_claims_for_chunk(single_tag_answer, 38)) == 1
    assert extract_claims_for_chunk(single_tag_answer, 99) == []

    multi_tag_answer = "Claim with multiple distinct tags [Doc: KB.docx, Chunk: 0, Chunk: 47]."
    assert len(extract_claims_for_chunk(multi_tag_answer, 0)) == 1
    assert len(extract_claims_for_chunk(multi_tag_answer, 47)) == 1

    chunks_plural_answer = "Claim with plural Chunks tag [Doc: KB.docx, Chunks: 12, 34]."
    assert len(extract_claims_for_chunk(chunks_plural_answer, 12)) == 1
    assert len(extract_claims_for_chunk(chunks_plural_answer, 34)) == 1


def test_malformed_and_edge_case_citation_markers_safety():
    """Verify missing, malformed, negative, or non-integer chunk indices fail safely."""
    # Empty / whitespace answers
    assert extract_claims_for_chunk("", 0) == []
    assert extract_claims_for_chunk("   \n\t  ", 0) == []

    # Malformed markers do not crash
    assert extract_claims_for_chunk("Status [Doc: NFS, Chunk: ]", 0) == []
    assert extract_claims_for_chunk("Status [Chunk: NaN]", 0) == []
    assert extract_claims_for_chunk("Status [Doc: 'NFS']", 0) == []
    assert extract_claims_for_chunk("Status [Chunk: 99999]", 0) == []
    assert extract_claims_for_chunk("Unclosed bracket [Chunk: 47", 47) == []

    # Negative chunk indices
    neg_answer = "Negative index claim [Chunk: -5]"
    assert extract_claims_for_chunk(neg_answer, 0) == []
    assert len(extract_claims_for_chunk(neg_answer, -5)) == 1

    # Calling with non-integer or unusual types fails safely without raising exceptions
    assert isinstance(extract_claims_for_chunk("Text [Chunk: 47]", "47"), list)
    assert isinstance(extract_claims_for_chunk("Text [Chunk: 47]", -1), list)


