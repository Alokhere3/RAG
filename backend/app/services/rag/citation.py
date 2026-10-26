"""Deterministic citation passage localization and snippet generation.

Conforms to Phase 0 and Phase 1 RAG citation requirements:
- Extracts exact, bounded verbatim excerpts from cited chunks.
- Prefers exact source phrases, dates, version numbers, and explicit labels (e.g. Supersedes, PILOT rule).
- Aligns citation previews to specific claim statements when answers contain multiple claims.
- Never fabricates, interpolates, or paraphrases source text.
- Preserves full backward-compatibility with existing CitationItem contract.
"""

import re
from typing import List, Optional, Set, Tuple

# Common English stop words excluded from keyword scoring
STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
    "we've", "were", "weren't", "what", "what's", "when", "when's", "where",
    "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with",
    "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've",
    "your", "yours", "yourself", "yourselves"
}


def tokenize(text: str) -> List[str]:
    """Extract lowercased alphanumeric word tokens."""
    return [w.lower() for w in re.findall(r"\w+", text) if len(w) >= 2]


def extract_keywords(text: str) -> Set[str]:
    """Extract non-stopword tokens from text."""
    tokens = tokenize(text)
    keywords = {t for t in tokens if t not in STOP_WORDS}
    return keywords if keywords else set(tokens)


def extract_claims_for_chunk(answer: str, chunk_index: int) -> List[str]:
    """Extract individual statements/lines from the answer that cite the given chunk index.

    Supports citations such as:
    - [Doc: "...", Chunk: 47]
    - [Doc: ..., Chunk: 0, Chunk: 47]
    - [Doc: KB.docx, Chunk: 38, 47]
    - [Doc: KB.docx, Chunk: 39, 1]
    - [Chunk: 47]
    - [Chunk 47]
    """
    if not answer:
        return []

    lines = answer.splitlines()
    claims: List[str] = []
    chunk_pattern = re.compile(
        rf"\[[^\]]*\bChunks?:?[^\]]*?(?<!\d){re.escape(str(chunk_index))}\b[^\]]*\]",
        re.IGNORECASE,
    )
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if chunk_pattern.search(stripped):
            clean_claim = re.sub(r"\[Doc:[^\]]*\]", "", stripped)
            clean_claim = re.sub(r"\[Chunks?:?[^\]]*\]", "", clean_claim, flags=re.IGNORECASE)
            clean_claim = clean_claim.strip(" -*#\t")
            if clean_claim:
                claims.append(clean_claim)
    return claims


def split_sentences_with_offsets(content: str) -> List[Tuple[str, int, int]]:
    """Split content into coherent sentence/segment spans preserving exact character offsets."""
    sentence_spans: List[Tuple[str, int, int]] = []
    lines = content.splitlines(keepends=True)
    offset = 0
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            offset += len(line)
            continue

        # Look for sentence terminators (.!?) followed by space and capital letter or end of line.
        # Avoid splitting on digits with dots (e.g. 1. 2. 10.1) or single letters.
        sub_pattern = re.compile(r"(?<!\b\d)(?<!\b[A-Za-z])[.!?]+(?:\s+(?=[A-Z0-9])|$)", re.UNICODE)
        last_sub_start = 0
        matches = list(sub_pattern.finditer(line))

        if not matches:
            start_in_line = line.find(stripped_line)
            sentence_spans.append((stripped_line, offset + start_in_line, offset + start_in_line + len(stripped_line)))
        else:
            for m in matches:
                sub_end = m.end()
                segment = line[last_sub_start:sub_end].strip()
                if segment:
                    start_in_line = line.find(segment, last_sub_start)
                    sentence_spans.append((segment, offset + start_in_line, offset + start_in_line + len(segment)))
                last_sub_start = sub_end

            if last_sub_start < len(line):
                segment = line[last_sub_start:].strip()
                if segment:
                    start_in_line = line.find(segment, last_sub_start)
                    sentence_spans.append((segment, offset + start_in_line, offset + start_in_line + len(segment)))

        offset += len(line)

    return sentence_spans


