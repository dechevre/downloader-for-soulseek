from __future__ import annotations

import csv
import hashlib
import inspect
import json
import re
from io import StringIO
from typing import Any

import requests
import streamlit as st
from bs4 import BeautifulSoup

import soulseek_client
from track_processor import process_track, spotify_track_from_dict


st.set_page_config(page_title="DJ Track Downloader Holding Pen", layout="wide")


RESULTS_KEY = "holding_pen_results"
DECISIONS_KEY = "holding_pen_decisions"
PLAYLIST_KEY = "holding_pen_playlist"
PLAYLIST_SIG_KEY = "holding_pen_playlist_sig"
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

SAFE_AUDIO_EXTENSIONS = {"mp3", "wav", "aiff", "aif", "flac"}
SUSPICIOUS_EXTENSIONS = {"exe", "bat", "cmd", "com", "scr", "js", "jar", "msi", "zip", "rar", "7z"}

FORMAT_PREFERENCE_OPTIONS = {
    "CDJ-safe (WAV/AIFF/MP3 320 first, FLAC lower)": "cdj_safe",
    "MP3 preferred (MP3 first, 320 > 256 > 224 > 192)": "mp3_preferred",
    "Lossless preferred (WAV/AIFF/FLAC first, MP3 320 next)": "lossless_preferred",
    "WAV/AIFF only (strictly WAV or AIFF)": "wav_aiff_only",
    "Best available (any format, quality-ranked; 320kbps above lower MP3s)": "best_available",
}


def playlist_signature(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def extract_track_ids(text: str) -> list[str]:
    ids: list[str] = []
    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if "/track/" in line:
            try:
                track_id = line.split("/track/")[1].split("?")[0]
                ids.append(track_id)
            except IndexError:
                pass

    return ids


def extract_playlist_id(text: str) -> str | None:
    text = text.strip()

    match = re.search(r"spotify\.com/playlist/([A-Za-z0-9]+)", text)
    if match:
        return match.group(1)

    match = re.search(r"spotify:playlist:([A-Za-z0-9]+)", text)
    if match:
        return match.group(1)

    return None


def fetch_track_data(track_id: str) -> dict[str, Any] | None:
    url = f"https://open.spotify.com/track/{track_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers, timeout=20)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", type="application/ld+json")
    if not script_tag or not script_tag.string:
        return None

    data = json.loads(script_tag.string)

    track_name = data.get("name", "")
    release_date = data.get("datePublished", "")
    year = release_date[:4] if release_date else ""
    description = data.get("description", "")

    artist = ""
    segments = [seg.strip() for seg in description.split("·")]
    if len(segments) >= 2:
        artist = segments[1]

    return {
        "spotify_id": track_id,
        "artist": artist,
        "title": track_name,
        "year": year,
    }


def fetch_playlist_track_ids_from_url(playlist_url: str) -> list[str]:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(playlist_url, headers=headers, timeout=20)
    response.raise_for_status()

    html = response.text
    track_ids = re.findall(r"open\.spotify\.com/track/([A-Za-z0-9]+)", html)
    if not track_ids:
        track_ids = re.findall(r"spotify:track:([A-Za-z0-9]+)", html)

    deduped: list[str] = []
    seen: set[str] = set()
    for track_id in track_ids:
        if track_id not in seen:
            seen.add(track_id)
            deduped.append(track_id)

    return deduped


def fetch_tracks_from_track_ids(track_ids: list[str], progress_label: str) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    progress = st.progress(0.0)
    status = st.empty()

    for i, track_id in enumerate(track_ids, start=1):
        status.write(f"{progress_label} {i}/{len(track_ids)}: {track_id}")
        track_info = fetch_track_data(track_id)
        if track_info:
            tracks.append(track_info)
        progress.progress(i / len(track_ids))

    status.write(f"Loaded {len(tracks)} tracks.")
    return tracks


