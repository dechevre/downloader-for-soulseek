from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from playlist_loader import fetch_playlist_track_ids_from_url, fetch_tracks_from_track_ids, parse_pasted_playlist_text, extract_playlist_id

app = FastAPI()


class PlaylistRequest(BaseModel):
    input_type: str  # "spotify_url" or "spotify_id"
    input_value: str

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "Track Hacker API is running"}

@app.post("/playlist")
def load_playlist(request: PlaylistRequest):
    if request.input_type == "spotify_url":
        playlist_id = extract_playlist_id(request.input_value)
        if not playlist_id:
            return {"error": "Invalid Spotify playlist URL"}
        track_ids = fetch_playlist_track_ids_from_url(request.input_value)
        tracks = fetch_tracks_from_track_ids(track_ids,"Loading playlist")
        return {"tracks": tracks}

    elif request.input_type == "pasted_text":
        tracks = parse_pasted_playlist_text(request.input_value)
        return {"tracks": tracks}
    
    return {"error": "Unsupported input type"}

