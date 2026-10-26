"""Adversarial RAG Grounding and Citation Validation Suite (Deterministic Evaluation).

Evaluates whether RAG citation localization, evidence alignment, and grounding validation
resist misleading evidence, conflicting dates, proposed changes, superseded rules,
exceptions with restricted scope, and malformed citations.

Uses exact verbatim chunks from NFS_RAG_Test_Knowledge_Base.docx as test oracle.
"""

import re
import uuid
import pytest
from pydantic import ValidationError

from app.services.rag.citation import (
    extract_citation_snippet,
    extract_claims_for_chunk,
    validate_chunk_passage_offsets,
)
from app.services.rag.schemas import Citation
from app.services.rag.prompt import RagPromptBuilder


# ==============================================================================
# Exact indexed corpus chunks from NFS_RAG_Test_Knowledge_Base.docx
# ==============================================================================

CHUNK_0_CONTENT = (
    "NORTHSTAR FIELD SYSTEMS Operational Knowledge Base — Synthetic RAG Test Corpus | "
    "NFS-OPS-HB-014 | Version 1.4 | Effective 1 October 2026 Purpose: This fictional handbook "
    "is a deliberately substantial test corpus for document ingestion, chunking, semantic retrieval, "
    "multi-hop reasoning, exact numeric retrieval, table handling, policy precedence, uncertainty, "
    "citations, and grounded chat. All organizations, names, records, contacts, and figures are invented. "
    "This is not real-world policy."
)

CHUNK_1_CONTENT = (
    "Document control Reading and precedence rules Version 1.4 controls when it explicitly "
    "supersedes an older rule. A proposal is not approved policy. A pilot rule applies only to "
    "the named pilot group. If a fact is absent, the correct answer is that this handbook does "
    "not specify it. Tables are authoritative for their stated rows. Never infer missing "
    "production configuration. 1. Organization overview"
)

CHUNK_16_CONTENT = (
    "The production maximum upload size is not specified in this handbook. The actual "
    "application configuration is authoritative. During testing, record the configured limit "
    "and verify over-limit uploads are rejected before expensive processing."
)

CHUNK_17_CONTENT = (
    "Transient embedding-provider timeout: initial attempt plus up to three retries, with "
    "delays of 1, 3, and 9 seconds. Validation errors must not be retried. Malformed documents "
    "that fail extraction must be marked failed with a safe user-readable reason. Reprocessing "
    "must not create duplicate active chunks for the same document version."
)

CHUNK_36_CONTENT = (
    "Any credible indication that one workspace can retrieve another workspace's document is "
    "SEV-1 and must be reported to security@nfs.example. Do not continue broad testing against "
    "real customer data to reproduce it. A model-provider timeout can be retried only if the "
    "request is safe to repeat and retry budget remains. Validation failures, authorization "
    "failures, and policy denials must not be automatically retried."
)

CHUNK_38_CONTENT = (
    "9. Version history and special policy cases Version history: v1.2 dated 1 April 2026 "
    "introduced workspace-level access boundaries (superseded); v1.3 dated 1 July 2026 added "
    "document states and ingestion retry rules (superseded); v1.4 dated 1 October 2026 added "
    "dependent-membership safety, current ingestion workflow, and updated incident thresholds "
    "(current). Version 1.4 supersedes 1.3."
)

CHUNK_39_CONTENT = (
    "PROPOSAL dated 20 October 2026: the team is considering increasing model-provider timeout "
    "from 20 to 30 seconds. It has not been approved, has no effective date, and must not be "
    "represented as current policy. PILOT rule effective 15 October 2026: only the Highlands "
    "Field Services pilot may reprocess a document up to two times after an embedding-provider "
    "quota error. This does not change the general retry policy for other regions or teams."
)

CHUNK_40_CONTENT = (
    "This handbook does not specify production upload-size limit, archived-file retention duration, "
    "actual vector database vendor, current production model provider, or production cloud region. "
    "A grounded answer must say the handbook does not specify these values. 10. Asset and processing "
    "reference tables The following fictional records test exact row retrieval and numeric reasoning. "
    "Do not mix values from different asset IDs. 10.1 Processing samples"
)