def parse_pasted_track_line(line: str) -> dict[str, Any] | None:
    working = line.strip()
    if not working:
        return None

    year = None

    paren_match = re.match(r"^(.*?)\s*\((19|20)\d{2}\)\s*$", working)
    if paren_match:
        year = working[-5:-1]
        working = paren_match.group(1).strip()
    else:
        dash_match = re.match(r"^(.*)\s-\s((19|20)\d{2})$", working)
        if dash_match:
            year = dash_match.group(2)
            working = dash_match.group(1).strip()

    if " - " not in working:
        return None

    artist, title = working.split(" - ", 1)
    artist = artist.strip()
    title = title.strip()

    if not artist or not title:
        return None

    return {
        "spotify_id": None,
        "artist": artist,
        "title": title,
        "year": year,
    }


def parse_pasted_playlist_text(text: str) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []

    for line in text.splitlines():
        parsed = parse_pasted_track_line(line)
        if parsed:
            tracks.append(parsed)

    return tracks


def load_tracks_from_uploaded_file(uploaded_file) -> list[dict[str, Any]]:
    suffix = uploaded_file.name.lower().rsplit(".", 1)[-1]
    raw_bytes = uploaded_file.getvalue()

    if suffix == "json":
        parsed = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(parsed, list):
            raise ValueError("Expected the uploaded JSON to contain a list of tracks.")
        return parsed

    if suffix == "txt":
        text = raw_bytes.decode("utf-8")
        track_ids = extract_track_ids(text)
        if not track_ids:
            raise ValueError("No Spotify track links were found in the uploaded TXT file.")
        return fetch_tracks_from_track_ids(track_ids, "Fetching Spotify track metadata")

    raise ValueError("Unsupported file type. Please upload a .json or .txt file.")


def tracks_to_cleaned_txt(tracks: list[dict[str, Any]]) -> str:
    lines: list[str] = []

    for track in tracks:
        artist = str(track.get("artist") or "").strip()
        title = str(track.get("title") or "").strip()
        year = str(track.get("year") or "").strip()

        if not artist or not title:
            continue

        if year:
            lines.append(f"{artist} - {title} ({year})")
        else:
            lines.append(f"{artist} - {title}")

    return "\n".join(lines)


def reset_playlist_state(signature: str, tracks: list[dict[str, Any]]) -> None:
    st.session_state[PLAYLIST_SIG_KEY] = signature
    st.session_state[PLAYLIST_KEY] = tracks
    st.session_state[RESULTS_KEY] = {}
    st.session_state[DECISIONS_KEY] = {}
    st.session_state[CURRENT_INDEX_KEY] = 0


def ensure_playlist_state(signature: str, tracks: list[dict[str, Any]]) -> None:
    current_sig = st.session_state.get(PLAYLIST_SIG_KEY)
    if current_sig != signature:
        reset_playlist_state(signature, tracks)

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


def apply_soulseek_settings() -> None:
    soulseek_client.BASE_URL = st.session_state.get(SLSKD_BASE_URL_KEY, soulseek_client.BASE_URL)
    soulseek_client.UI_USERNAME = st.session_state.get(SLSKD_USERNAME_KEY, soulseek_client.UI_USERNAME)
    soulseek_client.UI_PASSWORD = st.session_state.get(SLSKD_PASSWORD_KEY, soulseek_client.UI_PASSWORD)


def candidate_safety_notes(candidate: dict[str, Any]) -> list[str]:
    notes: list[str] = []

    extension = str(candidate.get("extension") or "").lower()
    bitrate = candidate.get("bitrate")
    length = candidate.get("length")
    size_mb = candidate.get("size_mb")

    if extension in SAFE_AUDIO_EXTENSIONS:
        notes.append(f"Audio file: {extension.upper()}")
    elif extension in SUSPICIOUS_EXTENSIONS:
        notes.append(f"Warning: suspicious extension {extension.upper()}")
    else:
        notes.append(f"Unknown or less common extension: {extension.upper() or '?'}")

    if bitrate:
        notes.append(f"Bitrate: {bitrate}kbps")
    else:
        notes.append("Bitrate missing")

    if length:
        notes.append(f"Length: {length}s")
    else:
        notes.append("Length missing")

    if size_mb:
        notes.append(f"Size: {size_mb}MB")
    else:
        notes.append("Size missing")

    return notes


def get_selected_candidates() -> list[dict[str, Any]]:
    decisions = get_decisions()
    selected: list[dict[str, Any]] = []

    for decision in decisions.values():
        if decision.get("decision") == "selected" and decision.get("candidate"):
            selected.append(decision["candidate"])

    return selected


