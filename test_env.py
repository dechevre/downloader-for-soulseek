import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

print("Current working directory:", os.getcwd())
print(".env exists?", Path('.env').exists())
print(".env absolute path:", Path('.env').absolute())

client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI')

print(f"Client ID: {client_id[:5]}...{client_id[-5:] if client_id else 'NOT FOUND'}")
print(f"Client Secret: {'*' * 10 if client_secret else 'NOT FOUND'}")
print(f"Redirect URI: {redirect_uri}")

if not all([client_id, client_secret, redirect_uri]):
    print("\n Missing some credentials! Check your .env file")
else:
    print("\n All credentials loaded successfully!")


print(f"Client ID loaded?", "✅ Yes" if client_id else "❌ No")
print(f"Client Secret loaded?", "✅ Yes" if client_secret else "❌ No")
print(f"Redirect URI loaded?", "✅ Yes" if redirect_uri else "❌ No")

# Only try to print preview if values exist
if client_id:
    print(f"Client ID preview: {client_id[:5]}...{client_id[-5:]}")
else:
    print("Client ID: NOT FOUND")