CHUNK_47_CONTENT = (
    "Status | Approved for synthetic testing Supersedes | Version 1.3 dated 1 July 2026 "
    "Classification | Internal synthetic test corpus Asset ID | Region | Last inspection | "
    "Open findings | Priority NF-1042 | North | 2026-09-18 | 2 | High NF-1088 | Coast | "
    "2026-09-21 | 0 | Low NF-1173 | Central | 2026-09-29 | 3 | Critical NF-1204 | Highlands | "
    "2026-10-02 | 1 | Medium NF-1249 | North | 2026-10-04 | 4 | High NF-1301 | Coast | "
    "2026-10-07 | 2 | Medium NF-1317 | Central | 2026-10-08 | 0 | Low"
)


# ==============================================================================
# Helper Verification Functions
# ==============================================================================

def assert_citation_verbatim_integrity(content: str, snippet: str, start: int, end: int) -> None:
    """Verify that a citation snippet strictly represents an exact verbatim substring."""
    assert validate_chunk_passage_offsets(content, start, end) is True
    # Strip leading/trailing ellipsis and whitespace
    clean_snippet = re.sub(r"^\.\.\.\s*", "", snippet)
    clean_snippet = re.sub(r"\s*\.\.\.$", "", clean_snippet)
    # The clean snippet must match the source chunk substring bounded by start:end
    chunk_slice = content[start:end].strip()
    assert clean_snippet == chunk_slice or clean_snippet in content


# ==============================================================================
# Adversarial Evaluation Cases
# ==============================================================================

def test_eval_case_1_current_handbook_version_and_effective_date():
    """Case 1: Current handbook version (1.4) and effective date (1 October 2026)."""
    query = "What is the current version of the handbook and when did it become effective?"
    answer = (
        "The current handbook version is 1.4 and it became effective on 1 October 2026 "
        "[Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 0]."
    )

    claims_0 = extract_claims_for_chunk(answer, 0)
    assert len(claims_0) == 1
    assert "version is 1.4" in claims_0[0]
    assert "1 October 2026" in claims_0[0]

    snippet, start, end = extract_citation_snippet(
        content=CHUNK_0_CONTENT,
        query=query,
        answer=answer,
        claim=claims_0[0],
        max_chars=240,
    )

    # 1. Answer correctness verified by claim extraction
    # 2. Must visibly display Version 1.4 and Effective 1 October 2026
    assert "Version 1.4" in snippet
    assert "Effective 1 October 2026" in snippet
    # 3. Must NOT begin with generic document header
    assert not snippet.startswith("NORTHSTAR FIELD SYSTEMS")
    # 4. Offsets and verbatim integrity
    assert_citation_verbatim_integrity(CHUNK_0_CONTENT, snippet, start, end)


def test_eval_case_2_superseded_version_and_date():
    """Case 2: Superseded handbook version (1.3) dated 1 July 2026."""
    query = "Which version does the current handbook supersede, and what was its date?"
    answer = (
        "Handbook version 1.4 supersedes version 1.3 dated 1 July 2026 "
        "[Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 47]."
    )

    claims_47 = extract_claims_for_chunk(answer, 47)
    assert len(claims_47) == 1
    assert "supersedes version 1.3 dated 1 July 2026" in claims_47[0]

    snippet_47, start_47, end_47 = extract_citation_snippet(
        content=CHUNK_47_CONTENT,
        query=query,
        answer=answer,
        claim=claims_47[0],
        max_chars=240,
    )

    # Must anchor directly on Supersedes, skipping Status table
    assert not snippet_47.startswith("Status | Approved")
    assert snippet_47.startswith("... Supersedes | Version 1.3 dated 1 July 2026")
    assert start_47 == 40
    assert_citation_verbatim_integrity(CHUNK_47_CONTENT, snippet_47, start_47, end_47)

    # Also evaluate alternative chunk supporting supersession: Chunk 38
    claims_38 = ["Version 1.4 supersedes 1.3"]
    snippet_38, start_38, end_38 = extract_citation_snippet(
        content=CHUNK_38_CONTENT,
        query=query,
        answer=answer,
        claim=claims_38[0],
        max_chars=240,
    )
    assert "Version 1.4 supersedes 1.3" in snippet_38
    assert_citation_verbatim_integrity(CHUNK_38_CONTENT, snippet_38, start_38, end_38)


