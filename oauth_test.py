import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import webbrowser
import time

load_dotenv()

print("1️⃣ Loading credentials...")
client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')

print("2️⃣ Setting up OAuth...")
print("   This will start a local server on port 8888")
print("   and open your browser for authorization.\n")

time.sleep(2)  # Give you time to read

try:
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://127.0.0.1:8888/callback",
        scope="playlist-read-private",
        cache_path=".spotify_cache",
        open_browser=True
    ))
    
    print("\n3️⃣ ✅ Authentication successful!")
    print("   Token saved to .spotify_cache")
    
    # Test by getting your profile
    user = sp.current_user()
    print(f"\n4️⃣ Logged in as: {user['display_name']}")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nDebug info:")
    print(f"Client ID exists: {bool(client_id)}")
    print(f"Client Secret exists: {bool(client_secret)}")
