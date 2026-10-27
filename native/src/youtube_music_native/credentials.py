"""OS-vault storage with atomic replacement and portable credential sizes."""

import base64
from dataclasses import dataclass, field
import json
import re
import sys
from uuid import uuid4

from .session import Session


SERVICE = "com.carter.youtube-music.native"
USERNAME = "session"
# Windows credentials allow 2560 bytes. ASCII chunks also fit UTF-16 encoding.
CHUNK_SIZE = 800
MAX_CHUNKS = 128
# Other vaults take the whole session as one record. On macOS every record can need its own
# access approval, so one record means at most one prompt.
LARGE_CHUNK = CHUNK_SIZE * MAX_CHUNKS


def default_chunk_size(platform=None):
    return CHUNK_SIZE if (platform or sys.platform) == "win32" else LARGE_CHUNK


class CredentialError(RuntimeError):
    pass


class CorruptManifest(CredentialError):
    pass


def secure_backend():
    import keyring

    try:
        selected = keyring.get_keyring()
        candidates = getattr(selected, "backends", [selected])
        approved = ("SecretService", "libsecret", "kwallet", "Windows", "macOS", "OS_X")
        for candidate in candidates:
            module = type(candidate).__module__
            if any(module == "keyring.backends." + name or module.startswith("keyring.backends." + name + ".") for name in approved):
                if candidate.priority > 0:
                    if hasattr(candidate, "appid"):
                        candidate.appid = SERVICE
                    return candidate
    except Exception:
        pass
    raise CredentialError("A secure system keyring is unavailable. Unlock or enable it and reconnect.")


@dataclass(repr=False)
class StoredAccount:
    session: Session = field(repr=False)
    profile: dict = field(repr=False)

    def __repr__(self):
        return "StoredAccount(<redacted>)"


class Credentials:
    def __init__(self, backend=None, chunk_size=None):
        self.chunk_size = chunk_size or default_chunk_size()
        self.backend = backend if backend is not None else secure_backend()

    def _manifest(self):
        raw = self.backend.get_password(SERVICE, USERNAME)
        if raw is None:
            return None
        try:
            manifest = json.loads(raw)
        except (ValueError, TypeError):
            raise CorruptManifest("The saved session is incomplete. Reconnect YouTube Music.") from None
        if (
            not isinstance(manifest, dict)
            or
            manifest.get("version") != 1
            or not isinstance(manifest.get("id"), str)
            or not re.fullmatch(r"[a-f0-9]{32}", manifest["id"])
            or not isinstance(manifest.get("count"), int)
            or not 1 <= manifest["count"] <= MAX_CHUNKS
        ):
            raise CorruptManifest("The saved session is incomplete. Reconnect YouTube Music.")
        return manifest

    def _chunk_service(self, manifest, index):
        return f"{SERVICE}.session.{manifest['id']}.{index}"

    def _remove_chunks(self, manifest):
        if manifest:
            for index in range(manifest["count"]):
                try:
                    self.backend.delete_password(self._chunk_service(manifest, index), USERNAME)
                except Exception:
                    pass

    def load(self):
        try:
            manifest = self._manifest()
            if manifest is None:
                return None
            pieces = [self.backend.get_password(self._chunk_service(manifest, index), USERNAME) for index in range(manifest["count"])]
            if not all(isinstance(piece, str) and len(piece) <= LARGE_CHUNK for piece in pieces):
                raise ValueError()
            value = json.loads(base64.b64decode("".join(pieces), validate=True))
            profile = value["profile"]
            if not isinstance(profile, dict) or not all(isinstance(v, str) for v in profile.values()):
                raise ValueError()
            return StoredAccount(Session.from_payload(value["session"]), profile)
        except Exception:
            raise CredentialError("The saved session could not be read. Unlock your keyring or reconnect.") from None

    def save(self, session, profile):
        try:
            try:
                previous = self._manifest()
            except Exception:
                # A corrupt entry, or one another app build may no longer read (macOS ties entries to
                # the code signature), is replaced rather than blocking a fresh sign-in.
                previous = None
            encoded = base64.b64encode(json.dumps({"session": session.to_payload(), "profile": profile}, separators=(",", ":")).encode()).decode("ascii")
            parts = [encoded[index:index + self.chunk_size] for index in range(0, len(encoded), self.chunk_size)]
            if not 1 <= len(parts) <= MAX_CHUNKS:
                raise CredentialError("The session is too large for portable keyring storage.")
            manifest = {"version": 1, "id": uuid4().hex, "count": len(parts)}
            committing = False
            try:
                for index, part in enumerate(parts):
                    self.backend.set_password(self._chunk_service(manifest, index), USERNAME, part)
                # Commit the pointer only after all secret chunks are safely stored.
                committing = True
                self.backend.set_password(SERVICE, USERNAME, json.dumps(manifest))
            except Exception:
                # A lost vault reply can follow a successful commit. Keep chunks
                # when the pointer outcome is uncertain instead of breaking it.
                if not committing:
                    self._remove_chunks(manifest)
                raise
            self._remove_chunks(previous)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("The session could not be saved. Unlock your system keyring and retry.") from None

    def clear(self):
        try:
            try:
                manifest = self._manifest()
            except CorruptManifest:
                self.backend.delete_password(SERVICE, USERNAME)
                return
            if manifest is None:
                return
            self.backend.delete_password(SERVICE, USERNAME)
            self._remove_chunks(manifest)
        except Exception:
            raise CredentialError("Sign-out could not clear the session. Unlock your keyring and retry.") from None