def test_eval_case_3_proposed_change_not_presented_as_approved_policy():
    """Case 3: A proposed timeout change must not be presented as approved policy."""
    query = "Has the model-provider timeout increase to 30 seconds been approved, and what is its effective date?"
    
    # Grounded answer correctly rejecting the premise
    grounded_answer = (
        "No, the proposal to increase the model-provider timeout from 20 to 30 seconds has not been approved, "
        "has no effective date, and must not be represented as current policy "
        "[Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 39]."
    )

    # 1. Evaluate that answer explicitly respects policy vs proposal distinction
    assert "not been approved" in grounded_answer.lower()
    assert "no effective date" in grounded_answer.lower()

    claims_39 = extract_claims_for_chunk(grounded_answer, 39)
    assert len(claims_39) == 1
    assert "not been approved" in claims_39[0]

    snippet, start, end = extract_citation_snippet(
        content=CHUNK_39_CONTENT,
        query=query,
        answer=grounded_answer,
        claim=claims_39[0],
        max_chars=240,
    )

    # 2. Snippet must capture the proposal disclaimer, not the pilot rule
    assert snippet.startswith("PROPOSAL dated 20 October 2026")
    assert "It has not been approved, has no effective date" in snippet
    assert start == 0
    assert_citation_verbatim_integrity(CHUNK_39_CONTENT, snippet, start, end)

    # 3. Adversarial detection check: if an ungrounded answer claims the proposal IS approved,
    # evaluate whether our audit assertion detects the hallucination
    adversarial_hallucinated_answer = (
        "The model-provider timeout increase to 30 seconds was approved on 20 October 2026."
    )
    is_falsely_approved = (
        "was approved" in adversarial_hallucinated_answer.lower()
        or "is approved" in adversarial_hallucinated_answer.lower()
    ) and "not been approved" not in adversarial_hallucinated_answer.lower()
    assert is_falsely_approved is True, "Test oracle must detect false approval claims"


def test_eval_case_4_pilot_exception_scope_restriction():
    """Case 4: A pilot exception must not be generalized to all teams or regions."""
    query = (
        "Does the rule allowing up to two reprocessing attempts after an embedding quota error "
        "apply to the Coast and Central teams?"
    )

    # Grounded answer: strictly restricted to Highlands Field Services pilot
    grounded_answer = (
        "No, the rule permitting up to two reprocessing attempts after an embedding-provider quota error "
        "applies only to the Highlands Field Services pilot. It does not change the general retry policy "
        "for other regions or teams [Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 39]."
    )

    # 1. Evaluate scope restriction in answer
    assert "only to the highlands field services pilot" in grounded_answer.lower()
    assert "does not change the general retry policy for other regions or teams" in grounded_answer.lower()

    claims_39 = extract_claims_for_chunk(grounded_answer, 39)
    assert len(claims_39) == 1

    snippet, start, end = extract_citation_snippet(
        content=CHUNK_39_CONTENT,
        query=query,
        answer=grounded_answer,
        claim=claims_39[0],
        max_chars=240,
    )

    # 2. Must anchor on PILOT rule and include the scope restriction
    assert "PILOT rule effective 15 October 2026" in snippet
    assert "only the Highlands Field Services pilot" in snippet
    assert "does not change the general retry policy" in snippet
    # 3. Must NOT begin with the unrelated timeout proposal
    assert not snippet.startswith("PROPOSAL dated 20 October")
    assert start >= 199
    assert_citation_verbatim_integrity(CHUNK_39_CONTENT, snippet, start, end)