def candidate_key(username: str | None, filename: str | None) -> str:
    return f"{username or ''}||{filename or ''}"


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

        error = enqueue_candidate_for_track(int(track_index), int(candidate_index))
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


def track_from_raw(raw_track: dict[str, Any]):
    return spotify_track_from_dict(raw_track)


def display_name_for_raw_track(raw_track: dict[str, Any]) -> str:
    return track_from_raw(raw_track).display_name


def result_for_index(index: int) -> dict[str, Any] | None:
    return get_results().get(index)


def decision_for_index(index: int) -> dict[str, Any] | None:
    return get_decisions().get(index)


def status_for_index(index: int) -> str:
    decision = decision_for_index(index)
    result = result_for_index(index)

    if decision:
        decision_type = decision.get("decision")
        if decision_type == "selected":
            return "selected"
        if decision_type == "skip":
            return "skipped"
        if decision_type == "not_found":
            return "marked not found"

    if result:
        result_status = result.get("status")
        if result_status == "error":
            return "error"
        if result_status == "found":
            return "searched"
        if result_status == "not_found":
            return "no hits"
        return "searched"

    return "pending"


def status_emoji(status: str) -> str:
    mapping = {
        "selected": "✅",
        "skipped": "⏭️",
        "marked not found": "🚫",
        "searched": "🔎",
        "no hits": "❓",
        "error": "⚠️",
        "pending": "⚪",
    }
    return mapping.get(status, "⚪")


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


def save_selected_candidate(index: int, candidate_index: int) -> None:
    result = result_for_index(index)
    if not result:
        return

    candidates = result.get("ranked_candidates", [])
    if candidate_index >= len(candidates):
        return

    candidate = candidates[candidate_index]
    decisions = get_decisions()
    decisions[index] = {
        "decision": "selected",
        "candidate_index": candidate_index,
        "candidate": candidate,
    }
    st.session_state[DECISIONS_KEY] = decisions


def mark_track(index: int, decision_type: str) -> None:
    decisions = get_decisions()
    decisions[index] = {"decision": decision_type}
    st.session_state[DECISIONS_KEY] = decisions


def clear_decision(index: int) -> None:
    decisions = get_decisions()
    decisions.pop(index, None)
    st.session_state[DECISIONS_KEY] = decisions


def go_previous() -> None:
    if st.session_state[CURRENT_INDEX_KEY] > 0:
        st.session_state[CURRENT_INDEX_KEY] -= 1


def go_next() -> None:
    if st.session_state[CURRENT_INDEX_KEY] < len(get_tracks()) - 1:
        st.session_state[CURRENT_INDEX_KEY] += 1


def build_export_rows() -> list[dict[str, Any]]:
    tracks = get_tracks()
    results = get_results()
    decisions = get_decisions()
    rows: list[dict[str, Any]] = []

    for index, raw_track in enumerate(tracks):
        result = results.get(index, {})
        decision = decisions.get(index, {})
        candidate = decision.get("candidate", {}) if decision.get("decision") == "selected" else {}

        row = {
            "playlist_index": index,
            "spotify_id": raw_track.get("spotify_id"),
            "artist": raw_track.get("artist"),
            "title": raw_track.get("title"),
            "year": raw_track.get("year"),
            "decision": decision.get("decision", "unreviewed"),
            "search_status": result.get("status", "not_searched"),
            "exact_query": (result.get("queries") or {}).get("exact"),
            "fallback_query": (result.get("queries") or {}).get("fallback"),
            "used_fallback": (result.get("queries") or {}).get("used_fallback"),
            "candidate_index": decision.get("candidate_index"),
            "candidate_filename": candidate.get("filename"),
            "candidate_username": candidate.get("username"),
            "candidate_extension": candidate.get("extension"),
            "candidate_bitrate": candidate.get("bitrate"),
            "candidate_length": candidate.get("length"),
            "candidate_size": candidate.get("size"),
            "candidate_size_mb": candidate.get("size_mb"),
            "candidate_score": candidate.get("score"),
            "candidate_source_query": candidate.get("source_query"),
            "candidate_reasons": " | ".join(candidate.get("reasons", [])) if candidate else None,
            "candidate_warnings": " | ".join(candidate.get("warnings", [])) if candidate else None,
            "format_preference": result.get("format_preference"),
        }
        rows.append(row)

    return rows


