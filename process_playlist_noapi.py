# python process_playlist_noapi.py playlists/smoothin_020326.txt
# python process_playlist_noapi.py playlists/test.txt

import sys
import os
import time
import re
import requests
import json
from bs4 import BeautifulSoup
import json


def extract_track_ids(text):
    ids = []
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

def fetch_track_data(track_id):
    url = f"https://open.spotify.com/track/{track_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch {track_id}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", type="application/ld+json")

    if not script_tag:
        print(f"No JSON-LD found for {track_id}")
        return None

    data = json.loads(script_tag.string)

    track_name = data.get("name", "")
    release_date = data.get("datePublished", "")
    year = release_date[:4] if release_date else ""
    description = data.get("description", "")

    # Extract artist
    artist = ""
    segments = [seg.strip() for seg in description.split("·")]

    if len(segments) >= 2:
        artist = segments[1]

    if not artist:
        print(f"Could not extract artist for {track_id}")

    return {
        "spotify_id": track_id,
        "artist": artist,
        "title": track_name,
        "year": year,
    }

if __name__ == "__main__":

    if len(sys.argv) != 2:
        print("Usage: python process_playlist_noapi.py <input_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    with open(file_path, "r") as f:
        raw_text = f.read()

    track_ids = extract_track_ids(raw_text)
    print(f"Extracted {len(track_ids)} track IDs")

    base_name = os.path.splitext(file_path)[0]
    output_file = f"{base_name}_cleaned.json"

    results = []

    for i, tid in enumerate(track_ids):
        print(f"[{i+1}/{len(track_ids)}] Processing {tid}")
        track_info = fetch_track_data(tid)

        if track_info:
            results.append(track_info)

        time.sleep(0.25)  # polite delay

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved {len(results)} tracks to {output_file}")