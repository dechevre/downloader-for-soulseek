from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from typing import Any
import re
import requests
from bs4 import BeautifulSoup

import streamlit as st

from track_processor import process_track, spotify_track_from_dict


st.set_page_config(page_title="DJ Track Downloader Holding Pen", layout="wide")


RESULTS_KEY = "holding_pen_results"
DECISIONS_KEY = "holding_pen_decisions"
PLAYLIST_KEY = "holding_pen_playlist"
PLAYLIST_SIG_KEY = "holding_pen_playlist_sig"
CURRENT_INDEX_KEY = "holding_pen_current_index"


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


def parse_pasted_playlist_text(text: str) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        track = parse_pasted_track_line(line)
        if track:
            tracks.append(track)

    return tracks


def parse_pasted_track_line(line: str) -> dict[str, Any] | None:
    year = None
    working = line.strip()

    year_match = re.match(r"^(.*)\s-\s(19|20)\d{2}$", working)
    if year_match:
        year = working.rsplit(" - ", 1)[1]
        working = working.rsplit(" - ", 1)[0]

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

        tracks: list[dict[str, Any]] = []
        progress = st.progress(0.0)
        status = st.empty()

        for i, track_id in enumerate(track_ids, start=1):
            status.write(f"Fetching Spotify metadata {i}/{len(track_ids)}: {track_id}")
            track_info = fetch_track_data(track_id)
            if track_info:
                tracks.append(track_info)
            progress.progress(i / len(track_ids))

        status.write(f"Loaded {len(tracks)} tracks from TXT playlist.")
        return tracks

    raise ValueError("Unsupported file type. Please upload a .json or .txt file.")

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
        if result.get("status") == "found":
            return "searched"
        return "no hits"

    return "pending"


def status_emoji(status: str) -> str:
    mapping = {
        "selected": "✅",
        "skipped": "⏭️",
        "marked not found": "🚫",
        "searched": "🔎",
        "no hits": "❓",
        "pending": "⚪",
    }
    return mapping.get(status, "⚪")


def process_track_for_index(index: int, force_refresh: bool = False) -> None:
    results = get_results()
    if index in results and not force_refresh:
        return

    raw_track = get_tracks()[index]
    track = track_from_raw(raw_track)

    with st.spinner(f'Searching Soulseek for "{track.display_name}"...'):
        try:
            result = process_track(track)
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
        return

    query_info = result.get("queries") or {}
    counts = result.get("counts") or {}

    with st.expander("Search details", expanded=True):
        st.write(f"**Exact query:** {query_info.get('exact') or '—'}")
        st.write(f"**Fallback query:** {query_info.get('fallback') or '—'}")
        st.write(f"**Used fallback:** {query_info.get('used_fallback')}")
        st.write(f"**Exact candidates:** {counts.get('exact_candidates')}")
        st.write(f"**Fallback candidates:** {counts.get('fallback_candidates')}")
        st.write(f"**Returned ranked candidates:** {counts.get('ranked_candidates_returned')}")

    candidates = result.get("ranked_candidates", [])

    if not candidates:
        st.warning("No candidates found for this track.")
        return

    current_decision = decision_for_index(index)
    selected_candidate_index = None
    if current_decision and current_decision.get("decision") == "selected":
        selected_candidate_index = current_decision.get("candidate_index")

    st.markdown("### Ranked candidates")

    for candidate_index, candidate in enumerate(candidates):
        selected_badge = " ✅ selected" if selected_candidate_index == candidate_index else ""
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

            subcols = st.columns([1, 2, 2])
            with subcols[0]:
                if st.button(
                    "Select this file",
                    key=f"select_{index}_{candidate_index}",
                    use_container_width=True,
                ):
                    save_selected_candidate(index, candidate_index)
                    st.rerun()
            with subcols[1]:
                st.write("**Reasons**")
                reasons = candidate.get("reasons") or []
                if reasons:
                    for reason in reasons[:6]:
                        st.write(f"- {reason}")
                else:
                    st.write("- —")
            with subcols[2]:
                st.write("**Warnings**")
                warnings = candidate.get("warnings") or []
                if warnings:
                    for warning in warnings[:6]:
                        st.write(f"- {warning}")
                else:
                    st.write("- —")


def main() -> None:
    st.title("DJ Track Downloader — Holding Pen")
    st.write("Paste a track list or upload a playlist file, then search Soulseek one track at a time and save a preferred file per track.")

    input_mode = st.selectbox(
        "Playlist input mode",
        [
            "Paste track list",
            "Upload Spotify links TXT",
            "Upload cleaned JSON",
        ],
    )

    pasted_playlist_text = ""
    uploaded_file = None

    if input_mode == "Paste track list":
        pasted_playlist_text = st.text_area(
            "Paste playlist text",
            height=180,
            placeholder=(
                "Sacred Spirit, Dreadzone - Ya-Na-Hana (Celebrate Wild Rice) - Remix - 2011\n"
                "Sacred Spirit, Mark Brydon - Heya-Hee (Intertribal Song To Stop The Rain) - Dubbery - 2011"
            ),
            help="Paste one track per line as 'Artist - Title' or 'Artist - Title - Year'.",
        )
    elif input_mode == "Upload Spotify links TXT":
        uploaded_file = st.file_uploader(
            "Upload Spotify links TXT",
            type=["txt"],
            help="Upload a TXT file containing Spotify track links.",
            key="playlist_txt_uploader",
        )
    else:
        uploaded_file = st.file_uploader(
            "Upload cleaned playlist JSON",
            type=["json"],
            help="Use the JSON output from process_playlist_noapi.py or a compatible track list.",
            key="playlist_json_uploader",
        )

    parsed = None
    signature_source = None

    if input_mode == "Paste track list":
        if not pasted_playlist_text.strip():
            st.info("Paste a track list to begin.")
            return

        try:
            parsed = parse_pasted_playlist_text(pasted_playlist_text)
            if not parsed:
                st.error("No valid tracks could be parsed from pasted text.")
                return
            signature_source = pasted_playlist_text.encode("utf-8")
        except Exception as exc:
            st.error(f"Could not parse pasted playlist text: {exc}")
            return

    else:
        if not uploaded_file:
            st.info("Upload a playlist file to begin.")
            return

        try:
            parsed = load_tracks_from_uploaded_file(uploaded_file)
            signature_source = uploaded_file.getvalue()
        except Exception as exc:
            st.error(f"Could not load playlist file: {exc}")
            return

    signature = playlist_signature(signature_source)
    ensure_playlist_state(signature, parsed)
    tracks = get_tracks()

    if not tracks:
        st.warning("The uploaded playlist is empty.")
        return

    render_sidebar(tracks)

    index = st.session_state.get(CURRENT_INDEX_KEY, 0)
    raw_track = tracks[index]

    render_track_header(index, raw_track)
    render_track_controls(index)
    render_result_block(index)


if __name__ == "__main__":
    main()
