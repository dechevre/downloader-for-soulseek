import os
import sys
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth


# -------- Spotify Auth --------

load_dotenv()

client_id = os.getenv("SPOTIFY_CLIENT_ID")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri="http://127.0.0.1:8888/callback",
    scope="user-read-private",
    cache_path=".spotify_cache"
))


# -------- Helpers --------

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


def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def fetch_tracks(track_ids):
    all_tracks = []

    for batch in chunk_list(track_ids, 50):
        response = sp.tracks(batch)

        for track in response["tracks"]:
            if track:
                artist_names = ", ".join(a["name"] for a in track["artists"])
                clean_line = f"{artist_names} - {track['name']}"
                all_tracks.append(clean_line)

    return all_tracks


# -------- Main CLI --------

if __name__ == "__main__":

    if len(sys.argv) != 2:
        print("Usage: python process_playlist.py <input_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    with open(file_path, "r") as f:
        raw_text = f.read()

    track_ids = extract_track_ids(raw_text)

    print(f"Extracted {len(track_ids)} track IDs")

    clean_tracks = fetch_tracks(track_ids)

    base_name = os.path.splitext(file_path)[0]
    output_file = f"{base_name}_clean.txt"
    
    with open(output_file, "w") as f:
        for line in clean_tracks:
            f.write(line + "\n")

    print(f"\nSaved {len(clean_tracks)} tracks to {output_file}")