"""Provider-only account mutations; keep Qt out of the catalog worker."""

import re

class ActionError(RuntimeError):
    pass


def perform(client, action, identifier, value):
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", identifier):
        raise ActionError("This music item is unavailable. Open it again and retry.")
    if action == "album_library":
        from ytmusicapi.models.content.enums import LikeStatus

        client.rate_playlist(identifier, LikeStatus.LIKE if value else LikeStatus.INDIFFERENT)
    elif action == "artist_subscription":
        if not identifier.startswith("UC"):
            raise ActionError("This artist has no subscription channel.")
        client.subscribe_artist(identifier) if value else client.unsubscribe_artists([identifier])
    else:
        raise ActionError("This account action is unavailable.")
    return {"action": action, "id": identifier, "value": bool(value)}