def export_rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def render_sidebar(tracks: list[dict[str, Any]]) -> None:
    st.sidebar.title("Holding Pen")

    with st.sidebar.expander("Soulseek connection", expanded=False):
        st.text_input(
            "slskd base URL",
            key=SLSKD_BASE_URL_KEY,
            value=st.session_state.get(SLSKD_BASE_URL_KEY, soulseek_client.BASE_URL),
        )
        st.text_input(
            "slskd username",
            key=SLSKD_USERNAME_KEY,
            value=st.session_state.get(SLSKD_USERNAME_KEY, soulseek_client.UI_USERNAME),
        )
        st.text_input(
            "slskd password",
            key=SLSKD_PASSWORD_KEY,
            value=st.session_state.get(SLSKD_PASSWORD_KEY, soulseek_client.UI_PASSWORD),
            type="password",
        )
        st.number_input(
            "Search timeout (seconds)",
            min_value=10,
            max_value=180,
            step=5,
            key=SEARCH_TIMEOUT_KEY,
            value=st.session_state.get(SEARCH_TIMEOUT_KEY, 45),
        )
        st.number_input(
            "Retry on timeout",
            min_value=0,
            max_value=3,
            step=1,
            key=SEARCH_RETRY_COUNT_KEY,
            value=st.session_state.get(SEARCH_RETRY_COUNT_KEY, 1),
        )
        st.caption("Use your own slskd instance and timeout settings here.")

    total = len(tracks)
    decisions = get_decisions()
    results = get_results()
    selected_count = sum(1 for d in decisions.values() if d.get("decision") == "selected")
    skipped_count = sum(1 for d in decisions.values() if d.get("decision") == "skip")
    not_found_count = sum(1 for d in decisions.values() if d.get("decision") == "not_found")
    searched_count = len(results)

    st.sidebar.write(f"Tracks: **{total}**")
    st.sidebar.write(f"Searched: **{searched_count}**")
    st.sidebar.write(f"Selected: **{selected_count}**")
    st.sidebar.write(f"Skipped: **{skipped_count}**")
    st.sidebar.write(f"Marked not found: **{not_found_count}**")

    options = list(range(total))

    def format_option(idx: int) -> str:
        status = status_for_index(idx)
        return f"{status_emoji(status)} {idx + 1}. {display_name_for_raw_track(tracks[idx])} [{status}]"

    current_index = st.session_state.get(CURRENT_INDEX_KEY, 0)
    selected_index = st.sidebar.selectbox(
        "Choose track",
        options=options,
        index=current_index,
        format_func=format_option,
    )
    st.session_state[CURRENT_INDEX_KEY] = selected_index

    rows = build_export_rows()
    if rows:
        st.sidebar.download_button(
            "Download decisions JSON",
            data=json.dumps(rows, indent=2),
            file_name="holding_pen_selections.json",
            mime="application/json",
            use_container_width=True,
        )
        st.sidebar.download_button(
            "Download decisions CSV",
            data=export_rows_to_csv(rows),
            file_name="holding_pen_selections.csv",
            mime="text/csv",
            use_container_width=True,
        )

    selected_candidates = get_selected_candidates()
    if selected_candidates:
        st.sidebar.checkbox(
            "Auto-try next candidate when selected download errored",
            key=AUTO_RETRY_ERRORED_KEY,
            value=st.session_state.get(AUTO_RETRY_ERRORED_KEY, True),
        )

        if st.sidebar.button("Enqueue selected downloads", use_container_width=True):
            enqueued, errors = enqueue_selected_downloads()

            if enqueued:
                st.sidebar.success(f"Enqueued {enqueued} download(s).")

            if errors:
                st.sidebar.error("Some downloads failed to enqueue.")
                for error in errors[:10]:
                    st.sidebar.write(f"- {error}")

        if st.sidebar.button("Refresh downloads status", use_container_width=True):
            count, errors = refresh_download_status_cache()
            if count:
                st.sidebar.success(f"Tracked {count} download status entrie(s).")
            if errors:
                st.sidebar.error("Could not refresh downloads status.")
                for error in errors[:5]:
                    st.sidebar.write(f"- {error}")
            elif st.session_state.get(AUTO_RETRY_ERRORED_KEY, True):
                retried, retry_errors = retry_errored_tracks_with_next_candidate()
                if retried:
                    st.sidebar.info(f"Queued next alternative for {retried} errored track(s).")
                if retry_errors:
                    for error in retry_errors[:10]:
                        st.sidebar.write(f"- {error}")

        with st.sidebar.expander("Downloads status", expanded=False):
            cache = get_download_status_cache()
            if not cache:
                st.write("No download status loaded yet. Use 'Refresh downloads status'.")
            else:
                for track_index, decision in decisions.items():
                    if decision.get("decision") != "selected":
                        continue

                    candidate = decision.get("candidate")
                    if not candidate:
                        continue

                    track_name = display_name_for_raw_track(tracks[int(track_index)])
                    status = get_candidate_download_status(candidate)
                    if not status:
                        st.write(f"**{track_name}** — no transfer status yet")
                        continue

                    st.write(f"**{track_name}** — {status.get('state') or 'Unknown'}")
                    if status.get("error"):
                        st.caption(status.get("error"))


