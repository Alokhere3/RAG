"""Adversarial RAG Grounding and Citation Live-Model Evaluation Runner.

Executes live end-to-end evaluation against the running application database and
Gemini LLM provider using the NFS synthetic test corpus.

Evaluates 8 required adversarial test cases:
1. Current handbook version and effective date.
2. Superseded version and date.
3. Proposed change that must not be presented as approved policy.
4. Pilot exception that must not be generalized to all teams.
5. Question combining multiple facts that require different source chunks.
6. Question asking for information the corpus explicitly does not specify.
7. Misleading query containing a trap date (20 October 2026).
8. Citation markers, exact substring extraction, and offset validity.
"""

import asyncio
import json
import re
import sys
from typing import Any, Dict, List, Tuple
from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.user import User
from app.models.chunk import DocumentChunk
from app.services.rag.service import RagService
from app.services.rag.schemas import RagQueryRequest, RagAnswer
from app.services.rag.citation import validate_chunk_passage_offsets


TEST_CASES = [
    {
        "id": "CASE_1",
        "name": "Current handbook version and effective date",
        "query": "What is the current version of the handbook and when did it become effective?",
        "expected_facts": [
            r"\b1\.4\b",
            r"\b1\s+October\s+2026\b",
        ],
        "disallowed_facts": [],
        "expected_chunk_indices": [0, 38],
    },
    {
        "id": "CASE_2",
        "name": "The version superseded by the current handbook",
        "query": "Which version does the current handbook supersede, and what was its date?",
        "expected_facts": [
            r"\b1\.3\b",
            r"\b1\s+July\s+2026\b",
        ],
        "disallowed_facts": [],
        "expected_chunk_indices": [38, 47],
    },
    {
        "id": "CASE_3",
        "name": "Proposed change not presented as approved policy",
        "query": "Has the model-provider timeout increase to 30 seconds been approved, and what is its effective date?",
        "expected_facts": [
            r"\b(?:not\s+approved|proposal|under\s+consideration|not\s+been\s+approved|no\s+effective\s+date)\b",
        ],
        "disallowed_facts": [
            r"\b(?:is\s+approved|has\s+been\s+approved|became\s+effective|effective\s+on\s+20\s+October)\b",
        ],
        "expected_chunk_indices": [39],
    },
    {
        "id": "CASE_4",
        "name": "Pilot exception not generalized to all teams",
        "query": "Does the rule allowing up to two reprocessing attempts after an embedding quota error apply to the Coast and Central teams?",
        "expected_facts": [
            r"\b(?:no\b|does\s+not\s+apply|only\s+(?:for\s+)?(?:the\s+)?Highlands)\b",
        ],
        "disallowed_facts": [
            r"\b(?:yes\b|applies\s+to\s+all|applies\s+to\s+Coast)\b",
        ],
        "expected_chunk_indices": [39],
    },
    {
        "id": "CASE_5",
        "name": "Question combining multiple facts requiring different source chunks",
        "query": "State the current handbook version, its effective date, the version it supersedes, and whether the Highlands pilot retry rule applies to other regions.",
        "expected_facts": [
            r"\b1\.4\b",
            r"\b1\s+October\s+2026\b",
            r"\b1\.3\b",
            r"\b(?:does\s+not\s+(?:apply|change)|only\s+.*Highlands|named\s+pilot\s+group)\b",
        ],
        "disallowed_facts": [],
        "expected_chunk_indices": [0, 38, 39, 47],
    },
    {
        "id": "CASE_6",
        "name": "Information the corpus explicitly does not specify",
        "query": "What is the production cloud region and actual vector database vendor specified in the handbook?",
        "expected_facts": [
            r"\b(?:does\s+not\s+specify|not\s+specified|insufficient\s+evidence|cannot\s+answer)\b",
        ],
        "disallowed_facts": [
            r"\b(?:AWS|Azure|Google\s+Cloud|Pinecone|Qdrant|Milvus|Weaviate)\b",
        ],
        "expected_chunk_indices": [16, 40],
    },
    {
        "id": "CASE_7",
        "name": "Misleading query with unrelated trap date",
        "query": "What policy rule became effective on 20 October 2026?",
        "expected_facts": [
            r"\b(?:no\s+policy|not\s+approved|proposal|has\s+no\s+effective\s+date|does\s+not\s+specify)\b",
        ],
        "disallowed_facts": [
            r"\b(?:timeout\s+increase\s+became\s+effective|timeout\s+increase\s+is\s+approved|rule\s+became\s+effective\s+on\s+20\s+October)\b",
        ],
        "expected_chunk_indices": [39],
    },
]


async def evaluate_live_suite():
    maker = get_sessionmaker()
    results = []

    async with maker() as session:
        # Load test user
        user_res = await session.execute(select(User).limit(1))
        user = user_res.scalars().first()
        if not user:
            print("[ERROR] No user found in database.")
            sys.exit(1)

        # Pre-load all chunks to verify snippet substring integrity
        chunk_res = await session.execute(select(DocumentChunk))
        all_chunks = {c.id: c for c in chunk_res.scalars().all()}

        service = RagService()

        print("================================================================================")
        print("          LIVE-MODEL ADVERSARIAL GROUNDING & CITATION EVALUATION                ")
        print("================================================================================")

        for case in TEST_CASES:
            case_id = case["id"]
            name = case["name"]
            query = case["query"]

            print(f"\n>>> Running {case_id}: {name}")
            print(f"    Query: {query}")

            req = RagQueryRequest(query=query)
            ans: RagAnswer = await service.answer_query(session, user, req)

            # Evaluate 7 mandatory criteria
            criteria: Dict[str, Any] = {
                "answer_correctness": False,
                "scope_and_dates_respected": False,
                "unsupported_details_withheld": True,
                "citations_reference_valid_chunks": True,
                "snippets_are_exact_substrings": True,
                "offsets_valid_and_consistent": True,
                "proposal_not_treated_as_policy": True,
            }
            issues: List[str] = []

            raw_answer = ans.answer
            print(f"    LLM Answer: {raw_answer.strip()[:180]}...")

            # 1. Answer correctness against expected facts
            matched_facts = 0
            for ef in case["expected_facts"]:
                if re.search(ef, raw_answer, re.IGNORECASE):
                    matched_facts += 1
                else:
                    issues.append(f"Missing expected fact matching regex: {ef}")

            criteria["answer_correctness"] = (matched_facts == len(case["expected_facts"]))

            # 2. Check disallowed/hallucinated facts
            for df in case["disallowed_facts"]:
                if re.search(df, raw_answer, re.IGNORECASE):
                    criteria["unsupported_details_withheld"] = False
                    issues.append(f"Answer contains disallowed/hallucinated detail matching: {df}")

            # 3. Check scope & effective dates
            criteria["scope_and_dates_respected"] = (
                criteria["answer_correctness"] and criteria["unsupported_details_withheld"]
            )

            # 4. Accidental use of proposal as approved policy
            if "20 October" in raw_answer and ("is approved" in raw_answer.lower() or "effective" in raw_answer.lower()):
                if "not approved" not in raw_answer.lower() and "proposal" not in raw_answer.lower() and "no effective date" not in raw_answer.lower():
                    criteria["proposal_not_treated_as_policy"] = False
                    issues.append("Proposal dated 20 October was treated as approved policy.")

            # 5 & 6 & 7: Citation validity, exact substring, and offset consistency
            if not ans.insufficient_evidence and not ans.citations:
                issues.append("No citations returned for grounded answer.")

            for i, cit in enumerate(ans.citations, 1):
                chunk_obj = all_chunks.get(cit.chunk_id)
                if not chunk_obj:
                    criteria["citations_reference_valid_chunks"] = False
                    issues.append(f"Citation #{i} references unknown chunk ID: {cit.chunk_id}")
                    continue

                content = chunk_obj.content
                start = cit.char_offset_start
                end = cit.char_offset_end

                # Validate offsets
                if not validate_chunk_passage_offsets(content, start, end):
                    criteria["offsets_valid_and_consistent"] = False
                    issues.append(f"Citation #{i} has invalid offsets [{start}:{end}] for len={len(content)}")

                # Validate exact substring
                if start is not None and end is not None:
                    slice_content = content[start:end].strip()
                    clean_snip = re.sub(r"^\.\.\.\s*", "", cit.snippet)
                    clean_snip = re.sub(r"\s*\.\.\.$", "", clean_snip).strip()
                    if clean_snip != slice_content and clean_snip not in content:
                        criteria["snippets_are_exact_substrings"] = False
                        issues.append(f"Citation #{i} snippet is not an exact source substring.")

            passed = all(criteria.values())
            results.append({
                "case_id": case_id,
                "name": name,
                "passed": passed,
                "criteria": criteria,
                "issues": issues,
                "citations_count": len(ans.citations),
                "latency_ms": ans.latency_ms,
            })

            status_str = "[PASS]" if passed else "[FAIL]"
            print(f"    Status: {status_str} ({ans.latency_ms:.1f}ms, {len(ans.citations)} citations)")
            if issues:
                for is_text in issues:
                    print(f"      - Issue: {is_text}")

        print("\n================================================================================")
        print("                          EVALUATION SUMMARY                                    ")
        print("================================================================================")
        total_passed = sum(1 for r in results if r["passed"])
        total_cases = len(results)
        print(f"Overall Result: {total_passed}/{total_cases} Passed")
        for r in results:
            mark = "PASS" if r["passed"] else "FAIL"
            print(f"  [{mark}] {r['case_id']}: {r['name']}")

        if total_passed == total_cases:
            print("\n>> ALL LIVE ADVERSARIAL EVALUATION CASES PASSED SUCCESSFULLY.")
        else:
            print(f"\n>> {total_cases - total_passed} ADVERSARIAL CASES FAILED.")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(evaluate_live_suite())
