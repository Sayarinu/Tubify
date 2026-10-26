"""Small private-pipe bridge to the native client's approved OS keyring backends."""

import json
import re
import sys

from .credentials import SERVICE, secure_backend

VAULT, ACCOUNT = SERVICE + ".streamdeck", "paired-client"
MAX_INPUT = 4096


def credential(value):
    if not isinstance(value, dict) or set(value) != {"port", "clientId", "token", "scope"}:
        raise ValueError()
    if type(value["port"]) is not int or not 1024 <= value["port"] <= 65535 or value["scope"] != "control":
        raise ValueError()
    if not isinstance(value["clientId"], str) or not re.fullmatch(r"[a-f0-9]{32}", value["clientId"]):
        raise ValueError()
    if not isinstance(value["token"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value["token"]):
        raise ValueError()
    return value


def execute(request, backend=None):
    if not isinstance(request, dict) or request.get("action") not in {"read", "write", "delete"}:
        raise ValueError()
    action = request["action"]
    if set(request) != ({"action", "credential"} if action == "write" else {"action"}):
        raise ValueError()
    value = credential(request["credential"]) if action == "write" else None
    backend = backend if backend is not None else secure_backend()
    if action == "write":
        backend.set_password(VAULT, ACCOUNT, json.dumps(value, separators=(",", ":")))
    elif action == "read":
        raw = backend.get_password(VAULT, ACCOUNT)
        return {"ok": True, "credential": credential(json.loads(raw)) if raw is not None else None}
    elif backend.get_password(VAULT, ACCOUNT) is not None:
        backend.delete_password(VAULT, ACCOUNT)
    return {"ok": True}


def main(stdin=None, stdout=None):
    source, target = stdin or sys.stdin, stdout or sys.stdout
    try:
        raw = source.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError()
        result = execute(json.loads(raw))
    except (ValueError, TypeError, KeyError, RecursionError):
        result = {"ok": False, "error": "Invalid Stream Deck credential request."}
    except Exception:
        result = {"ok": False, "error": "Unlock or enable the system keyring, then retry pairing."}
    # Only the invoking plugin's pipe receives credentials. Never log request/error objects.
    target.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0 if result["ok"] else 1