def render_track_header(index: int, raw_track: dict[str, Any]) -> None:
    track = track_from_raw(raw_track)
    status = status_for_index(index)

    st.subheader(f"Track {index + 1}: {track.display_name}")
    st.caption(f"Status: {status_emoji(status)} {status}")

    meta_cols = st.columns(4)
    with meta_cols[0]:
        st.metric("Artist", raw_track.get("artist") or "—")
    with meta_cols[1]:
        st.metric("Title", raw_track.get("title") or "—")
    with meta_cols[2]:
        st.metric("Year", raw_track.get("year") or "—")
    with meta_cols[3]:
        st.metric("Spotify ID", raw_track.get("spotify_id") or "—")


def render_track_controls(index: int) -> None:
    control_cols = st.columns(6)

    with control_cols[0]:
        if st.button("Search current track", use_container_width=True):
            process_track_for_index(index, force_refresh=False)
    with control_cols[1]:
        if st.button("Refresh search", use_container_width=True):
            process_track_for_index(index, force_refresh=True)
    with control_cols[2]:
        if st.button("Mark skip", use_container_width=True):
            mark_track(index, "skip")
    with control_cols[3]:
        if st.button("Mark not found", use_container_width=True):
            mark_track(index, "not_found")
    with control_cols[4]:
        if st.button("Clear decision", use_container_width=True):
            clear_decision(index)
    with control_cols[5]:
        if st.button("Auto-search all pending", use_container_width=True):
            auto_search_pending_tracks()

    nav_cols = st.columns(2)
    with nav_cols[0]:
        if st.button("← Previous track", use_container_width=True, disabled=index == 0):
            go_previous()
            st.rerun()
    with nav_cols[1]:
        if st.button("Next track →", use_container_width=True, disabled=index >= len(get_tracks()) - 1):
            go_next()
            st.rerun()


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


