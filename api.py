from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from track_processor import process_track, spotify_track_from_dict


app = FastAPI(title="DJ Track Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TrackIn(BaseModel):
    artist: str
    title: str
    duration: int | None = None
    year: int | None = None


class SearchTrackRequest(BaseModel):
    track: TrackIn
    format_preference: str = "best_available"
    search_timeout: int = 45
    retry_on_timeout: int = 1
    top_n: int = 10


@app.get("/")
def root():
    return {"message": "API is running"}


@app.post("/tracks/search")
def search_track(payload: SearchTrackRequest):
    try:
        track = spotify_track_from_dict(payload.track.model_dump())

        result = process_track(
            track,
            format_preference=payload.format_preference,
            search_timeout=payload.search_timeout,
            retry_on_timeout=payload.retry_on_timeout,
            top_n=payload.top_n,
        )

        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc