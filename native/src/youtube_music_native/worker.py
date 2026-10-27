"""Private line-delimited provider protocol; never print credentials or raw errors."""

import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from .auth import AuthError, AuthService
from .catalog import Catalog, CatalogError
from .credentials import CredentialError
from .session import SessionError
from .store import MetadataStore
from .media import MediaFiles
from .sources import SourceError, Sources
from .downloads import DownloadError, Downloads
from .mutations import ActionError, perform
from .playlist_ops import PlaylistError, perform as playlist_action
from .lyric_data import Lyrics, LyricsError
from .lyric_providers import ProviderUnavailable, provider_key
from .lastfm_service import LastFmService, LastFmError


def handle(service, request, resources=None, progress=None):
    operation = request.get("operation")
    payload = request.get("payload") or {}
    resources = resources if resources is not None else {}
    if operation == "maintenance":
        from .maintenance import perform as maintenance_action
        return maintenance_action(payload)
    if operation == "lastfm":
        root = str(Path(payload["data_dir"]).resolve())
        key = ("lastfm", root)
        if key not in resources:
            resources[key] = LastFmService(root)
        try:
            return resources[key].perform(payload.get("action"), payload)
        except LastFmError:
            raise
        except Exception:
            raise LastFmError("storage", "Last.fm could not save or read its local state. Check storage and retry.") from None
    if operation == "artwork":
        from .large_artwork import resolve
        return resolve(service, payload["data_dir"], payload["media"], payload["pixels"], bool(payload.get("online")))
    if operation == "lyrics_key":
        return provider_key(payload.get("action"), payload.get("value", ""))
    if operation == "lyrics":
        root = str(Path(payload["data_dir"]).resolve())
        key = ("lyrics", root)
        if key not in resources:
            resources[key] = Lyrics(service, root)
        return resources[key].fetch(payload["videoId"], bool(payload.get("refresh")), payload.get("track"), payload.get("options"))
    if isinstance(operation, str) and operation.startswith("downloads_"):
        resources = resources if resources is not None else {}
        root = str(Path(payload["data_dir"]).resolve())
        key = ("downloads", root)
        if key not in resources:
            resources[key] = Downloads(service, root)
        downloads = resources[key]
        if operation == "downloads_initialize":
            downloads.store.recover()
        elif operation == "downloads_schedule":
            identifier = downloads.schedule(payload["media"])
            return {**downloads.store.status(), "scheduled": identifier}
        elif operation == "downloads_run":
            downloads.notify = progress or (lambda value: None)
            return downloads.run(payload["id"])
        elif operation == "downloads_cancel":
            downloads.store.cancel(payload["id"])
        elif operation == "downloads_retry":
            downloads.store.retry(payload["id"])
        elif operation == "downloads_remove":
            downloads.store.remove(payload["id"])
        elif operation == "downloads_collection":
            return downloads.store.view(payload["id"])
        elif operation == "downloads_lookup":
            return downloads.store.lookup(payload["kind"], payload["id"])
        elif operation == "downloads_fail":
            if downloads.store.state(payload["id"]) in {"queued", "downloading"}:
                body = downloads.store.collection(payload["id"])
                downloads.store.progress(payload["id"], 0, len(body["items"]), state="failed", error="Download stopped. Retry to continue; completed songs were kept.")
        elif operation != "downloads_status":
            raise DownloadError("This download operation is unavailable.")
        return downloads.store.status()
    if operation == "restore":
        return service.restore()
    if operation == "import_session":
        result = service.import_session(payload["path"], tauri=bool(payload.get("tauri")))
        resources.clear()
        return result
    if operation == "import_browser":
        result = service.import_browser([name for name in payload.get("browsers", []) if isinstance(name, str)])
        resources.clear()
        return result
    if operation == "sign_out":
        result = service.sign_out()
        resources.clear()
        return result
    if operation in {"account_action", "account_history"}:
        client = service.catalog()
        if operation == "account_history":
            response = client.add_history_item(client.get_song(payload["videoId"]))
            if response.status_code != 204:
                raise ActionError("Listening history could not be updated.")
            result = {"recorded": True}
        elif payload["action"] in {"playlist_create", "playlist_rename", "playlist_delete", "playlist_add", "playlist_remove", "playlist_move"}:
            result = playlist_action(client, payload["action"], payload)
        else:
            result = perform(client, payload["action"], payload["id"], payload.get("value"), payload)
        if result.get("action") in {"playlist_rename", "playlist_remove", "playlist_move", "playlist_delete"}:
            resources.setdefault("playlist_changes", []).append({"saved": time.time(), "result": result})
        store = None
        try:
            store = MetadataStore(payload["cache_path"])
            store.invalidate()
        except sqlite3.Error:
            pass
        finally:
            if store:
                store.close()
        return {**result, "contextId": payload.get("contextId", "")}
    if operation == "catalog":
        # Keep delayed read responses from undoing confirmed edits or skipping songs.
        changes = [change for change in resources.get("playlist_changes", []) if time.time() - change["saved"] < 30][-100:]
        resources["playlist_changes"] = changes
        store = MetadataStore(payload["cache_path"])
        try:
            return Catalog(service, store, changes).fetch(payload["route"], payload.get("params"), payload.get("offset", 0), bool(payload.get("refresh")), payload.get("page_size"))
        finally:
            store.close()
    if operation == "resolve":
        resources = resources if resources is not None else {}
        root = str(Path(payload["data_dir"]).resolve())
        if root not in resources:
            resources[root] = Sources(service, MediaFiles(Path(root) / "media"))
        sources = resources[root]
        if payload.get("damaged"):
            sources.media.mark_damaged(payload["videoId"])
        return sources.resolve(payload["videoId"], force=bool(payload.get("force")), prepared=payload.get("prepared"), available=payload.get("available", True))
    raise AuthError("That account operation is unavailable.")


def safe_error(error):
    if isinstance(error, LastFmError):
        return {"code": "lastfm_" + error.code, "message": str(error)}
    if isinstance(error, (AuthError, CredentialError, SessionError, CatalogError, SourceError, DownloadError, ActionError, PlaylistError, LyricsError, ProviderUnavailable)):
        return {"code": type(error).__name__, "message": str(error)}
    import requests

    if isinstance(error, (requests.ConnectionError, requests.Timeout)):
        return {"code": "offline", "message": "YouTube Music could not be reached. Downloads remain available offline."}
    if str(error).startswith(("Server returned HTTP 401", "Server returned HTTP 403")):
        return {"code": "reconnect", "message": "Your session needs reconnecting. Downloaded music remains available."}
    return {"code": "provider_error", "message": "YouTube Music could not complete this request. Retry or reconnect your account."}


def main():
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    service = None
    resources = {}
    for line in sys.stdin:
        identifier = None
        try:
            if len(line) > 1024 * 1024:
                raise AuthError("The account request is too large.")
            request = json.loads(line)
            identifier = request["id"]
            if not isinstance(identifier, int):
                identifier = None
                raise AuthError("The account request is invalid.")
            if service is None:
                service = AuthService()
            result = handle(service, request, resources, lambda value: print(json.dumps({"id": identifier, "progress": value}), flush=True))
            response = {"id": identifier, "ok": True, "result": result}
        except Exception as error:
            response = {"id": identifier, "ok": False, "error": safe_error(error)}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