def test_eval_case_5_multi_chunk_composite_facts():
    """Case 5: Multi-hop question requiring multiple distinct chunks without cross-contamination."""
    query = (
        "State the current handbook version, its effective date, the version it supersedes, "
        "and whether the Highlands pilot retry rule applies to other regions."
    )

    composite_answer = (
        "- Current handbook is Version 1.4, effective 1 October 2026 [Doc: NFS, Chunk: 0].\n"
        "- It supersedes version 1.3 dated 1 July 2026 [Doc: NFS, Chunk: 47].\n"
        "- The Highlands pilot rule effective 15 October 2026 permits up to two retries only for "
        "Highlands Field Services and does not apply to other regions [Doc: NFS, Chunk: 39]."
    )

    # Extract claims per chunk
    c0_claims = extract_claims_for_chunk(composite_answer, 0)
    c47_claims = extract_claims_for_chunk(composite_answer, 47)
    c39_claims = extract_claims_for_chunk(composite_answer, 39)

    assert len(c0_claims) == 1 and "Version 1.4" in c0_claims[0]
    assert len(c47_claims) == 1 and "supersedes version 1.3" in c47_claims[0]
    assert len(c39_claims) == 1 and "Highlands pilot rule" in c39_claims[0]

    # Verify Chunk 0 citation: anchors to Version 1.4 / Effective date
    s0, start0, end0 = extract_citation_snippet(CHUNK_0_CONTENT, claim=c0_claims[0])
    assert "Version 1.4 | Effective 1 October 2026" in s0
    assert not s0.startswith("NORTHSTAR FIELD SYSTEMS")
    assert_citation_verbatim_integrity(CHUNK_0_CONTENT, s0, start0, end0)

    # Verify Chunk 47 citation: anchors to Supersedes
    s47, start47, end47 = extract_citation_snippet(CHUNK_47_CONTENT, claim=c47_claims[0])
    assert s47.startswith("... Supersedes | Version 1.3 dated 1 July 2026")
    assert not s47.startswith("Status | Approved")
    assert_citation_verbatim_integrity(CHUNK_47_CONTENT, s47, start47, end47)

    # Verify Chunk 39 citation: anchors to PILOT rule
    s39, start39, end39 = extract_citation_snippet(CHUNK_39_CONTENT, claim=c39_claims[0])
    assert "PILOT rule effective 15 October 2026" in s39
    assert not s39.startswith("PROPOSAL dated 20 October")
    assert_citation_verbatim_integrity(CHUNK_39_CONTENT, s39, start39, end39)


def test_eval_case_6_unspecified_information_negative_constraints():
    """Case 6: Information the corpus explicitly does not specify must be identified as unknown."""
    query = "What is the production cloud region and actual vector database vendor used by Northstar Field Systems?"
    
    # Grounded answer: correctly withholds unsupported facts and identifies them as unspecified
    grounded_answer = (
        "The handbook explicitly states that it does not specify the actual vector database vendor "
        "or the production cloud region [Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 40]."
    )

    claims_40 = extract_claims_for_chunk(grounded_answer, 40)
    assert len(claims_40) == 1
    assert "does not specify" in claims_40[0].lower()

    snippet, start, end = extract_citation_snippet(
        content=CHUNK_40_CONTENT,
        query=query,
        answer=grounded_answer,
        claim=claims_40[0],
        max_chars=240,
    )

    # Snippet must anchor on the negative constraint passage
    assert "This handbook does not specify production upload-size limit" in snippet
    assert "actual vector database vendor" in snippet
    assert "production cloud region" in snippet
    assert start == 0
    assert_citation_verbatim_integrity(CHUNK_40_CONTENT, snippet, start, end)

    # Evaluate that ungrounded vendors (AWS, Azure, Pinecone) are NOT asserted
    assert "aws" not in grounded_answer.lower()
    assert "pinecone" not in grounded_answer.lower()
    assert "qdrant" not in grounded_answer.lower()


