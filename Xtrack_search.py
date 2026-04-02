from __future__ import annotations

import inspect
from typing import Any

import streamlit as st

from state import (
    RESULTS_KEY,
    apply_soulseek_settings,
    get_format_preference,
    get_results,
    get_search_retry_count,
    get_search_timeout,
    get_tracks,
)
from track_processor import process_track, spotify_track_from_dict

def track_from_raw(raw_track: dict[str, Any]):
    return spotify_track_from_dict(raw_track)


def display_name_for_raw_track(raw_track: dict[str, Any]) -> str:
    return track_from_raw(raw_track).display_name


def result_for_index(index: int) -> dict[str, Any] | None:
    return get_results().get(index)


def process_track_for_index(index: int, force_refresh: bool = False) -> None:
    results = get_results()
    if index in results and not force_refresh:
        return

    raw_track = get_tracks()[index]
    track = track_from_raw(raw_track)
    format_preference = get_format_preference()
    search_timeout = get_search_timeout()
    retry_count = get_search_retry_count()

    apply_soulseek_settings()

    with st.spinner(f'Searching Soulseek for "{track.display_name}"...'):
        try:
            process_signature = inspect.signature(process_track)
            process_kwargs: dict[str, Any] = {}

            if "format_preference" in process_signature.parameters:
                process_kwargs["format_preference"] = format_preference
            if "search_timeout" in process_signature.parameters:
                process_kwargs["search_timeout"] = search_timeout
            if "retry_on_timeout" in process_signature.parameters:
                process_kwargs["retry_on_timeout"] = retry_count

            result = process_track(track, **process_kwargs)
        except Exception as exc:
            result = {
                "track": {
                    **raw_track,
                    "display_name": track.display_name,
                },
                "status": "error",
                "error": str(exc),
                "queries": {
                    "exact": None,
                    "fallback": None,
                    "used_fallback": False,
                },
                "counts": {
                    "exact_candidates": 0,
                    "fallback_candidates": 0,
                    "total_candidates_before_ranking": 0,
                    "ranked_candidates_returned": 0,
                    "weak_exact_threshold": None,
                },
                "ranked_candidates": [],
            }

    result["format_preference"] = format_preference
    result["search_timeout"] = search_timeout
    result["retry_on_timeout"] = retry_count
    results[index] = result
    st.session_state[RESULTS_KEY] = results


def auto_search_pending_tracks() -> None:
    tracks = get_tracks()
    results = get_results()

    pending_indexes = [idx for idx in range(len(tracks)) if idx not in results]
    if not pending_indexes:
        st.info("No pending tracks left to search.")
        return

    progress = st.progress(0.0)
    status_text = st.empty()

    for step, idx in enumerate(pending_indexes, start=1):
        track = track_from_raw(tracks[idx])
        status_text.write(f"Searching {step}/{len(pending_indexes)}: {track.display_name}")
        process_track_for_index(idx, force_refresh=False)
        progress.progress(step / len(pending_indexes))

    status_text.write("Finished searching pending tracks.")

