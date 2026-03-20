
from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from state import get_decisions, get_results, get_tracks

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

