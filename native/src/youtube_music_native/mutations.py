"""Provider-only account mutations; keep Qt out of the catalog worker."""

import re

class ActionError(RuntimeError):
    pass


def perform(client, action, identifier, value, payload=None):
    payload = payload or {}
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", identifier):
        raise ActionError("This music item is unavailable. Open it again and retry.")
    if action in {"album_library", "playlist_library"}:
        from ytmusicapi.models.content.enums import LikeStatus

        response = client.rate_playlist(identifier, LikeStatus.LIKE if value else LikeStatus.INDIFFERENT)
    elif action == "artist_subscription":
        if not identifier.startswith("UC"):
            raise ActionError("This artist has no subscription channel.")
        response = client.subscribe_artist(identifier) if value else client.unsubscribe_artists([identifier])
    elif action == "song_rating":
        from ytmusicapi.models.content.enums import LikeStatus

        if len(identifier) != 11 or value not in {"LIKE", "DISLIKE", "INDIFFERENT"}:
            raise ActionError("This song rating is invalid.")
        response = client.rate_song(identifier, LikeStatus(value))
    elif action == "song_library":
        if len(identifier) != 11:
            raise ActionError("This song has no valid music identifier.")
        token = payload.get("token")
        if not token and payload.get("albumId"):
            raw = client.get_album(payload["albumId"])
            song = next((track for track in raw.get("tracks", []) if track.get("videoId") == identifier), {})
            token = (song.get("feedbackTokens") or {}).get("add" if value else "remove")
        if not isinstance(token, str) or not 1 <= len(token) <= 16384 or any(ord(c) < 32 for c in token):
            raise ActionError("Open this song's album to change its library status.")
        response = client.edit_song_library_status([token])
    else:
        raise ActionError("This account action is unavailable.")
    if isinstance(response, dict) and (response.get("error") or response.get("status", "STATUS_SUCCEEDED") != "STATUS_SUCCEEDED"):
        raise ActionError("Your music could not be updated. Refresh and retry.")
    return {"action": action, "id": identifier, "value": value if action == "song_rating" else bool(value)}