def render_result_block(index: int) -> None:
    result = result_for_index(index)

    if not result:
        st.info("This track has not been searched yet.")
        return

    if result.get("status") == "error":
        st.error(f"Search failed: {result.get('error')}")
        st.caption("This is different from 'no hits'. It usually means the search timed out or the connection failed.")
        return

    query_info = result.get("queries") or {}
    counts = result.get("counts") or {}

    with st.expander("Search details", expanded=False):
        st.write(f"**Exact query:** {query_info.get('exact') or '—'}")
        st.write(f"**Fallback query:** {query_info.get('fallback') or '—'}")
        st.write(f"**Used fallback:** {query_info.get('used_fallback')}")
        st.write(f"**Exact candidates:** {counts.get('exact_candidates')}")
        st.write(f"**Fallback candidates:** {counts.get('fallback_candidates')}")
        st.write(f"**Returned ranked candidates:** {counts.get('ranked_candidates_returned')}")
        st.write(f"**Format preference:** {result.get('format_preference')}")

    candidates = result.get("ranked_candidates", [])

    if not candidates:
        st.warning("No candidates found for this track.")
        return

    current_decision = decision_for_index(index)
    selected_candidate_index = None
    if current_decision and current_decision.get("decision") == "selected":
        selected_candidate_index = current_decision.get("candidate_index")

    top_candidate = candidates[0]
    top_selected = selected_candidate_index == 0
    top_ext = (top_candidate.get("extension") or "?").upper()
    top_bitrate = f"{top_candidate.get('bitrate')}kbps" if top_candidate.get("bitrate") else "?"
    top_size_mb = f"{top_candidate.get('size_mb')}MB" if top_candidate.get("size_mb") else "?"
    top_length = f"{top_candidate.get('length')}s" if top_candidate.get("length") else "?"
    top_selected_badge = " ✅ selected" if top_selected else ""

    st.markdown("### Suggested file")
    with st.container(border=True):
        st.markdown(
            f"**[{top_candidate.get('score', '?')}] {top_ext} · {top_bitrate} · {top_size_mb} · {top_length} · {top_candidate.get('username', 'unknown')}**{top_selected_badge}"
        )
        st.write(top_candidate.get("filename", ""))
        st.caption(f"Source query: {top_candidate.get('source_query') or '—'}")
        st.write("**File safety / download clarity**")
        for note in candidate_safety_notes(top_candidate):
            st.write(f"- {note}")

        top_cols = st.columns([1, 2, 2])
        with top_cols[0]:
            if st.button("Select suggested file", key=f"select_top_{index}", use_container_width=True):
                save_selected_candidate(index, 0)
                st.rerun()
        with top_cols[1]:
            st.write("**Reasons**")
            reasons = top_candidate.get("reasons") or []
            if reasons:
                for reason in reasons[:6]:
                    st.write(f"- {reason}")
            else:
                st.write("- —")
        with top_cols[2]:
            st.write("**Warnings**")
            warnings = top_candidate.get("warnings") or []
            if warnings:
                for warning in warnings[:6]:
                    st.write(f"- {warning}")
            else:
                st.write("- —")

    alternative_candidates = candidates[1:6]
    if alternative_candidates:
        with st.expander("Show other good versions", expanded=False):
            for offset, candidate in enumerate(alternative_candidates, start=1):
                selected_badge = " ✅ selected" if selected_candidate_index == offset else ""
                ext = (candidate.get("extension") or "?").upper()
                bitrate = f"{candidate.get('bitrate')}kbps" if candidate.get("bitrate") else "?"
                size_mb = f"{candidate.get('size_mb')}MB" if candidate.get("size_mb") else "?"
                length = f"{candidate.get('length')}s" if candidate.get("length") else "?"

                with st.container(border=True):
                    st.markdown(
                        f"**[{candidate.get('score', '?')}] {ext} · {bitrate} · {size_mb} · {length} · {candidate.get('username', 'unknown')}**{selected_badge}"
                    )
                    st.write(candidate.get("filename", ""))
                    st.caption(f"Source query: {candidate.get('source_query') or '—'}")
                    for note in candidate_safety_notes(candidate):
                        st.write(f"- {note}")

                    subcols = st.columns([1, 2, 2])
                    with subcols[0]:
                        if st.button(
                            "Select this version",
                            key=f"select_{index}_{offset}",
                            use_container_width=True,
                        ):
                            save_selected_candidate(index, offset)
                            st.rerun()
                    with subcols[1]:
                        st.write("**Reasons**")
                        reasons = candidate.get("reasons") or []
                        if reasons:
                            for reason in reasons[:5]:
                                st.write(f"- {reason}")
                        else:
                            st.write("- —")
                    with subcols[2]:
                        st.write("**Warnings**")
                        warnings = candidate.get("warnings") or []
                        if warnings:
                            for warning in warnings[:5]:
                                st.write(f"- {warning}")
                        else:
                            st.write("- —")