def find_claim_anchor(
    content: str,
    claim: str = "",
    query: str = "",
    answer: str = "",
) -> Optional[Tuple[int, int]]:
    """Find the best verbatim start and end offset in content matching claims, dates, versions, or labels."""
    content_lower = content.lower()

    # Pass 1: If claim is provided, search claim first for direct evidence alignment
    if claim:
        # 1a. Explicit structural labels in claim
        # Proposal / Proposed
        if re.search(r"\b(proposal|proposed)\b", claim, re.IGNORECASE):
            m = re.search(r"\b(?:proposal|proposed)\b\s*(?:dated[^\n:]*:|:)?", content, re.IGNORECASE)
            if m:
                start = m.start()
                return start, min(len(content), start + 80)

        # Pilot rule / Highlands pilot
        if re.search(r"\b(pilot\s+rule|pilot\s+retry|highlands(?:\s+field\s+services)?\s+pilot)\b", claim, re.IGNORECASE):
            m = re.search(r"\b(?:pilot\s+rule|pilot)\b", content, re.IGNORECASE)
            if m:
                start = m.start()
                return start, min(len(content), start + 80)

        # Explicit negative constraints: "does not specify"
        if re.search(r"\b(?:does\s+not\s+specify|not\s+specify)\b", claim, re.IGNORECASE):
            m = re.search(r"\b(?:does\s+not\s+specify|not\s+specify)\b", content, re.IGNORECASE)
            if m:
                start = m.start()
                prefix_sub = content[max(0, start - 60) : start]
                sent_m = re.search(r"(?:^|[.!?]\s+|\n+)([A-Z0-9][^\n.!?]*)$", prefix_sub)
                if sent_m:
                    start = max(0, start - 60) + sent_m.start(1)
                return start, min(len(content), start + 80)

        # Supersedes / Superseded
        if re.search(r"\b(supersedes|superseded|supersede)\b", claim, re.IGNORECASE):
            # Check for exact claim phrase first (e.g. "Version 1.4 supersedes" or "supersedes version 1.3")
            sub_m = re.search(r"\b(?:version\s+\d+(?:\.\d+)+\s+supersedes(?:\s+\d+(?:\.\d+)+)?|supersedes\s+version\s+\d+(?:\.\d+)+)\b", claim, re.IGNORECASE)
            if sub_m:
                phrase = sub_m.group(0).lower()
                idx = content_lower.find(phrase)
                if idx != -1:
                    prefix_sub = content[max(0, idx - 45) : idx]
                    label_m = re.search(r"([A-Z0-9][a-zA-Z0-9\s_.-]{1,25}(?:\|\s*|:\s*))(?:[^\n|:]*)$", prefix_sub)
                    if label_m:
                        return max(0, idx - 45) + label_m.start(1), idx + len(phrase)
                    return idx, idx + len(phrase)

            m = re.search(r"\b(?:supersedes|superseded|supersede)\b\s*(?:\|\s*)?", content, re.IGNORECASE)
            if m:
                start = m.start()
                return start, min(len(content), start + 80)

        # Effective date
        if re.search(r"\b(effective\s+date|effective)\b", claim, re.IGNORECASE):
            m = re.search(r"\b(?:effective\s+date|effective)\b\s*(?:\|\s*)?", content, re.IGNORECASE)
            if m:
                start = m.start()
                prefix_sub = content[max(0, start - 45) : start]
                label_m = re.search(
                    r"((?:Version\s+\d+(?:\.\d+)+|v\d+(?:\.\d+)+)\s*(?:\|\s*|:\s*))(?:[^\n|:]*)$",
                    prefix_sub,
                    re.IGNORECASE,
                )
                if label_m:
                    start = max(0, start - 45) + label_m.start(1)
                return start, min(len(content), start + 80)

        # 1b. Exact multi-word phrases from claim (preserving dots in numbers like 1.4)
        words = re.findall(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*", claim)
        for n in (6, 5, 4, 3):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i : i + n]).lower()
                if len(phrase) >= 12:
                    idx = content_lower.find(phrase)
                    if idx != -1:
                        prefix_sub = content[max(0, idx - 60) : idx]
                        label_m = re.search(r"([A-Z0-9][a-zA-Z0-9\s_.-]{1,35}(?:\|\s*|:\s*))(?:[^\n|:]*)$", prefix_sub)
                        if label_m:
                            label_start = max(0, idx - 60) + label_m.start(1)
                            return label_start, idx + len(phrase)
                        sent_m = re.search(r"(?:^|[.!?]\s+|\n+)([A-Z0-9][^\n.!?]*)$", prefix_sub)
                        if sent_m:
                            sent_start = max(0, idx - 60) + sent_m.start(1)
                            return sent_start, idx + len(phrase)
                        return idx, idx + len(phrase)

        # 1c. Exact dates in claim
        dates = re.findall(
            r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
            claim,
            re.IGNORECASE,
        )
        dates += re.findall(r"\b\d{4}-\d{2}-\d{2}\b", claim)
        for d in dates:
            idx = content_lower.find(d.lower())
            if idx != -1:
                prefix_sub = content[max(0, idx - 45) : idx]
                label_m = re.search(r"([A-Z0-9][a-zA-Z0-9\s_.-]{1,25}(?:\|\s*|:\s*))(?:[^\n|:]*)$", prefix_sub)
                if label_m:
                    label_start = max(0, idx - 45) + label_m.start(1)
                    return label_start, idx + len(d)
                return idx, idx + len(d)

        # 1d. Version strings in claim
        versions = re.findall(r"\b(?:[vV]ersion\s+\d+(?:\.\d+)+|v\d+(?:\.\d+)+)\b", claim)
        for v in versions:
            idx = content_lower.find(v.lower())
            if idx != -1:
                prefix_sub = content[max(0, idx - 45) : idx]
                label_m = re.search(r"([A-Z0-9][a-zA-Z0-9\s_.-]{1,25}(?:\|\s*|:\s*))(?:[^\n|:]*)$", prefix_sub)
                if label_m:
                    label_start = max(0, idx - 45) + label_m.start(1)
                    return label_start, idx + len(v)
                return idx, idx + len(v)

    # Pass 2: Fallback to query and answer for explicit domain labels and specific dates/versions
    search_texts = [t for t in (query, answer) if t]
    if not search_texts:
        return None

    # Check for Proposal
    if any(re.search(r"\b(proposal|proposed)\b", t, re.IGNORECASE) for t in search_texts):
        m = re.search(r"\b(?:proposal|proposed)\b\s*(?:dated[^\n:]*:|:)?", content, re.IGNORECASE)
        if m:
            start = m.start()
            return start, min(len(content), start + 80)

    # Check for Supersedes / Superseded
    if any(re.search(r"\b(supersedes|superseded|supersede)\b", t, re.IGNORECASE) for t in search_texts):
        m = re.search(r"\b(?:supersedes|superseded|supersede)\b\s*(?:\|\s*)?", content, re.IGNORECASE)
        if m:
            start = m.start()
            return start, min(len(content), start + 80)

    # Check for PILOT rule
    if any(re.search(r"\b(pilot\s+rule|pilot\s+retry|highlands(?:\s+field\s+services)?\s+pilot)\b", t, re.IGNORECASE) for t in search_texts):
        m = re.search(r"\b(?:pilot\s+rule|pilot)\b", content, re.IGNORECASE)
        if m:
            start = m.start()
            return start, min(len(content), start + 80)

    # Check for Effective date
    if any(re.search(r"\b(effective\s+date|effective)\b", t, re.IGNORECASE) for t in search_texts):
        m = re.search(r"\b(?:effective\s+date|effective)\b\s*(?:\|\s*)?", content, re.IGNORECASE)
        if m:
            start = m.start()
            prefix_sub = content[max(0, start - 45) : start]
            label_m = re.search(
                r"((?:Version\s+\d+(?:\.\d+)+|v\d+(?:\.\d+)+)\s*(?:\|\s*|:\s*))(?:[^\n|:]*)$",
                prefix_sub,
                re.IGNORECASE,
            )
            if label_m:
                start = max(0, start - 45) + label_m.start(1)
            return start, min(len(content), start + 80)

    # Check for exact dates in query or answer
    for text_source in search_texts:
        dates = re.findall(
            r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
            text_source,
            re.IGNORECASE,
        )
        dates += re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text_source)
        for d in dates:
            idx = content_lower.find(d.lower())
            if idx != -1:
                prefix_sub = content[max(0, idx - 45) : idx]
                label_m = re.search(r"([A-Z0-9][a-zA-Z0-9\s_.-]{1,25}(?:\|\s*|:\s*))(?:[^\n|:]*)$", prefix_sub)
                if label_m:
                    label_start = max(0, idx - 45) + label_m.start(1)
                    return label_start, idx + len(d)
                return idx, idx + len(d)

    # Check for explicit version strings in query or answer
    for text_source in search_texts:
        versions = re.findall(r"\b(?:[vV]ersion\s+\d+(?:\.\d+)+|v\d+(?:\.\d+)+)\b", text_source)
        for v in versions:
            idx = content_lower.find(v.lower())
            if idx != -1:
                prefix_sub = content[max(0, idx - 45) : idx]
                label_m = re.search(r"([A-Z0-9][a-zA-Z0-9\s_.-]{1,25}(?:\|\s*|:\s*))(?:[^\n|:]*)$", prefix_sub)
                if label_m:
                    label_start = max(0, idx - 45) + label_m.start(1)
                    return label_start, idx + len(v)
                return idx, idx + len(v)

    return None


