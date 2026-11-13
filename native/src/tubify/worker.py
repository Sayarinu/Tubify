"""Private line-delimited provider protocol; never print credentials or raw errors."""

import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from .account.auth import AuthError, AuthService
from .catalog.catalog import STABLE_ROUTES, Catalog, CatalogError
from .account.credentials import CredentialError, remove_old_entries
from .account.session import SessionError
from .catalog.store import MetadataStore
from .playback.media import MediaFiles
from .playback.sources import SourceError, Sources
from .downloads.downloads import DownloadError, Downloads
from .local.library import LibraryError, LocalLibrary
from .catalog.mutations import ActionError, perform
from .catalog.playlist_ops import PlaylistError, perform as playlist_action
from .lyrics.lyric_data import Lyrics, LyricsError
from .lyrics.lyric_providers import ProviderUnavailable, provider_key
from .integrations.lastfm_service import LastFmService, LastFmError
from .util import session_rejected


PLAYLIST_ACTIONS = {"playlist_create", "playlist_rename", "playlist_delete", "playlist_add", "playlist_remove", "playlist_move"}
# Edits that delayed catalog reads must not undo (see _catalog).
REMEMBERED_CHANGES = {"playlist_rename", "playlist_remove", "playlist_move", "playlist_delete"}


def _shared(resources, kind, payload, create):
    """One long-lived helper per kind and data folder, reused across requests."""
    root = str(Path(payload["data_dir"]).resolve())
    key = (kind, root)
    if key not in resources:
        resources[key] = create(root)
    return resources[key]


def _maintenance(service, payload, resources, progress):
    from .updates.maintenance import perform as maintenance_action
    return maintenance_action(payload, progress=progress)


def _lastfm(service, payload, resources, progress):
    lastfm = _shared(resources, "lastfm", payload, LastFmService)
    try:
        return lastfm.perform(payload.get("action"), payload)
    except LastFmError:
        raise
    except Exception:
        raise LastFmError("storage", "Last.fm could not save or read its local state. Check storage and retry.") from None


def _artwork(service, payload, resources, progress):
    from .artwork.large_artwork import resolve
    return resolve(service, payload["data_dir"], payload["media"], payload["pixels"], bool(payload.get("online")))


def _lyrics_key(service, payload, resources, progress):
    return provider_key(payload.get("action"), payload.get("value", ""))


def _lyrics(service, payload, resources, progress):
    lyrics = _shared(resources, "lyrics", payload, lambda root: Lyrics(service, root))
    return lyrics.fetch(payload["videoId"], bool(payload.get("refresh")), payload.get("track"), payload.get("options"))


def _with_progress(downloads, progress, action):
    downloads.notify = progress or (lambda value: None)
    try:
        return action()
    finally:
        downloads.notify = lambda value: None


def _schedule(downloads, payload, progress):
    identifier = downloads.schedule(payload["media"], str(payload.get("files") or ""))
    return {**downloads.store.status(), "scheduled": identifier}


def _schedule_all(downloads, payload, progress):
    playlists = payload.get("playlists")
    if not isinstance(playlists, list) or len(playlists) > 10000:
        raise DownloadError("Choose playlists to download.")
    return _with_progress(downloads, progress, lambda: {**downloads.store.status(), **downloads.schedule_all(playlists, str(payload.get("files") or ""))})


def _run_downloads(downloads, payload, progress):
    downloads.notify = progress or (lambda value: None)
    return downloads.run_queue()


def _stop_download(downloads, payload, progress):
    downloads.store.stop()
    return downloads.store.status()


def _then_status(change):
    def action(downloads, payload, progress):
        change(downloads.store, payload)
        return downloads.store.status()
    return action


