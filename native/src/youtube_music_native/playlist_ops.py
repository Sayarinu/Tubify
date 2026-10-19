"""Playlist mutations preserve occurrence IDs and report provider failures safely."""

import re


class PlaylistError(RuntimeError):
    pass


def identifier(value, video=False):
    pattern = r"[A-Za-z0-9_-]{11}" if video else r"[A-Za-z0-9_-]{1,256}"
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise PlaylistError("This music item is unavailable. Refresh the playlist and retry.")
    return value


def occurrence(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise PlaylistError("This playlist entry has changed. Refresh the playlist and retry.")
    return value


def title(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 150 or any(ord(c) < 32 or c in "<>" for c in value):
        raise PlaylistError("Enter a playlist name with 1–150 characters, without line breaks, < or >.")
    return value.strip()


def apply_change(data, result, collection_id=None, added=None):
    action = result["action"]
    for container in [data.get("items", [])] + [section.get("items", []) for section in data.get("shelves", [])]:
        if action == "playlist_rename":
            for item in container:
                if item.get("kind") == "playlist" and item.get("id") == result["id"]:
                    item["title"] = result["title"]
        elif action == "playlist_delete":
            container[:] = [item for item in container if not (item.get("kind") == "playlist" and item.get("id") == result["id"])]
    if collection_id != result["id"]:
        return
    tracks = list(data.get("items", []))
    if action == "playlist_rename":
        data["title"] = result["title"]
    elif action == "playlist_remove":
        key = result.get("removedSetVideoId") or result.get("setVideoId")
        removed = [track for track in tracks if track.get("setVideoId") == key]
        tracks = [track for track in tracks if track.get("setVideoId") != key]
        data["trackCount"] = max(0, data.get("trackCount", len(tracks) + len(removed)) - len(removed))
        data["duration"] = max(0, data.get("duration", 0) - sum(track.get("duration", 0) for track in removed))
        if data.get("cursor") is not None:
            data["cursor"] = max(0, data["cursor"] - len(removed))
    elif action == "playlist_move":
        key = result.get("movedSetVideoId") or result.get("setVideoId")
        moved = next((track for track in tracks if track.get("setVideoId") == key), None)
        successor = result.get("successor")
        anchor = next((track for track in tracks if track.get("setVideoId") == successor), None)
        if moved and (anchor or not successor):
            tracks.remove(moved)
            tracks.insert(tracks.index(anchor) if anchor else len(tracks), moved)
    elif action == "playlist_add":
        existing = {track.get("setVideoId") for track in tracks}
        entries = [entry for entry in result.get("addedEntries", []) if entry["setVideoId"] not in existing]
        if added and data.get("cursor") is None:
            tracks.extend({**added, **entry, "id": entry["videoId"], "kind": "song"} for entry in entries)
        data["trackCount"] = data.get("trackCount", len(tracks) - len(entries)) + len(entries)
        data["duration"] = data.get("duration", 0) + len(entries) * (added or {}).get("duration", 0)
        data["thumbnail"] = data.get("thumbnail") or (added or {}).get("thumbnail", "")
    data["items"] = tracks


def perform(client, action, payload):
    result = {"action": action}
    if action == "playlist_create":
        name = title(payload.get("title"))
        created = client.create_playlist(name, "", privacy_status="PRIVATE")
        if not isinstance(created, str) or created.startswith("STATUS_"):
            raise PlaylistError("The playlist could not be created. Retry.")
        return {**result, "id": identifier(created), "title": name}
    playlist = identifier(payload.get("id"))
    result["id"] = playlist
    if action == "playlist_rename":
        result["title"] = title(payload.get("title"))
        response = client.edit_playlist(playlist, title=result["title"])
    elif action == "playlist_delete":
        response = client.delete_playlist(playlist)
    elif action == "playlist_add":
        videos = payload.get("videoIds")
        if not isinstance(videos, list) or not 1 <= len(videos) <= 1000:
            raise PlaylistError("Choose songs to add to this playlist.")
        response = client.add_playlist_items(playlist, [identifier(v, video=True) for v in videos], duplicates=True)
    elif action == "playlist_remove":
        entry = {"videoId": identifier(payload.get("videoId"), video=True), "setVideoId": occurrence(payload.get("setVideoId"))}
        response = client.remove_playlist_items(playlist, [entry])
        result["removedSetVideoId"] = entry["setVideoId"]
    elif action == "playlist_move":
        entry = occurrence(payload.get("setVideoId"))
        successor = occurrence(payload["successor"]) if payload.get("successor") else None
        if entry == successor:
            raise PlaylistError("Choose a different position for this playlist entry.")
        response = client.edit_playlist(playlist, moveItem=(entry, successor) if successor else entry)
        result.update(movedSetVideoId=entry, successor=successor or "")
    else:
        raise PlaylistError("This playlist action is unavailable.")
    status = response.get("status") if isinstance(response, dict) else response
    if action == "playlist_delete" and status is None and isinstance(response, dict) and not response.get("error"):
        rows = client.get_library_playlists(limit=None)
        if not any((row.get("playlistId") or row.get("browseId", "").removeprefix("VL")) == playlist for row in rows):
            return result
    if status != "STATUS_SUCCEEDED":
        raise PlaylistError("The playlist could not be updated. Refresh and retry.")
    if action == "playlist_add" and isinstance(response, dict):
        result["addedEntries"] = [{"videoId": row["videoId"], "setVideoId": row["setVideoId"]} for row in response.get("playlistEditResults", []) if isinstance(row, dict) and row.get("videoId") and row.get("setVideoId")]
    return result
