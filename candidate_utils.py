
from __future__ import annotations

from typing import Any

SAFE_AUDIO_EXTENSIONS = {"mp3", "wav", "aiff", "aif", "flac"}
SUSPICIOUS_EXTENSIONS = {"exe", "bat", "cmd", "com", "scr", "js", "jar", "msi", "zip", "rar", "7z"}

def candidate_safety_notes(candidate: dict[str, Any]) -> list[str]:
    notes: list[str] = []

    extension = str(candidate.get("extension") or "").lower()
    bitrate = candidate.get("bitrate")
    length = candidate.get("length")
    size_mb = candidate.get("size_mb")

    if extension in SAFE_AUDIO_EXTENSIONS:
        notes.append(f"Audio file: {extension.upper()}")
    elif extension in SUSPICIOUS_EXTENSIONS:
        notes.append(f"Warning: suspicious extension {extension.upper()}")
    else:
        notes.append(f"Unknown or less common extension: {extension.upper() or '?'}")

    if bitrate:
        notes.append(f"Bitrate: {bitrate}kbps")
    else:
        notes.append("Bitrate missing")

    if length:
        notes.append(f"Length: {length}s")
    else:
        notes.append("Length missing")

    if size_mb:
        notes.append(f"Size: {size_mb}MB")
    else:
        notes.append("Size missing")

    return notes