def main() -> None:
    st.title("DJ Track Downloader — Holding Pen")
    st.write("Load a Spotify playlist URL, paste newline-separated tracks, upload a TXT of Spotify track links, or upload a cleaned JSON file. The app will search all tracks and suggest one best file per song, with alternatives available on demand.")

    format_label = st.selectbox(
        "Preferred file format strategy",
        options=list(FORMAT_PREFERENCE_OPTIONS.keys()),
        index=0,
    )
    st.session_state[FORMAT_PREFERENCE_KEY] = FORMAT_PREFERENCE_OPTIONS[format_label]

    input_mode = st.selectbox(
        "Playlist source",
        [
            "Spotify playlist URL",
            "Paste track list",
            "Spotify links TXT",
            "Cleaned JSON",
        ],
        index=0,
    )

    parsed: list[dict[str, Any]] | None = None
    signature_source: bytes | None = None

    if input_mode == "Spotify playlist URL":
        playlist_url = st.text_input(
            "Paste Spotify playlist URL",
            placeholder="https://open.spotify.com/playlist/...",
        )

        if not playlist_url.strip():
            st.info("Paste a Spotify playlist URL to begin.")
            return

        playlist_id = extract_playlist_id(playlist_url)
        if not playlist_id:
            st.error("That does not look like a valid Spotify playlist URL.")
            return

        normalized_playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"

        try:
            track_ids = fetch_playlist_track_ids_from_url(normalized_playlist_url)
        except Exception as exc:
            st.error(f"Could not fetch playlist page: {exc}")
            return

        if not track_ids:
            st.error("No track IDs were found on the playlist page.")
            return

        parsed = fetch_tracks_from_track_ids(track_ids, "Fetching playlist track metadata")
        signature_source = normalized_playlist_url.encode("utf-8")

    elif input_mode == "Paste track list":
        pasted_tracks = st.text_area(
            "Paste tracks (one per line)",
            height=180,
            placeholder=(
                "Eev Frances - Bala Cynwyd (2025)\n"
                "Anchorsong - Expo (2016)\n"
                "Rockers Hifi - Push Push (G-Corp. Mix) (2003)"
            ),
            help="Paste one track per line as 'Artist - Title', 'Artist - Title (Year)', or 'Artist - Title - Year'.",
        )

        if not pasted_tracks.strip():
            st.info("Paste tracks to begin.")
            return

        parsed = parse_pasted_playlist_text(pasted_tracks)
        if not parsed:
            st.error("No valid tracks could be parsed from the pasted text.")
            return

        signature_source = pasted_tracks.encode("utf-8")

    elif input_mode == "Spotify links TXT":
        uploaded_file = st.file_uploader(
            "Upload Spotify links TXT",
            type=["txt"],
            help="Upload a TXT file containing Spotify track links.",
            key="playlist_txt_uploader",
        )

        if not uploaded_file:
            st.info("Upload a TXT file to begin.")
            return

        try:
            parsed = load_tracks_from_uploaded_file(uploaded_file)
        except Exception as exc:
            st.error(f"Could not load TXT file: {exc}")
            return

        signature_source = uploaded_file.getvalue()

    else:
        uploaded_file = st.file_uploader(
            "Upload cleaned playlist JSON",
            type=["json"],
            help="Use the JSON output from process_playlist_noapi.py or a compatible track list.",
            key="playlist_json_uploader",
        )

        if not uploaded_file:
            st.info("Upload a JSON file to begin.")
            return

        try:
            parsed = load_tracks_from_uploaded_file(uploaded_file)
        except Exception as exc:
            st.error(f"Could not load JSON file: {exc}")
            return

        signature_source = uploaded_file.getvalue()

    if not parsed:
        st.warning("No tracks were loaded.")
        return

    download_cols = st.columns(2)
    with download_cols[0]:
        st.download_button(
            "Download cleaned JSON",
            data=json.dumps(parsed, indent=2),
            file_name="playlist_cleaned.json",
            mime="application/json",
            use_container_width=True,
        )
    with download_cols[1]:
        st.download_button(
            "Download cleaned TXT",
            data=tracks_to_cleaned_txt(parsed),
            file_name="playlist_cleaned.txt",
            mime="text/plain",
            use_container_width=True,
        )

    signature = playlist_signature(signature_source + st.session_state[FORMAT_PREFERENCE_KEY].encode())
    ensure_playlist_state(signature, parsed)
    tracks = get_tracks()

    if not tracks:
        st.warning("The loaded playlist is empty.")
        return

    if not get_results():
        auto_search_pending_tracks()
        st.rerun()

    render_sidebar(tracks)

    index = st.session_state.get(CURRENT_INDEX_KEY, 0)
    raw_track = tracks[index]

    render_track_header(index, raw_track)
    render_track_controls(index)
    render_result_block(index)


if __name__ == "__main__":
    main()