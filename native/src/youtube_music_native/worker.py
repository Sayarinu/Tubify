"""Private line-delimited provider protocol; never print credentials or raw errors."""

import json
import os
import sys

from .auth import AuthError, AuthService
from .credentials import CredentialError
from .session import SessionError


def handle(service, request):
    operation = request.get("operation")
    payload = request.get("payload") or {}
    if operation == "restore":
        return service.restore()
    if operation == "import_session":
        return service.import_session(payload["path"], tauri=bool(payload.get("tauri")))
    if operation == "sign_out":
        return service.sign_out()
    raise AuthError("That account operation is unavailable.")


def safe_error(error):
    if isinstance(error, (AuthError, CredentialError, SessionError)):
        return {"code": type(error).__name__, "message": str(error)}
    import requests

    if isinstance(error, (requests.ConnectionError, requests.Timeout)):
        return {"code": "offline", "message": "YouTube Music could not be reached. Downloads remain available offline."}
    if type(error).__name__ == "YTMusicUserError" or str(error).startswith(("Server returned HTTP 401", "Server returned HTTP 403")):
        return {"code": "reconnect", "message": "Your session needs reconnecting. Downloaded music remains available."}
    return {"code": "provider_error", "message": "YouTube Music could not complete this request. Retry or reconnect your account."}


def main():
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    service = None
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
            result = handle(service, request)
            response = {"id": identifier, "ok": True, "result": result}
        except Exception as error:
            response = {"id": identifier, "ok": False, "error": safe_error(error)}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