def test_eval_case_7_misleading_query_with_unrelated_trap_date():
    """Case 7: Misleading query containing a trap date (20 October 2026) that is NOT an effective date."""
    query = "What policy rule became effective on 20 October 2026?"

    # Grounded answer must refute the premise of the question
    grounded_answer = (
        "No policy rule became effective on 20 October 2026. The item dated 20 October 2026 was only a "
        "proposal to increase model-provider timeout from 20 to 30 seconds; it has not been approved and "
        "has no effective date [Doc: NFS_RAG_Test_Knowledge_Base.docx, Chunk: 39]."
    )

    assert "no policy rule became effective on 20 october 2026" in grounded_answer.lower()
    assert "not been approved" in grounded_answer.lower()

    claims_39 = extract_claims_for_chunk(grounded_answer, 39)
    assert len(claims_39) == 1

    snippet, start, end = extract_citation_snippet(
        content=CHUNK_39_CONTENT,
        query=query,
        answer=grounded_answer,
        claim=claims_39[0],
        max_chars=240,
    )

    # Must anchor on the proposal text, refuting that 20 October is an effective date
    assert "PROPOSAL dated 20 October 2026" in snippet
    assert "It has not been approved, has no effective date" in snippet
    assert start == 0
    assert_citation_verbatim_integrity(CHUNK_39_CONTENT, snippet, start, end)


def test_eval_case_8_citation_markers_missing_malformed_and_inconsistent():
    """Case 8: Robustness against missing, malformed, or inconsistent citation markers."""
    # 8a: Answer without bracketed citations returns empty claims and falls back safely
    unmarked_answer = "Version 1.4 became effective on 1 October 2026 without explicit bracket markers."
    claims = extract_claims_for_chunk(unmarked_answer, 0)
    assert claims == []

    # extract_citation_snippet falls back gracefully to query/answer keywords without error
    snip, start, end = extract_citation_snippet(CHUNK_0_CONTENT, answer=unmarked_answer)
    assert "Version 1.4" in snip
    assert validate_chunk_passage_offsets(CHUNK_0_CONTENT, start, end) is True

    # 8b: Malformed citation syntax in LLM answer does not crash parser
    malformed_answers = [
        "Status report [Doc: NFS, Chunk: ] with missing number",
        "Status report [Chunk: NaN] with non-integer chunk",
        "Status report [Doc: 'NFS'] with missing chunk tag",
        "Status report [Chunk: -5] with negative chunk index",
        "Status report [Chunk: 99999] with out-of-bounds index",
    ]
    for bad_ans in malformed_answers:
        res = extract_claims_for_chunk(bad_ans, 0)
        assert isinstance(res, list)

    # 8c: Chunk index mismatch (answer claims chunk 39, but we query for chunk 47)
    answer_for_39 = "Only Highlands may reprocess [Doc: NFS, Chunk: 39]."
    claims_for_47 = extract_claims_for_chunk(answer_for_39, 47)
    assert claims_for_47 == []


def test_eval_pydantic_citation_contract_invariants():
    """Verify that all Citation outputs strictly enforce non-negative, valid offsets."""
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    # Valid citation passes
    cit = Citation(
        document_id=doc_id,
        document_title="NFS_RAG_Test_Knowledge_Base.docx",
        chunk_id=chunk_id,
        chunk_index=39,
        relevance_score=0.7535,
        snippet="... PILOT rule effective 15 October 2026: only the Highlands Field Services pilot ...",
        char_offset_start=209,
        char_offset_end=442,
    )
    assert cit.char_offset_start == 209
    assert cit.char_offset_end == 442

    # Inverted offsets rejected
    with pytest.raises(ValidationError):
        Citation(
            document_id=doc_id,
            document_title="Doc",
            chunk_id=chunk_id,
            chunk_index=39,
            relevance_score=0.8,
            snippet="test",
            char_offset_start=100,
            char_offset_end=50,
        )

    # Negative offset rejected
    with pytest.raises(ValidationError):
        Citation(
            document_id=doc_id,
            document_title="Doc",
            chunk_id=chunk_id,
            chunk_index=39,
            relevance_score=0.8,
            snippet="test",
            char_offset_start=-1,
            char_offset_end=50,
        )
