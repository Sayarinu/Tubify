"""Bounded LRC/TTML parsing, preserving supplied timing and XML text/tail spacing."""

import math
import re
import xml.etree.ElementTree as ET

MAX_TEXT = 512 * 1024
MAX_DOCUMENT = 2 * 1024 * 1024
MAX_LINES = 10000


def seconds(value):
    if not isinstance(value, str):
        raise ValueError("Missing cue timestamp")
    value = value.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?ms", value):
        result = float(value[:-2]) / 1000
    elif re.fullmatch(r"\d+(?:\.\d+)?s", value):
        result = float(value[:-1])
    elif re.fullmatch(r"\d+(?::\d{1,2}){0,2}(?:\.\d+)?", value):
        result = 0.
        for part in value.split(":"):
            result = result * 60 + float(part)
    else:
        raise ValueError("Invalid cue timestamp")
    if not math.isfinite(result) or not 0 <= result <= 86400:
        raise ValueError("Invalid cue timestamp")
    return result


def checked_document(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_DOCUMENT:
        raise ValueError("Lyrics document is too large")
    return text


def finish(lines, identity=None):
    if len(lines) > MAX_LINES or sum(len(line["text"]) for line in lines) > MAX_TEXT:
        raise ValueError("Lyrics are too large")
    timed_lines = [line for line in lines if 0 <= line["start"] < line["end"]]
    timed = bool(timed_lines)
    if timed:
        # Isolate malformed cues and terminal empty markers without discarding
        # genuine timing from the remainder of the document.
        lines = sorted(timed_lines, key=lambda line: line["start"])
    else:
        for line in lines:
            line.update(start=-1., end=-1., words=[])
    words = [word for line in lines for word in line.get("words", [])]
    sync = "syllable" if any(word.get("syllable") for word in words) else "word" if words else "line" if timed else "plain"
    return {"lines": lines, "timed": timed, "syncLevel": sync, "available": any(line["text"].strip() for line in lines), "identity": identity or {}}


def plain(text):
    checked_document(text)
    return finish([{"text": row, "start": -1., "end": -1.} for row in text.splitlines()])


def lrc(text, duration=0):
    checked_document(text)
    lines, identity = [], {}
    stamp = re.compile(r"\[(\d+:\d+(?:\.\d+)?)\]")
    for raw in text.splitlines():
        metadata = re.fullmatch(r"\[(ti|ar|al):(.+)\]", raw.strip(), re.I)
        if metadata:
            identity[{"ti": "title", "ar": "artist", "al": "album"}[metadata[1].lower()]] = metadata[2].strip()
            continue
        raw = raw.lstrip()
        matches, offset = [], 0
        while match := stamp.match(raw, offset):
            matches.append(match)
            offset = match.end()
        if not matches:
            continue
        body = raw[offset:].strip()
        for match in matches:
            try:
                start = seconds(match[1])
            except ValueError:
                continue
            lines.append({"text": body, "start": start, "end": -1.})
    lines.sort(key=lambda row: row["start"])
    starts = sorted({line["start"] for line in lines})
    ends = dict(zip(starts, starts[1:] + [max(starts[-1], duration or 86400.)])) if starts else {}
    for line in lines:
        line["end"] = ends[line["start"]]
    return finish(lines, identity)


def ttml(text):
    checked_document(text)
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("Unsupported XML declarations")
    tree = ET.fromstring(text)
    lines, identity = [], {}
    def local(tag):
        return tag.rsplit("}", 1)[-1]
    for element in tree.iter():
        name = local(element.tag)
        # Only explicit track metadata proves identity; vocalist agent names do not.
        if name in {"title", "song", "artist", "album"} and element.text:
            identity["title" if name == "song" else name] = element.text.strip()
        if name == "duration" and element.text:
            try:
                identity["duration"] = seconds(element.text)
            except ValueError:
                pass
        if name != "p":
            continue
        parts, words, offset = [], [], 0
        def append(value, timing, syllable):
            nonlocal offset
            if not value:
                return
            parts.append(value)
            if timing and value.strip():
                words.append({"text": value, "offset": offset, "start": timing[0], "end": timing[1], "syllable": syllable})
            offset += len(value)
        def visit(node, inherited=None, depth=0):
            if depth > 32:
                raise ValueError("Lyrics XML is too deeply nested")
            if local(node.tag) == "br":
                append("\n", None, False)
                return
            timing = inherited
            own = local(node.tag) == "span" and "begin" in node.attrib and "end" in node.attrib
            if own:
                try:
                    start, end = seconds(node.get("begin")), seconds(node.get("end"))
                    timing = (start, end) if start < end else None
                except ValueError:
                    timing = None
            syllable = own and inherited is not None
            append(node.text, timing, syllable)
            for child in node:
                visit(child, timing, depth + 1)
                append(child.tail, timing, syllable)
        visit(element)
        body = "".join(parts)
        try:
            start, end = seconds(element.get("begin")), seconds(element.get("end"))
        except ValueError:
            start, end = -1., -1.
        # A malformed word cue never becomes an invented timing interval.
        words = [word for word in words if start <= word["start"] < word["end"] <= end]
        lines.append({"text": body, "start": start, "end": end, "words": words})
    return finish(lines, identity)
