from __future__ import annotations

from typing import Any

import streamlit as st

import soulseek_client
from candidate_utils import SUSPICIOUS_EXTENSIONS
from decision_logic import save_selected_candidate
from state import (
    DOWNLOAD_STATUS_CACHE_KEY,
    apply_soulseek_settings,
    get_attempted_candidate_indexes,
    get_decisions,
    get_download_status_cache,
    remember_download_attempt,
)
from track_search import result_for_index


def enqueue_track_with_fallback(
    track_index: int,
    starting_candidate_index: int,
) -> tuple[int | None, str | None]:
    result = result_for_index(track_index)
    if not result:
        return None, "No result available for track"

    candidates = result.get("ranked_candidates", [])
    attempted = set(get_attempted_candidate_indexes(track_index))
    first_error: str | None = None

    for candidate_index in range(starting_candidate_index, len(candidates)):
        if candidate_index in attempted:
            continue

        candidate = candidates[candidate_index]
        ext = str(candidate.get("extension") or "").lower()
        if ext in SUSPICIOUS_EXTENSIONS:
            continue

        error = enqueue_candidate_for_track(track_index, candidate_index)
        if error is None:
            return candidate_index, None

        if first_error is None:
            first_error = error

    return None, first_error or "No untried candidates available"

def candidate_key(username: str | None, filename: str | None) -> str:
    return f"{username or ''}||{filename or ''}"


def extract_download_entries(downloads_raw: Any) -> list[dict[str, Any]]:
    if isinstance(downloads_raw, dict):
        if isinstance(downloads_raw.get("downloads"), list):
            items = downloads_raw["downloads"]
        elif isinstance(downloads_raw.get("items"), list):
            items = downloads_raw["items"]
        else:
            items = [downloads_raw]
    elif isinstance(downloads_raw, list):
        items = downloads_raw
    else:
        items = []

    entries: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        if isinstance(item.get("files"), list):
            group_user = item.get("username") or item.get("user")
            for file_entry in item["files"]:
                if isinstance(file_entry, dict):
                    merged = dict(file_entry)
                    if group_user and not merged.get("username"):
                        merged["username"] = group_user
                    entries.append(merged)
        else:
            entries.append(item)

    return entries


def extract_download_state(entry: dict[str, Any]) -> str:
    state = entry.get("state") or entry.get("status")
    if isinstance(state, dict):
        parts = [str(state.get(part)) for part in ("local", "remote") if state.get(part)]
        if parts:
            return ", ".join(parts)
    elif state:
        return str(state)

    local_state = entry.get("localState") or entry.get("local")
    remote_state = entry.get("remoteState") or entry.get("remote")
    parts = [str(part) for part in (local_state, remote_state) if part]
    if parts:
        return ", ".join(parts)

    return "Unknown"


def extract_download_error(entry: dict[str, Any]) -> str | None:
    for key in ("errorMessage", "error", "message", "failureReason", "reason"):
        value = entry.get(key)
        if value:
            return str(value)
    return None


def get_candidate_download_status(candidate: dict[str, Any]) -> dict[str, Any] | None:
    return get_download_status_cache().get(
        candidate_key(candidate.get("username"), candidate.get("filename"))
    )


def refresh_download_status_cache() -> tuple[int, list[str]]:
    apply_soulseek_settings()

    try:
        downloads_raw = soulseek_client.get_downloads()
    except Exception as exc:
        return 0, [str(exc)]

    entries = extract_download_entries(downloads_raw)
    cache: dict[str, dict[str, Any]] = {}

    for entry in entries:
        username = entry.get("username") or entry.get("user")
        filename = entry.get("filename") or entry.get("name") or entry.get("path")
        if not username or not filename:
            continue

        cache[candidate_key(username, filename)] = {
            "state": extract_download_state(entry),
            "error": extract_download_error(entry),
            "raw": entry,
        }

    st.session_state[DOWNLOAD_STATUS_CACHE_KEY] = cache
    return len(cache), []


def enqueue_candidate_for_track(track_index: int, candidate_index: int) -> str | None:
    result = result_for_index(track_index)
    if not result:
        return "No result available for track"

    candidates = result.get("ranked_candidates", [])
    if candidate_index >= len(candidates):
        return "Candidate index out of range"

    candidate = candidates[candidate_index]
    username = candidate.get("username")
    filename = candidate.get("filename")
    size = candidate.get("size")

    if not username or not filename:
        return "Missing username or filename"

    try:
        apply_soulseek_settings()
        soulseek_client.enqueue_download(username=username, filename=filename, size=size)
        remember_download_attempt(track_index, candidate_index)
        save_selected_candidate(track_index, candidate_index)
        return None
    except Exception as exc:
        remember_download_attempt(track_index, candidate_index)
        return str(exc)


def enqueue_selected_downloads() -> tuple[int, list[str]]:
    decisions = get_decisions()
    enqueued = 0
    errors: list[str] = []

    for track_index, decision in decisions.items():
        if decision.get("decision") != "selected":
            continue

        candidate_index = decision.get("candidate_index")
        if candidate_index is None:
            continue

        chosen_index, error = enqueue_track_with_fallback(
            int(track_index),
            int(candidate_index),
        )

        if error is None:
            enqueued += 1
        else:
            candidate = decision.get("candidate", {})
            errors.append(
                f"{candidate.get('username')} :: {candidate.get('filename')} :: {error}"
            )

    return enqueued, errors


def retry_errored_tracks_with_next_candidate() -> tuple[int, list[str]]:
    retried = 0
    errors: list[str] = []

    for track_index, decision in get_decisions().items():
        if decision.get("decision") != "selected":
            continue

        current_candidate = decision.get("candidate")
        if not current_candidate:
            continue

        status = get_candidate_download_status(current_candidate)
        if not status:
            continue

        state_text = str(status.get("state") or "").lower()
        error_text = str(status.get("error") or "")
        if "errored" not in state_text and not error_text:
            continue

        result = result_for_index(int(track_index))
        if not result:
            continue

        candidates = result.get("ranked_candidates", [])
        attempted = set(get_attempted_candidate_indexes(int(track_index)))
        current_index = int(decision.get("candidate_index", -1))

        retry_error: str | None = None
        retried_this_track = False

        for next_index in range(current_index + 1, len(candidates)):
            if next_index in attempted:
                continue

            candidate = candidates[next_index]
            ext = str(candidate.get("extension") or "").lower()
            if ext in SUSPICIOUS_EXTENSIONS:
                continue

            retry_error = enqueue_candidate_for_track(int(track_index), next_index)
            if retry_error is None:
                retried += 1
                retried_this_track = True
                break

        if not retried_this_track:
            if retry_error:
                errors.append(f"Track {int(track_index) + 1}: {retry_error}")
            else:
                errors.append(
                    f"Track {int(track_index) + 1}: no untried alternative candidates available after errored download"
                )

    return retried, errors