DOWNLOAD_OPERATIONS = {
    "downloads_status": _then_status(lambda store, payload: None),
    "downloads_initialize": _then_status(lambda store, payload: store.recover()),
    "downloads_schedule": _schedule,
    "downloads_schedule_all": _schedule_all,
    "downloads_run": _run_downloads,
    "downloads_cancel": _then_status(lambda store, payload: store.cancel(payload["id"])),
    "downloads_retry": _then_status(lambda store, payload: store.retry(payload["id"])),
    "downloads_remove": _then_status(lambda store, payload: store.remove(payload["id"])),
    "downloads_collection": lambda downloads, payload, progress: downloads.store.view(payload["id"]),
    "downloads_lookup": lambda downloads, payload, progress: downloads.store.lookup(payload["kind"], payload["id"]),
    "downloads_fail": _stop_download,
    "downloads_save_files": _then_status(lambda store, payload: store.request_files(payload["id"], str(payload["folder"]))),
}


def _downloads(operation, service, payload, resources, progress):
    downloads = _shared(resources, "downloads", payload, lambda root: Downloads(service, root))
    action = DOWNLOAD_OPERATIONS.get(operation)
    if action is None:
        raise DownloadError("This download operation is unavailable.")
    return action(downloads, payload, progress)


LOCAL_OPERATIONS = {
    "local_changes": lambda library, payload, progress: library.changes(int(payload.get("since") or 0)),
    "local_add_folder": lambda library, payload, progress: {"folder": library.add_folder(str(payload["path"])), **library.changes()},
    "local_remove_folder": lambda library, payload, progress: (library.remove_folder(int(payload["id"])), library.changes())[1],
    "local_remove_songs": lambda library, payload, progress: (library.remove_songs([str(value) for value in payload.get("ids", [])]), library.changes())[1],
    "local_forget_missing": lambda library, payload, progress: (library.forget_missing(payload.get("id")), library.changes())[1],
    "local_scan": lambda library, payload, progress: library.scan(payload.get("id"), progress),
}


def _local(operation, service, payload, resources, progress):
    """Local music works without an account: these operations never touch the session."""
    library = _shared(resources, "local", payload, LocalLibrary)
    action = LOCAL_OPERATIONS.get(operation)
    if action is None:
        raise LibraryError("This local music operation is unavailable.")
    return action(library, payload, progress or (lambda value: None))


def _account_change(change):
    """Run a sign-in change; cached workers belong to the previous account."""
    def action(service, payload, resources, progress):
        result = change(service, payload)
        resources.clear()
        return result
    return action


def _restore(service, payload, resources, progress):
    result = service.restore()
    if (payload or {}).get("removeOldEntries"):
        try:
            remove_old_entries()
            result = {**result, "oldEntriesRemoved": True}
        except CredentialError:
            # The keyring is locked or missing; the app tries again next launch.
            pass
    return result


def _account_history(service, payload, resources, progress):
    client = service.catalog()
    response = client.add_history_item(client.get_song(payload["videoId"]))
    if response.status_code != 204:
        raise ActionError("Listening history could not be updated.")
    # Recording a listen changes no cached view; wiping here made Home and the
    # sidebar refetch (and reshuffle) after every song.
    return {"recorded": True, "contextId": payload.get("contextId", "")}


def _account_action(service, payload, resources, progress):
    client = service.catalog()
    if payload["action"] in PLAYLIST_ACTIONS:
        result = playlist_action(client, payload["action"], payload)
    else:
        result = perform(client, payload["action"], payload["id"], payload.get("value"), payload)
    if result.get("action") in REMEMBERED_CHANGES:
        resources.setdefault("playlist_changes", []).append({"saved": time.time(), "result": result})
    store = None
    try:
        store = MetadataStore(payload["cache_path"])
        store.invalidate(STABLE_ROUTES)
    except sqlite3.Error:
        pass
    finally:
        if store:
            store.close()
    return {**result, "contextId": payload.get("contextId", "")}


def _catalog(service, payload, resources, progress):
    # Keep delayed read responses from undoing confirmed edits or skipping songs.
    changes = [change for change in resources.get("playlist_changes", []) if time.time() - change["saved"] < 30][-100:]
    resources["playlist_changes"] = changes
    store = MetadataStore(payload["cache_path"])
    try:
        return Catalog(service, store, changes).fetch(payload["route"], payload.get("params"), payload.get("offset", 0), bool(payload.get("refresh")), payload.get("page_size"))
    finally:
        store.close()


