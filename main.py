import asyncio
import soulseek_client
import traceback
import os
import shutil
import re
import yaml
import json
import subprocess


from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from playlist_loader import fetch_playlist_track_ids_from_url, fetch_tracks_from_track_ids, parse_pasted_playlist_text, extract_playlist_id
from track_processor import process_track, spotify_track_from_dict

MAX_RETRIES = 3
RETRY_POLL_INTERVAL = 5  # seconds between each poll

ERRORED_STATES = {"Completed, Errored", "Completed, TimedOut"}

retry_counts: dict[str, int] = {}

TRACK_HACKER_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "track_hacker_config.json")

DEFAULT_CONFIG = {
    "slskd_path": os.path.expanduser("~/slskd/slskd"),
    "slskd_config_path": os.path.expanduser("~/Library/Application Support/slskd/slskd.yml"),
    "download_subfolder": "Track Hacker Music"
}

def load_track_hacker_config() -> dict:
    try:
        with open(TRACK_HACKER_CONFIG_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return DEFAULT_CONFIG.copy()

def get_slskd_config_path() -> str:
    return load_track_hacker_config().get("slskd_config_path", DEFAULT_CONFIG["slskd_config_path"])

def save_track_hacker_config(config: dict) -> None:
    with open(TRACK_HACKER_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def resolve_and_create_download_dir(subfolder: str) -> str:
    full_path = os.path.join(os.path.expanduser("~/Downloads"), subfolder)
    incomplete_path = os.path.join(full_path, "Incomplete")
    os.makedirs(full_path, exist_ok=True)
    os.makedirs(incomplete_path, exist_ok=True)
    return full_path


def get_download_dir() -> str:
    try:
        with open(get_slskd_config_path(), "r") as f:
            config = yaml.safe_load(f)
        return os.path.expanduser(
            config.get("directories", {}).get("downloads", "~/Music/slskd")
        )
    except Exception:
        return os.path.expanduser("~/Music/slskd")

def flatten_completed_download(transfer: dict) -> None:
    DOWNLOAD_DIR = get_download_dir()
    remote_filename = transfer.get("filename", "")
    # Get just the file's basename
    basename = re.split(r"[\\/]", remote_filename)[-1]
    # Get the last folder component
    parts = re.split(r"[\\/]", remote_filename)
    last_folder = parts[-2] if len(parts) >= 2 else None
    
    if not last_folder or not basename:
        return

    current_path = os.path.join(DOWNLOAD_DIR, last_folder, basename)
    target_path = os.path.join(DOWNLOAD_DIR, basename)

    if os.path.exists(current_path) and not os.path.exists(target_path):
        shutil.move(current_path, target_path)
        print(f"[flatten] moved {basename} to flat directory")
        # Clean up empty folder
        try:
            os.rmdir(os.path.join(DOWNLOAD_DIR, last_folder))
        except OSError:
            pass  # folder not empty, leave it

async def retry_failed_downloads():
    """
    Background task that polls slskd every RETRY_POLL_INTERVAL seconds,
    finds errored transfers, and re-enqueues them up to MAX_RETRIES times.
    """
    while True:
        await asyncio.sleep(RETRY_POLL_INTERVAL)
        try:
            # get_downloads() returns a list of user objects, each with
            # a "directories" list containing transfer objects
            downloads = soulseek_client.get_downloads()

            for user in downloads:
                username = user.get("username", "")
                directories = user.get("directories", [])

                for directory in directories:
                    files = directory.get("files", [])

                    for transfer in files:
                        state = transfer.get("state", "")
                        filename = transfer.get("filename", "")
                        size = transfer.get("size")
                        key = f"{username}::{filename}"


                        if "Completed" in state:
                            flatten_completed_download(transfer)

                        if state not in ERRORED_STATES:
                            continue

                        attempts = retry_counts.get(key, 0)
                        if attempts >= MAX_RETRIES:
                            print(f"[retry] giving up on {filename} from {username} after {MAX_RETRIES} attempts")
                            continue

                        retry_counts[key] = attempts + 1
                        print(f"[retry] attempt {attempts + 1}/{MAX_RETRIES} for {filename} from {username}")

                        try:
                            soulseek_client.enqueue_download(
                                username=username,
                                filename=filename,
                                size=size,
                            )
                        except Exception as e:
                            print(f"[retry] failed to re-enqueue {filename}: {e}")

        except Exception as e:
            print(f"[retry] error polling downloads: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs on startup — launches the retry loop as a background task
    task = asyncio.create_task(retry_failed_downloads())
    yield
    # Runs on shutdown — cancels the background task cleanly
    task.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

semaphore  = asyncio.Semaphore(3)  # Limit to 5 concurrent track processing tasks

class PlaylistRequest(BaseModel):
    input_type: str  # "spotify_url" or "spotify_id"
    input_value: str

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


@app.post("/search")
async def search_tracks(track: dict):
    async with semaphore:
        try:
            spotify_track = spotify_track_from_dict(track)
            format_preference = track.get("format_preference", "best_available")
            result = process_track(spotify_track, search_timeout=90, format_preference=format_preference)
            return result
        except Exception as e:
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e),
                "ranked_candidates": [],
                "counts": {"ranked_candidates_returned": 0}
            }

    
@app.post("/download")
def download_track(candidate: dict):
    try:
        soulseek_client.enqueue_download(
            username=candidate["username"],
            filename=candidate["filename"],
            size=candidate.get("size")
        )
        return {"status": "queued"}
    except Exception as e:
        print(f"[download] failed to enqueue {candidate.get('filename')}: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/config")
def get_config():
    return {"download_dir": get_download_dir()}

@app.post("/config")
def update_config(body: dict):
    try:
        subfolder = body.get("subfolder", "Track Hacker Music")
        full_path = resolve_and_create_download_dir(subfolder)
        
        with open(get_slskd_config_path(), "r") as f:
            config = yaml.safe_load(f)
        
        config.setdefault("directories", {})["downloads"] = full_path
        config["directories"]["incomplete"] = os.path.join(full_path, "Incomplete")       
         
        with open(get_slskd_config_path(), "w") as f:
            yaml.dump(config, f)
        
        return {"status": "ok", "download_dir": full_path}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/setup")
def setup(body: dict):
    try:
        slskd_path = body.get("slskd_path", DEFAULT_CONFIG["slskd_path"])
        username = body["username"]
        password = body["password"]
        subfolder = body.get("download_subfolder", "Track Hacker Music")

        # Save Track Hacker config
        th_config = load_track_hacker_config()
        th_config["slskd_path"] = slskd_path
        th_config["download_subfolder"] = subfolder
        save_track_hacker_config(th_config)

        # Create download dirs
        full_path = resolve_and_create_download_dir(subfolder)

        # Write slskd.yml
        slskd_config_path = get_slskd_config_path()
        try:
            with open(slskd_config_path, "r") as f:
                slskd_config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            slskd_config = {}

        slskd_config.setdefault("soulseek", {})["username"] = username
        slskd_config["soulseek"]["password"] = password
        slskd_config.setdefault("directories", {})["downloads"] = full_path
        slskd_config["directories"]["incomplete"] = os.path.join(full_path, "Incomplete")
        slskd_config.setdefault("authentication", {})["disabled"] = True

        with open(slskd_config_path, "w") as f:
            yaml.dump(slskd_config, f)

        # Start slskd
        subprocess.Popen([slskd_path])

        return {"status": "ok", "download_dir": full_path}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

@app.get("/health")
def health():
    try:
        soulseek_client.get_token()
        return {"slskd": "ok"}
    except Exception:
        return {"slskd": "unreachable"}

@app.get("/downloads/status")
def get_downloads_status():
    try:
        downloads = soulseek_client.get_downloads()
        return {"downloads": downloads}
    except Exception as e:
        return {"error": str(e)}