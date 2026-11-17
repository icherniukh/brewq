"""Port of Ruby's DidYouMean::SpellChecker, which `brew search` uses for fuzzy hits.

The algorithm is adapted from Yuki Nishijima's DidYouMean (MIT). See NOTICE.

Homebrew adds spell-checker suggestions to substring name matches for both
formulae and casks. Reproducing the algorithm keeps brewq's result set a
superset of `brew search`. Membership matches Ruby; ordering is irrelevant
because brewq ranks results itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import ceil


def _normalize(text: str) -> str:
    return text.lower().replace("@", "")


def _jaro(s1: str, s2: str) -> float:
    if len(s1) > len(s2):
        s1, s2 = s2, s1
    len1, len2 = len(s1), len(s2)
    window = len2 // 2 - 1 if len2 > 3 else 0
    flags1 = [False] * len1
    flags2 = [False] * len2
    matches = 0
    for i, ch in enumerate(s1):
        lo = i - window if i >= window else 0
        for j in range(lo, min(i + window, len2 - 1) + 1):
            if not flags2[j] and s2[j] == ch:
                flags2[j] = flags1[i] = True
                matches += 1
                break
    if not matches:
        return 0.0
    transpositions = 0
    k = 0
    for i in range(len1):
        if flags1[i]:
            while not flags2[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1
    t = transpositions // 2
    return (matches / len1 + matches / len2 + (matches - t) / matches) / 3


def _jaro_winkler(s1: str, s2: str) -> float:
    jaro = _jaro(s1, s2)
    if jaro <= 0.7:
        return jaro
    prefix = 0
    for a, b in zip(s1, s2, strict=False):
        if a != b or prefix >= 4:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def _levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def correct(query: str, dictionary: Iterable[str]) -> list[str]:
    """Return DidYouMean-style corrections for `query` from `dictionary`."""
    normalized = _normalize(query)
    if not normalized:
        return []
    threshold = 0.834 if len(normalized) > 3 else 0.77
    lq = len(normalized)
    # Jaro-Winkler <= 0.6 * jaro + 0.4 once jaro exceeds 0.7, and jaro is bounded
    # by the number of matching characters. Skip words that provably fall short
    # before paying for the full computation (no false rejects).
    jaro_floor = (threshold - 0.4) / 0.6
    drop_matching = str.maketrans("", "", normalized)

    scored: list[tuple[float, str, str]] = []
    for word in dictionary:
        if word == query:
            continue
        norm_word = word.lower().replace("@", "")
        lw = len(norm_word)
        if lw == 0:
            continue
        # Characters of the word that also occur in the query bound the match count.
        bound = min(lw - len(norm_word.translate(drop_matching)), lq)
        if (bound / lq + bound / lw + 1) / 3 < jaro_floor:
            continue
        score = _jaro_winkler(norm_word, normalized)
        if score >= threshold:
            scored.append((score, word, norm_word))
    # Ruby sorts ascending then reverses; mirroring that keeps tie order identical.
    scored.sort(key=lambda item: item[0])
    scored.reverse()

    max_typos = ceil(len(normalized) * 0.25)
    corrections = [
        word for _, word, norm_word in scored
        if _levenshtein(norm_word, normalized) <= max_typos
    ]
    if corrections:
        return corrections
    for _, word, norm_word in scored:
        length = min(len(normalized), len(norm_word))
        if _levenshtein(norm_word, normalized) < length:
            return [word]
    return []


def suggestion(raw: str, choices: Iterable[str]) -> str:
    """Suggest exact spellings without accepting a correction implicitly."""
    matches = correct(raw, choices)
    return f" Did you mean {', '.join(repr(word) for word in matches)}?" if matches else ""
