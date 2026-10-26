"""Persisted lyric choices; secrets are deliberately outside this schema."""

PROVIDERS = {"lrclib": "LRCLIB", "unison": "Unison", "better": "Better Lyrics"}
DEFAULTS = {
    "external": False, "captions": False, "approximate": False,
    "timestamps": False, "autoOpen": False, "style": "line",
    "providers": [{"id": key, "enabled": True} for key in PROVIDERS],
}


def clean_options(value):
    value = value if isinstance(value, dict) else {}
    result = {key: value.get(key) is True for key in DEFAULTS if key not in {"providers", "style"}}
    result["style"] = value.get("style") if value.get("style") in {"line", "word", "syllable"} else "line"
    rows, seen = [], set()
    for row in value.get("providers", []) if isinstance(value.get("providers"), list) else []:
        if isinstance(row, dict) and row.get("id") in PROVIDERS and row["id"] not in seen:
            rows.append({"id": row["id"], "enabled": row.get("enabled") is True})
            seen.add(row["id"])
    rows.extend({"id": key, "enabled": True} for key in PROVIDERS if key not in seen)
    result["providers"] = rows
    return result