def _sources(service, payload, resources):
    root = str(Path(payload["data_dir"]).resolve())
    if root not in resources:
        resources[root] = Sources(service, MediaFiles(Path(root) / "media"))
    return resources[root]


def _warmup(service, payload, resources, progress):
    return _sources(service, payload, resources).warm()


def _resolve(service, payload, resources, progress):
    identifier = payload.get("videoId")
    if isinstance(identifier, str) and identifier.startswith("local:"):
        # A local file plays without the account or the network.
        library = _shared(resources, "local", payload, LocalLibrary)
        try:
            path = library.resolve(identifier, damaged=bool(payload.get("damaged")))
        except LibraryError as error:
            raise SourceError(str(error)) from None
        return {"kind": "local", "source": path, "headers": [], "videoId": identifier}
    sources = _sources(service, payload, resources)
    if payload.get("damaged"):
        sources.media.mark_damaged(payload["videoId"])
    return sources.resolve(payload["videoId"], force=bool(payload.get("force")), prepared=payload.get("prepared"), available=payload.get("available", True), video=bool(payload.get("video")))


OPERATIONS = {
    "maintenance": _maintenance,
    "lastfm": _lastfm,
    "artwork": _artwork,
    "lyrics_key": _lyrics_key,
    "lyrics": _lyrics,
    "restore": _restore,
    "import_session": _account_change(lambda service, payload: service.import_session(payload["path"])),
    "import_browser": _account_change(lambda service, payload: service.import_browser([name for name in payload.get("browsers", []) if isinstance(name, str)])),
    "sign_out": _account_change(lambda service, payload: service.sign_out()),
    "verify_session": lambda service, payload, resources, progress: service.verify(),
    "account_history": _account_history,
    "account_action": _account_action,
    "catalog": _catalog,
    "warmup": _warmup,
    "resolve": _resolve,
}


def handle(service, request, resources=None, progress=None):
    operation = request.get("operation")
    payload = request.get("payload") or {}
    resources = resources if resources is not None else {}
    if not isinstance(operation, str):
        raise AuthError("That account operation is unavailable.")
    if operation.startswith("downloads_"):
        return _downloads(operation, service, payload, resources, progress)
    if operation.startswith("local_"):
        return _local(operation, service, payload, resources, progress)
    action = OPERATIONS.get(operation)
    if action is None:
        raise AuthError("That account operation is unavailable.")
    return action(service, payload, resources, progress)


def safe_error(error):
    if isinstance(error, LastFmError):
        return {"code": "lastfm_" + error.code, "message": str(error)}
    if isinstance(error, (AuthError, CredentialError, SessionError, CatalogError, SourceError, DownloadError, LibraryError, ActionError, PlaylistError, LyricsError, ProviderUnavailable)):
        return {"code": type(error).__name__, "message": str(error)}
    import requests

    if isinstance(error, (requests.ConnectionError, requests.Timeout)):
        return {"code": "offline", "message": "YouTube Music could not be reached. Downloads remain available offline."}
    if session_rejected(error):
        return {"code": "reconnect", "message": "Your session needs reconnecting. Downloaded music remains available."}
    return {"code": "provider_error", "message": "YouTube Music could not complete this request. Retry or reconnect your account."}


def contain_children():
    """Kill extractor helpers (deno, ffmpeg) whenever this Windows worker is killed."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("Read", "Write", "Other", "ReadBytes", "WriteBytes", "OtherBytes")]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", Counters), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            return None
        info = Extended()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info)):
            return None
        if not kernel.AssignProcessToJobObject(wintypes.HANDLE(job), kernel.GetCurrentProcess()):
            return None
        # The handle stays open for the process lifetime; closing it kills the children.
        return job
    except Exception:
        return None


def main():
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    contain_children()
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
