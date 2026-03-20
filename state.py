from __future__ import annotations

from typing import Any

import streamlit as st

import soulseek_client

RESULTS_KEY = "holding_pen_results"
DECISIONS_KEY = "holding_pen_decisions"
PLAYLIST_KEY = "holding_pen_playlist"
PLAYLIST_SIG_KEY = "holding_pen_playlist_sig"
PLAYLIST_SOURCE_SIG_KEY = "holding_pen_playlist_source_sig"
CURRENT_INDEX_KEY = "holding_pen_current_index"
FORMAT_PREFERENCE_KEY = "holding_pen_format_preference"
SLSKD_BASE_URL_KEY = "holding_pen_slskd_base_url"
SLSKD_USERNAME_KEY = "holding_pen_slskd_username"
SLSKD_PASSWORD_KEY = "holding_pen_slskd_password"
SEARCH_TIMEOUT_KEY = "holding_pen_search_timeout"
SEARCH_RETRY_COUNT_KEY = "holding_pen_search_retry_count"
DOWNLOAD_STATUS_CACHE_KEY = "holding_pen_download_status_cache"
DOWNLOAD_ATTEMPTS_KEY = "holding_pen_download_attempts"
AUTO_RETRY_ERRORED_KEY = "holding_pen_auto_retry_errored"

def reset_playlist_state(
    signature: str,
    tracks: list[dict[str, Any]],
    source_signature: str | None = None,
) -> None:
    st.session_state[PLAYLIST_SIG_KEY] = signature

    if source_signature is not None:
        st.session_state[PLAYLIST_SOURCE_SIG_KEY] = source_signature

    st.session_state[PLAYLIST_KEY] = tracks
    st.session_state[RESULTS_KEY] = {}
    st.session_state[DECISIONS_KEY] = {}
    st.session_state[CURRENT_INDEX_KEY] = 0

def ensure_playlist_state(
    signature: str,
    tracks: list[dict[str, Any]],
    source_signature: str | None = None,
) -> None:
    current_sig = st.session_state.get(PLAYLIST_SIG_KEY)
    if current_sig != signature:
        reset_playlist_state(signature, tracks, source_signature=source_signature)

    st.session_state.setdefault(RESULTS_KEY, {})
    st.session_state.setdefault(DECISIONS_KEY, {})
    st.session_state.setdefault(CURRENT_INDEX_KEY, 0)


def get_tracks() -> list[dict[str, Any]]:
    return st.session_state.get(PLAYLIST_KEY, [])


def get_results() -> dict[int, dict[str, Any]]:
    return st.session_state.get(RESULTS_KEY, {})


def get_decisions() -> dict[int, dict[str, Any]]:
    return st.session_state.get(DECISIONS_KEY, {})


def get_format_preference() -> str:
    return st.session_state.get(FORMAT_PREFERENCE_KEY, "cdj_safe")


def get_search_timeout() -> int:
    return int(st.session_state.get(SEARCH_TIMEOUT_KEY, 45))


def get_search_retry_count() -> int:
    return int(st.session_state.get(SEARCH_RETRY_COUNT_KEY, 1))


def get_download_attempts() -> dict[str, list[int]]:
    return st.session_state.setdefault(DOWNLOAD_ATTEMPTS_KEY, {})


def remember_download_attempt(track_index: int, candidate_index: int) -> None:
    attempts = get_download_attempts()
    key = str(track_index)
    attempts.setdefault(key, [])
    if candidate_index not in attempts[key]:
        attempts[key].append(candidate_index)
    st.session_state[DOWNLOAD_ATTEMPTS_KEY] = attempts


def get_attempted_candidate_indexes(track_index: int) -> list[int]:
    return get_download_attempts().get(str(track_index), [])


def get_download_status_cache() -> dict[str, dict[str, Any]]:
    return st.session_state.setdefault(DOWNLOAD_STATUS_CACHE_KEY, {})

def apply_soulseek_settings() -> None:
    soulseek_client.BASE_URL = st.session_state.get(SLSKD_BASE_URL_KEY, soulseek_client.BASE_URL)
    soulseek_client.UI_USERNAME = st.session_state.get(SLSKD_USERNAME_KEY, soulseek_client.UI_USERNAME)
    soulseek_client.UI_PASSWORD = st.session_state.get(SLSKD_PASSWORD_KEY, soulseek_client.UI_PASSWORD)
