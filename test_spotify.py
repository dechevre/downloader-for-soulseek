import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')

#Spotify client
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri="http://127.0.0.1:8888/callback",
    scope="playlist-read-private playlist-read-collaborative user-read-private user-library-read",
    cache_path=".spotify_cache"
))

# call api
user = sp.current_user()
user_id = user["id"]
print("Logged in as:", user["display_name"])


# --- Debug block ---
print("🔍 Debug: Checking token scopes...")
token_info = sp.auth_manager.get_cached_token()
if token_info:
    print(f"Token scopes: {token_info['scope']}")
    print(f"Token expires in: {token_info['expires_in']} seconds")
else:
    print("No cached token found.")


# get playlist
def get_my_playlists():
    playlists = []
    results = sp.current_user_playlists()

    while results:
        for item in results["items"]:
            if item["owner"]["id"] == user_id:
                playlists.append({
                    "name": item["name"],
                    "id": item["id"]
                })

        if results["next"]:
            results = sp.next(results)
        else:
            results = None

    return playlists

# my playlists
my_playlists = get_my_playlists()

for i, p in enumerate(my_playlists):
    print(f"{i+1}. {p['name']}")

choice = int(input("Select playlist number: ")) - 1
selected_playlist_id = my_playlists[choice]["id"]

# tracks
def get_playlist_tracks(playlist_id):
    results = sp.playlist_items(
        playlist_id,
        market="GB"
    )

    tracks = []
    while results:
        for item in results["items"]:
            track = item["track"]
            if track:
                tracks.append({
                    "name": track["name"],
                    "artists": ", ".join(a["name"] for a in track["artists"])
                })

        if results["next"]:
            results = sp.next(results)
        else:
            results = None

    return tracks


tracks = get_playlist_tracks(selected_playlist_id)

print("\n📝 Your tracks:")
for i, track in enumerate(tracks):
    print(f"{i+1}. {track['artists']} - {track['name']}")