def score_sentence(
    sentence_text: str,
    query_keywords: Set[str],
    answer_keywords: Set[str],
    claim_keywords: Set[str] = set(),
    query_raw: str = "",
) -> float:
    """Deterministically score a candidate sentence against claim, query, and answer signals."""
    if not sentence_text:
        return 0.0

    tokens = set(tokenize(sentence_text))
    s_lower = sentence_text.lower()
    score = 0.0

    # 1. Claim keyword matches (highest importance for claim alignment)
    for ck in claim_keywords:
        if ck in tokens:
            score += 4.0
        elif len(ck) >= 4 and any(t.startswith(ck[:4]) or ck.startswith(t[:4]) for t in tokens if len(t) >= 4):
            score += 2.0

    # 2. Query keyword matches (primary intent signal)
    for qk in query_keywords:
        if qk in tokens:
            score += 2.0
        elif len(qk) >= 4 and any(t.startswith(qk[:4]) or qk.startswith(t[:4]) for t in tokens if len(t) >= 4):
            score += 1.0

    # 3. Answer keyword matches (secondary confirmation)
    for ak in answer_keywords:
        if ak in tokens and ak not in query_keywords and ak not in claim_keywords:
            score += 0.5

    # 4. Exact multi-word query phrase matching bonus
    if query_raw:
        q_words = tokenize(query_raw)
        for n in (3, 2):
            for i in range(len(q_words) - n + 1):
                phrase = " ".join(q_words[i : i + n])
                if len(phrase) >= 8 and phrase in s_lower:
                    score += 5.0 * n

    return score


