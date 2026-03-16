from __future__ import annotations

from dataclasses import asdict
from typing import Any

from soulseek_client import search_soulseek
from ranking_pipeline import (
    SpotifyTrack,
    RankedCandidate,
    SearchCandidate,
    flatten_search_responses,
    generate_search_queries,
    rank_candidates_for_track,
)


def spotify_track_from_dict(data: dict[str, Any]) -> SpotifyTrack:
    year = data.get("year")
    duration = data.get("duration")

    try:
        year = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        year = None

    try:
        duration = int(duration) if duration not in (None, "") else None
    except (TypeError, ValueError):
        duration = None

    return SpotifyTrack(
        artist=data.get("artist", "").strip(),
        title=data.get("title", "").strip(),
        duration=duration,
        year=year,
    )


def ranked_candidate_to_dict(candidate: RankedCandidate) -> dict[str, Any]:
    data = asdict(candidate)
    data["size_mb"] = round(candidate.size / (1024 * 1024), 2) if candidate.size else None
    return data


def track_to_dict(track: SpotifyTrack) -> dict[str, Any]:
    data = asdict(track)
    data["display_name"] = track.display_name
    return data


def is_exact_search_weak(candidates: list[SearchCandidate], min_candidates: int = 3) -> bool:
    return len(candidates) < min_candidates


def search_with_retry(
    query: str,
    *,
    search_timeout: int,
    retry_on_timeout: int,
) -> list[dict[str, Any]]:
    attempts = retry_on_timeout + 1
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            return search_soulseek(query, timeout=search_timeout)
        except TimeoutError as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
        except Exception as exc:
            last_error = exc
            raise

    if last_error:
        raise last_error

    return []


def process_track(
    track: SpotifyTrack,
    exact_query: str | None = None,
    *,
    weak_exact_threshold: int = 3,
    top_n: int | None = 10,
    run_fallback: bool = True,
    search_timeout: int = 45,
    retry_on_timeout: int = 1,
    format_preference: str = "best_available",
) -> dict[str, Any]:
    search_queries = generate_search_queries(track, exact_query=exact_query)

    exact_query_used = search_queries[0]
    fallback_query_used = search_queries[1] if len(search_queries) > 1 else None

    exact_responses = search_with_retry(
        exact_query_used,
        search_timeout=search_timeout,
        retry_on_timeout=retry_on_timeout,
    )
    exact_candidates = flatten_search_responses(
        exact_responses,
        source_query=exact_query_used,
    )

    fallback_candidates: list[SearchCandidate] = []
    used_fallback = False

    if (
        run_fallback
        and fallback_query_used
        and fallback_query_used != exact_query_used
        and is_exact_search_weak(exact_candidates, min_candidates=weak_exact_threshold)
    ):
        used_fallback = True
        fallback_responses = search_with_retry(
            fallback_query_used,
            search_timeout=search_timeout,
            retry_on_timeout=retry_on_timeout,
        )
        fallback_candidates = flatten_search_responses(
            fallback_responses,
            source_query=fallback_query_used,
        )

    all_candidates = [*exact_candidates, *fallback_candidates]
    ranked_candidates = rank_candidates_for_track(
        track,
        all_candidates,
        top_n=top_n,
        format_preference=format_preference,
    )

    ranked_candidate_dicts = [ranked_candidate_to_dict(candidate) for candidate in ranked_candidates]

    return {
        "track": track_to_dict(track),
        "queries": {
            "exact": exact_query_used,
            "fallback": fallback_query_used,
            "used_fallback": used_fallback,
        },
        "counts": {
            "exact_candidates": len(exact_candidates),
            "fallback_candidates": len(fallback_candidates),
            "total_candidates_before_ranking": len(all_candidates),
            "ranked_candidates_returned": len(ranked_candidates),
            "weak_exact_threshold": weak_exact_threshold,
        },
        "format_preference": format_preference,
        "search_timeout": search_timeout,
        "retry_on_timeout": retry_on_timeout,
        "status": "found" if ranked_candidates else "not_found",
        "best_candidate": ranked_candidate_dicts[0] if ranked_candidate_dicts else None,
        "alternative_candidates": ranked_candidate_dicts[1:5],
        "ranked_candidates": ranked_candidate_dicts,
    }