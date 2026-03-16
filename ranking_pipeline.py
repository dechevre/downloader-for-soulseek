from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable
import math
import re

from soulseek_client import search_soulseek


# Models

@dataclass
class SpotifyTrack:
    artist: str
    title: str
    duration: int | None = None
    year: int | None = None

    @property
    def display_name(self) -> str:
        if self.year:
            return f"{self.artist} - {self.title} ({self.year})"
        return f"{self.artist} - {self.title}"
        
@dataclass
class SearchCandidate:
    filename: str
    username: str
    size: int | None = None
    bitrate: int | None = None
    length: int | None = None
    extension: str | None = None
    source_query: str | None = None
    raw: dict[str, Any] = field(default_factory=dict) # default factory so new dict for each instance
    
@dataclass
class RankedCandidate(SearchCandidate):
    score: int = 0
    subscores: dict[str, int] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Configure

FORMAT_SCORES = {
    "wav": 40,
    "aiff": 38,
    "aif": 38,
    "mp3": 30,
    "flac": 24,
    "m4a": 10,
    "aac": 8,
    "ogg": 5,
    "opus": 5,
    "wma": 0,
}

MP3_BITRATE_BONUS = {
    320: 22,
    256: 14,
    224: 8,
    192: 2,
    160: -4,
    128: -10,
}

# Terms that usually meaning is not the  original track
# accepted
EXPECTED_VARIANT_TERMS = {
    "remix",
    "mix",
    "edit",
    "radio",
    "live",
    "karaoke",
    "instrumental",
    "cover",
    "tribute",
    "bootleg",
    "mashup",
    "vs",
    "rework",
    "acapella",
    "version",
    "dub",
    "dubbery",
    "club",
    "extended",
    "original",
}
# & these penalised, so mix, edit, dub, version recognised but not immediately penalised
GENERIC_PENALTY_VARIANT_TERMS = {
    "remix",
    "live",
    "karaoke",
    "instrumental",
    "cover",
    "tribute",
    "bootleg",
    "mashup",
    "vs",
    "rework",
    "acapella",
}

NEGATIVE_FILENAME_TERMS = {
    "youtube": -10,
    "yt": -6,
    "rip": -10,
    "karaoke": -18,
    "cover": -16,
    "tribute": -16,
    "live": -10,
    "radio edit": -8,
    "bootleg": -8,
    "mashup": -18,
    "vs": -14,
    "acapella": -8,
}

POSITIVE_FILENAME_TERMS = {
    "original mix": 10,
    "extended mix": 8,
    "club mix": 8,
    "album version": 5,
    "full": 2,
}

STOPWORDS = {
    "the", "a", "an", "and", "feat", "ft", "featuring", "vs", "dj", "radio"
}

JUNK_FILENAME_TERMS = {
    "www.": -5,
    ".com": -4,
    ".org": -4,
    ".net": -4,
    "djsoundtop": -4,
    "groovytunes": -4,
}


# Normalization helpers

def unique_keep_order(items):
    seen = set()
    out = []

    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)

    return out


def first_artist_name(artist_text):
    """
    For collaborations like:
    'Sacred Spirit, Dreadzone'
    return:
    'Sacred Spirit'
    """
    return artist_text.split(",")[0].strip()


def strip_parenthetical(text):
    """
    Remove (...) sections for broader fallback queries.
    """
    return normalize_spaces(re.sub(r"\([^)]*\)", " ", text))


def base_title_for_search(title):
    """
    Build a simpler core title for fallback searching.

    Example:
    'Hot Flush - Sabres Of Paradise Remix'
    -> 'Hot Flush'

    'Ya-Na-Hana (Celebrate Wild Rice) - Remix'
    -> 'Ya-Na-Hana'
    """
    title_no_parens = strip_parenthetical(title)
    core = title_no_parens.split(" - ")[0]
    return normalize_spaces(core)

def get_filename_basename(filename):
    """
    Return just the file name, without folder path.
    Works for both / and \\ separators.
    """
    return re.split(r"[\\/]", filename)[-1]


def contains_whole_phrase(text, phrase):
    """
    Match a word or multi-word phrase using word boundaries,
    so 'rip' does not match inside 'trip'.
    """
    text_norm = normalize_text(text)
    phrase_words = normalize_text(phrase).split()

    if not phrase_words:
        return False

    pattern = r"\b" + r"\s+".join(re.escape(word) for word in phrase_words) + r"\b"
    return re.search(pattern, text_norm) is not None


ARTIST_WEAK_TOKENS = {
    "from",
    "and",
    "with",
}


def artist_tokens_for_match(artist_text):
    """
    Tokenize artist names but remove weak connector words like 'from'.
    """
    return [
        token
        for token in tokenize(artist_text)
        if token not in ARTIST_WEAK_TOKENS and len(token) > 1
    ]

def safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def infer_extension(filename: str) -> str | None:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix or None


def strip_extension(filename: str) -> str:
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", filename)


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\b(feat\.?|ft\.?|featuring)\b", " feat ", text)
    text = re.sub(r"[\[\]\(\)\{\}_]+", " ", text)
    text = re.sub(r"[-–—/\\|]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return normalize_spaces(text)


def tokenize(text: str) -> list[str]:
    tokens = normalize_text(text).split()
    return [t for t in tokens if t and t not in STOPWORDS]


def normalize_filename_for_match(filename: str) -> str:
    base = strip_extension(filename)
    return normalize_text(base)


def contains_phrase(text: str, phrase: str) -> bool:
    return normalize_text(phrase) in normalize_text(text)


def expected_mp3_size_bytes(bitrate_kbps: int, duration_seconds: int) -> int:
    # Approximate audio payload size.
    # This ignores tags/metadata overhead, which is fine for heuristics.
    return int((bitrate_kbps * 1000 / 8) * duration_seconds)

def candidate_has_expected_variant(filename_norm, expected_variant_terms):
    for term in expected_variant_terms:
        if contains_whole_phrase(filename_norm, term):
            return True
    return False

def required_variant_terms_for_query(track):
    """
    Return only the variant terms that are important enough
    to preserve in fallback search queries.
    """
    expected = extract_expected_variant_terms(track)

    important = {
        "remix",
        "edit",
        "version",
        "dub",
        "dubbery",
        "live",
        "rework",
        "acapella",
        "bootleg",
    }

    return [term for term in expected if term in important]


# Flattening

def flatten_search_responses(
    responses_payload: list[dict[str, Any]] | dict[str, Any],
    source_query: str | None = None,
) -> list[SearchCandidate]:
    """
    flattener for slskd responses.

    files with fields like: 
    filename, bitRate, size, length
    """
    if isinstance(responses_payload, dict):
        if "responses" in responses_payload and isinstance(responses_payload["responses"], list):
            response_items = responses_payload["responses"]
        elif "results" in responses_payload and isinstance(responses_payload["results"], list):
            response_items = responses_payload["results"]
        else:
            response_items = [responses_payload]
    else:
        response_items = responses_payload

    flattened: list[SearchCandidate] = []

    for response in response_items:
        username = (
            response.get("username")
            or response.get("user")
            or response.get("name")
            or (response.get("peer") or {}).get("username")
        )

        files = response.get("files") or []

        # Some payloads may nest files elsewhere
        if not files and isinstance(response.get("result"), dict):
            files = response["result"].get("files") or []

        for file_obj in files:
            filename = file_obj.get("filename") or file_obj.get("name") or file_obj.get("path")
            if not filename:
                continue

            candidate = SearchCandidate(
                filename=filename,
                username=username or "unknown",
                size=safe_int(file_obj.get("size")),
                bitrate=safe_int(file_obj.get("bitRate") or file_obj.get("bitrate")),
                length=safe_int(file_obj.get("length") or file_obj.get("duration")),
                extension=infer_extension(filename),
                source_query=source_query,
                raw=file_obj,
            )
            flattened.append(candidate)

    return flattened


# Scoring helpers

def score_format(candidate: SearchCandidate) -> tuple[int, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []

    ext = (candidate.extension or "").lower()
    score = FORMAT_SCORES.get(ext, -5)

    if ext in {"wav", "aiff", "aif"}:
        reasons.append(f"{ext.upper()} is highly CDJ-friendly")
    elif ext == "flac":
        reasons.append("FLAC is lossless")
        warnings.append("Some CDJ setups may not support FLAC reliably")
    elif ext == "mp3":
        reasons.append("MP3 is widely compatible")

        if candidate.bitrate is not None:
            bonus = MP3_BITRATE_BONUS.get(candidate.bitrate, 0)
            score += bonus
            if candidate.bitrate >= 320:
                reasons.append("320kbps MP3 preferred")
            elif candidate.bitrate >= 256:
                reasons.append(f"{candidate.bitrate}kbps MP3 is acceptable")
            else:
                warnings.append(f"{candidate.bitrate}kbps MP3 is lower quality")
    else:
        warnings.append(f"Less preferred format: {ext or 'unknown'}")

    return score, reasons, warnings


def score_duration(track: SpotifyTrack, candidate: SearchCandidate) -> tuple[int, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []

    if track.duration is None or candidate.length is None:
        return -2, reasons, ["Missing duration for precise match checking"]

    delta = abs(track.duration - candidate.length)

    if delta == 0:
        return 33, ["Duration exactly matches Spotify"], warnings
    if delta <= 3:
        return 30, [f"Duration within {delta}s"], warnings
    if delta <= 10:
        return 20, [f"Duration close ({delta}s off)"], warnings
    if delta <= 20:
        return 8, [f"Duration somewhat close ({delta}s off)"], warnings
    if delta <= 35:
        return 0, reasons, [f"Duration is a bit off ({delta}s)"]
    return -20, reasons, [f"Duration mismatch ({delta}s)"]


def extract_expected_variant_terms(track: SpotifyTrack) -> set[str]:
    title_norm = normalize_text(track.title)
    expected: set[str] = set()

    for term in EXPECTED_VARIANT_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", title_norm):
            expected.add(term)

    # Two-word cases
    for phrase in ["radio edit", "original mix", "extended mix", "club mix", "album version"]:
        if contains_whole_phrase(title_norm, phrase):
            expected.update(phrase.split())

    return expected

def phrase_in_text(phrase, text):
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None

def score_filename(track: SpotifyTrack, candidate: SearchCandidate) -> tuple[int, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []

    filename_norm = normalize_filename_for_match(candidate.filename)
    filename_words = filename_norm.split()

    artist_tokens = artist_tokens_for_match(track.artist)
    title_tokens = tokenize(track.title)
    expected_variant_terms = extract_expected_variant_terms(track)

    score = 0

    # Artist/title token coverage
    artist_hits = sum(1 for token in artist_tokens if token in filename_words)
    if artist_hits:
        add = min(artist_hits * 4, 12)
        score += add
        reasons.append(f"Artist tokens matched ({artist_hits})")

    title_hits = sum(1 for token in title_tokens if token in filename_words)
    if title_hits:
        add = min(title_hits * 5, 20)
        score += add
        reasons.append(f"Title tokens matched ({title_hits})")

    # Strong phrase matches
    if contains_phrase(candidate.filename, track.artist):
        score += 6
        reasons.append("Artist phrase matched")

    if contains_phrase(candidate.filename, track.title):
        score += 12
        reasons.append("Title phrase matched")

    if contains_phrase(candidate.filename, f"{track.artist} {track.title}"):
        score += 8
        reasons.append("Artist + title strongly matched")

    # Positive phrases
    for phrase, bonus in POSITIVE_FILENAME_TERMS.items():
        if contains_whole_phrase(filename_norm, phrase):
            # Only reward "original mix" / etc. lightly unless the target expects a variant
            score += bonus
            reasons.append(f'Contains "{phrase}"')

    # Negative phrases, unless target explicitly expects them
    for phrase, penalty in NEGATIVE_FILENAME_TERMS.items():
        phrase_tokens = set(phrase.split())
        
        if contains_whole_phrase(filename_norm, phrase):
            if phrase_tokens & expected_variant_terms:
                reasons.append(f'Target appears to expect "{phrase}"')
            else:
                score += penalty
                warnings.append(f'Unexpected "{phrase}" in filename')

    filename_lower = candidate.filename.lower()
    for phrase, penalty in JUNK_FILENAME_TERMS.items():
        if phrase in filename_lower:
            score += penalty
            warnings.append(f'Contains filename junk "{phrase}"')

    # Generic unexpected variant terms
    for term in GENERIC_PENALTY_VARIANT_TERMS:
        if contains_whole_phrase(filename_norm, term):
            if term not in expected_variant_terms:
                # Prevent double-penalizing obvious phrases already handled above
                    score -= 3
                    warnings.append(f'Unexpected variant term "{term}"')

    # Penalise candidates that look like the plain/original version
    # when the target title clearly expects a variant.
    variant_required_terms = expected_variant_terms.intersection(
        {"remix", "edit", "version", "dub", "dubbery", "live", "bootleg", "rework", "acapella"}
    )

    if variant_required_terms:
        variant_list = ", ".join(sorted(variant_required_terms))

        if candidate_has_expected_variant(filename_norm, variant_required_terms):
            score += 12
            reasons.append(f"Contains expected variant term(s): {variant_list}")
        else:
            score -= 18
            warnings.append(f"Missing expected variant term(s): {variant_list}")

    return score, reasons, warnings


def score_size_plausibility(track: SpotifyTrack, candidate: SearchCandidate) -> tuple[int, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []

    ext = (candidate.extension or "").lower()
    if ext != "mp3":
        return 0, reasons, warnings

    if candidate.size is None or candidate.length is None or candidate.bitrate is None:
        return 0, reasons, ["Missing size/length/bitrate for fake-320 check"]

    expected = expected_mp3_size_bytes(candidate.bitrate, candidate.length)
    if expected <= 0:
        return 0, reasons, warnings

    ratio = candidate.size / expected

    # Very small for declared bitrate = suspicious
    if ratio < 0.70:
        return -18, reasons, [f"Suspiciously small for {candidate.bitrate}kbps ({ratio:.2f}x expected)"]
    if ratio < 0.85:
        return -8, reasons, [f"Slightly small for declared bitrate ({ratio:.2f}x expected)"]
    if ratio <= 1.20:
        return 6, [f"File size looks plausible ({ratio:.2f}x expected)"], warnings
    if ratio <= 1.50:
        return 2, ["File size is slightly larger than expected"], warnings

    return 0, reasons, ["Unusually large MP3; may include extra metadata or be oddly encoded"]


def score_candidate(track: SpotifyTrack, candidate: SearchCandidate) -> RankedCandidate:
    ranked = RankedCandidate(**asdict(candidate))

    total = 0
    subscores: dict[str, int] = {}
    reasons: list[str] = []
    warnings: list[str] = []

    format_score, r, w = score_format(candidate)
    subscores["format"] = format_score
    total += format_score
    reasons.extend(r)
    warnings.extend(w)

    duration_score, r, w = score_duration(track, candidate)
    subscores["duration"] = duration_score
    total += duration_score
    reasons.extend(r)
    warnings.extend(w)

    filename_score, r, w = score_filename(track, candidate)
    subscores["filename"] = filename_score
    total += filename_score
    reasons.extend(r)
    warnings.extend(w)

    size_score, r, w = score_size_plausibility(track, candidate)
    subscores["size_plausibility"] = size_score
    total += size_score
    reasons.extend(r)
    warnings.extend(w)

    # Small bonus if source query looked close to target
    if candidate.source_query:
        query_norm = normalize_text(candidate.source_query)
        target_norm = normalize_text(f"{track.artist} {track.title}")
        if query_norm == target_norm:
            subscores["query_match"] = 4
            total += 4
            reasons.append("Found via exact query variant")
        else:
            subscores["query_match"] = 0

    ranked.score = total
    ranked.subscores = subscores
    ranked.reasons = dedupe_strings(reasons)
    ranked.warnings = dedupe_strings(warnings)
    return ranked


def dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


# Dedupe + ranking

def candidate_fingerprint(candidate: SearchCandidate) -> tuple[Any, ...]:
    """
    Dedupe by: uploader, basename only (not full path), size, length. 
    """
    basename = get_filename_basename(candidate.filename)

    return (
        candidate.username.lower().strip(),
        normalize_filename_for_match(basename),
        candidate.size,
        candidate.length,
    )


def dedupe_ranked_candidates(candidates: list[RankedCandidate]) -> list[RankedCandidate]:
    best_by_fp: dict[tuple[Any, ...], RankedCandidate] = {}

    for candidate in candidates:
        fp = candidate_fingerprint(candidate)
        existing = best_by_fp.get(fp)
        if existing is None or candidate.score > existing.score:
            best_by_fp[fp] = candidate

    return list(best_by_fp.values())


def rank_candidates_for_track(
    track: SpotifyTrack,
    candidates: list[SearchCandidate],
    top_n: int | None = None,
) -> list[RankedCandidate]:
    ranked = [score_candidate(track, c) for c in candidates]
    ranked = dedupe_ranked_candidates(ranked)

    ranked.sort(
        key=lambda c: (
            c.score,
            c.bitrate or -1,
            c.size or -1,
        ),
        reverse=True,
    )

    if top_n is not None:
        return ranked[:top_n]
    return ranked


# Convenience helpers

def generate_search_queries(track: SpotifyTrack, exact_query: str | None = None) -> list[str]:
    """
    Return:
    - exact query
    - one simplified fallback query

    If the target title expects an important variant term
    like remix / edit / dub / version, keep that in the fallback.
    """
    artist_first = first_artist_name(track.artist)
    title_core = base_title_for_search(track.title)
    variant_terms = required_variant_terms_for_query(track)

    queries: list[str] = []

    exact = exact_query or exact_query_for_track(track)
    queries.append(exact)

    if variant_terms:
        fallback_query = "%s - %s - %s" % (
            artist_first,
            title_core,
            " ".join(variant_terms),
        )
    else:
        fallback_query = "%s - %s" % (artist_first, title_core)

    queries.append(fallback_query)

    return unique_keep_order(queries)

def exact_query_for_track(track: SpotifyTrack) -> str:
    """
    Build the default exact query from the full artist + full title.
    """
    return normalize_spaces(f"{track.artist} - {track.title}")


def summarize_ranked_candidate(candidate: RankedCandidate) -> str:
    bitrate = f"{candidate.bitrate}kbps" if candidate.bitrate else "?"
    length = f"{candidate.length}s" if candidate.length else "?"
    size_mb = f"{candidate.size / (1024 * 1024):.1f}MB" if candidate.size else "?"
    ext = (candidate.extension or "?").upper()
    return (
        f"[{candidate.score:>3}] {ext:<4} {bitrate:<8} {size_mb:<8} {length:<6} "
        f"{candidate.username:<18} {candidate.filename}"
    )

