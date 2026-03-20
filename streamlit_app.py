from __future__ import annotations

import json
from typing import Any

import streamlit as st

import soulseek_client
from candidate_utils import candidate_safety_notes
from decision_logic import (
    clear_decision,
    decision_for_index,
    get_selected_candidates,
    mark_track,
    save_selected_candidate,
    status_for_index,
)
from download_manager import (
    enqueue_selected_downloads,
    get_candidate_download_status,
    refresh_download_status_cache,
    retry_errored_tracks_with_next_candidate,
)
from export_utils import build_export_rows, export_rows_to_csv
from playlist_loader import (
    extract_playlist_id,
    fetch_playlist_track_ids_from_url,
    fetch_tracks_from_track_ids,
    load_tracks_from_uploaded_file,
    parse_pasted_playlist_text,
    playlist_signature,
    tracks_to_cleaned_txt,
)
from state import (
    AUTO_RETRY_ERRORED_KEY,
    CURRENT_INDEX_KEY,
    FORMAT_PREFERENCE_KEY,
    PLAYLIST_SIG_KEY,
    PLAYLIST_SOURCE_SIG_KEY,
    SEARCH_RETRY_COUNT_KEY,
    SEARCH_TIMEOUT_KEY,
    SLSKD_BASE_URL_KEY,
    SLSKD_PASSWORD_KEY,
    SLSKD_USERNAME_KEY,
    ensure_playlist_state,
    get_decisions,
    get_download_status_cache,
    get_results,
    get_tracks,
)
from track_search import (
    auto_search_pending_tracks,
    display_name_for_raw_track,
    process_track_for_index,
    result_for_index,
    track_from_raw,
)

st.set_page_config(page_title="DJ Track Downloader Holding Pen", layout="wide")



FORMAT_PREFERENCE_OPTIONS = {
    "CDJ-safe (WAV/AIFF/MP3 320 first, FLAC lower)": "cdj_safe",
    "MP3 preferred (MP3 first, 320 > 256 > 224 > 192)": "mp3_preferred",
    "Lossless preferred (WAV/AIFF/FLAC first, MP3 320 next)": "lossless_preferred",
    "WAV/AIFF only (strictly WAV or AIFF)": "wav_aiff_only",
    "Best available (any format, quality-ranked; 320kbps above lower MP3s)": "best_available",
}




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


def go_previous() -> None:
    if st.session_state[CURRENT_INDEX_KEY] > 0:
        st.session_state[CURRENT_INDEX_KEY] -= 1


def go_next() -> None:
    if st.session_state[CURRENT_INDEX_KEY] < len(get_tracks()) - 1:
        st.session_state[CURRENT_INDEX_KEY] += 1


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
    signature: str | None = None

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
        signature_source = normalized_playlist_url.encode("utf-8")

        source_signature = playlist_signature(signature_source)
        full_signature = playlist_signature(
            signature_source + st.session_state[FORMAT_PREFERENCE_KEY].encode()
        )

        if st.session_state.get(PLAYLIST_SOURCE_SIG_KEY) == source_signature and get_tracks():
            parsed = get_tracks()
            signature = full_signature
        else:
            try:
                track_ids = fetch_playlist_track_ids_from_url(normalized_playlist_url)
            except Exception as exc:
                st.error(f"Could not fetch playlist page: {exc}")
                return

            if not track_ids:
                st.error("No track IDs were found on the playlist page.")
                return

            parsed = fetch_tracks_from_track_ids(
                track_ids,
                "Fetching playlist track metadata",
            )
            signature = full_signature

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

    if signature is None:
        signature = playlist_signature(
            signature_source + st.session_state[FORMAT_PREFERENCE_KEY].encode()
        )

    ensure_playlist_state(
        signature,
        parsed,
        source_signature=source_signature if input_mode == "Spotify playlist URL" else None,
    )
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