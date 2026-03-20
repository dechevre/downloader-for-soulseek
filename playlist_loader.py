from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

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

    for i, track_id in enumerate(track_ids, start=1):
        track_info = fetch_track_data(track_id)
        if track_info:
            tracks.append(track_info)

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