def extract_citation_snippet(
    content: str,
    query: str = "",
    answer: str = "",
    claim: str = "",
    max_chars: int = 240,
) -> Tuple[str, int, int]:
    """Deterministically extract the most relevant passage snippet and character offsets.

    Returns:
        (snippet_text, char_offset_start, char_offset_end)
    """
    if not content or not content.strip():
        return "", 0, 0

    clean_content = content.strip()
    # Fast path: if the entire chunk fits within preview budget, return it verbatim
    if len(clean_content) <= max_chars:
        start = content.find(clean_content)
        end = start + len(clean_content)
        return clean_content, start, end

    # Check for direct verbatim quotes in the LLM answer
    if answer:
        quote_matches = re.findall(r'["\u201c]([^\n"\u201d]{15,})["\u201d]', answer)
        for q in quote_matches:
            q_clean = q.strip()
            idx = content.find(q_clean)
            if idx != -1:
                end_idx = idx + len(q_clean)
                prefix = "... " if idx > 0 else ""
                suffix = " ..." if end_idx < len(content) else ""
                return f"{prefix}{q_clean}{suffix}", idx, end_idx

    # Step 1: Look for exact entity anchors (labels, dates, version numbers, claim phrases)
    anchor = find_claim_anchor(content, claim=claim, query=query, answer=answer)
    if anchor is not None:
        anchor_start, _ = anchor
        window_start = anchor_start
        window_end = min(len(content), window_start + max_chars)

        # Break cleanly on line boundary or word boundary
        if window_end < len(content):
            slice_text = content[window_start:window_end]
            newline_pos = slice_text.find("\n")
            if newline_pos > 30:
                window_end = window_start + newline_pos
            else:
                last_space = slice_text.rfind(" ")
                if last_space > max_chars // 2:
                    window_end = window_start + last_space

        extracted = content[window_start:window_end].strip()
        prefix = "... " if window_start > 0 else ""
        suffix = " ..." if window_end < len(content) else ""
        return f"{prefix}{extracted}{suffix}", window_start, window_end

    # Step 2: Sentence / segment scoring
    sentences = split_sentences_with_offsets(content)
    if not sentences:
        clipped = content[:max_chars].strip()
        end_idx = min(len(content), max_chars)
        return f"{clipped}...", 0, end_idx

    query_keywords = extract_keywords(query) if query else set()
    answer_keywords = extract_keywords(answer) if answer else set()
    claim_keywords = extract_keywords(claim) if claim else set()

    scored_sentences = [
        (score_sentence(s_text, query_keywords, answer_keywords, claim_keywords, query), s_text, start, end)
        for s_text, start, end in sentences
    ]

    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    best_score, best_text, best_start, best_end = scored_sentences[0]

    # If no sentence had any keyword overlap, fallback safely to chunk prefix
    if best_score <= 0.0:
        clipped = content[:max_chars].strip()
        end_idx = min(len(content), max_chars)
        return f"{clipped}...", 0, end_idx

    window_start = best_start
    window_end = best_end

    # If best sentence itself exceeds max_chars, truncate cleanly at word boundary
    if (window_end - window_start) > max_chars:
        slice_text = content[window_start : window_start + max_chars]
        last_space = slice_text.rfind(" ")
        if last_space > max_chars // 2:
            window_end = window_start + last_space
        else:
            window_end = window_start + max_chars
    else:
        # Expand window forward by subsequent sentences if space allows
        current_idx = next(i for i, s in enumerate(sentences) if s[1] == best_start)
        for i in range(current_idx + 1, len(sentences)):
            _, next_start, next_end = sentences[i]
            if (next_end - window_start) <= max_chars:
                window_end = next_end
            else:
                break

        # Only if best sentence is very short (< half of budget), expand backward
        if (window_end - window_start) < (max_chars // 2):
            for i in range(current_idx - 1, -1, -1):
                _, prev_start, _ = sentences[i]
                if (window_end - prev_start) <= max_chars:
                    window_start = prev_start
                else:
                    break

    extracted = content[window_start:window_end].strip()
    prefix = "... " if window_start > 0 else ""
    suffix = " ..." if window_end < len(content) else ""
    snippet = f"{prefix}{extracted}{suffix}"

    return snippet, window_start, window_end


def validate_chunk_passage_offsets(
    chunk_content: str,
    start: Optional[int],
    end: Optional[int],
) -> bool:
    """Validate that offsets strictly bound an actual substring within the chunk content."""
    if start is None and end is None:
        return True
    if start is None or end is None:
        return False
    if start < 0 or end < start or end > len(chunk_content):
        return False
    return True
