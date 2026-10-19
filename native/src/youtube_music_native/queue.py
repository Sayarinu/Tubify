"""Playback source, one-time manual additions and actual played history."""

import math
import random
from uuid import uuid4


def new_entries(tracks):
    return [{"key": uuid4().hex, "track": dict(track)} for track in tracks]


class Queue:
    def __init__(self):
        self.source, self.manual, self.history = [], [], []
        self.current = None
        self.source_label = ""
        self._history_sources = []
        self.source_index = -1
        self.repeat = "off"
        self.shuffled = False
        self._original = []

    @property
    def remaining(self):
        return [entry for entry in self.source[self.source_index + 1:] if entry is not self.current]

    @property
    def entries(self):
        return ([self.current] if self.current else []) + self.manual + self.remaining

    @property
    def all_entries(self):
        return list({entry["key"]: entry for entry in self.source + self.manual + self.history + ([self.current] if self.current else [])}.values())

    def replace(self, tracks, index=0, source_label=""):
        self.source_label = source_label.strip()
        self.source = new_entries(tracks)
        self.source_index = max(0, min(int(index), len(self.source) - 1)) if self.source else -1
        self.current = self.source[self.source_index] if self.source else None
        self.history, self._history_sources = [], []
        self._original = [entry["key"] for entry in self.source]
        if self.shuffled:
            self._shuffle_remaining()

    def append_context(self, tracks):
        entries = new_entries(tracks)
        self.source.extend(entries)
        self._original.extend(entry["key"] for entry in entries)
        if self.shuffled:
            self._shuffle_remaining()

    def append(self, tracks, next=False):
        entries = new_entries(tracks)
        if next:
            self.manual[0:0] = entries
        else:
            self.manual.extend(entries)
        if self.current is None and self.manual:
            self.current = self.manual.pop(0)

    def _remember(self):
        if self.current:
            self.history.append(self.current)
            self._history_sources.append(self.source[self.source_index]["key"] if self.source_index >= 0 else None)
            self.history = self.history[-1000:]
            self._history_sources = self._history_sources[-1000:]

    def select(self, index):
        if not 0 <= index < len(self.entries):
            return None
        entry = self.entries[index]
        if entry is self.current:
            return entry
        self._remember()
        if entry in self.manual:
            del self.manual[:self.manual.index(entry) + 1]
        else:
            self.source_index = self.source.index(entry)
        self.current = entry
        return entry

    def peek(self, automatic=False):
        if automatic and self.repeat == "one" and self.current:
            return self.current
        if self.manual:
            return self.manual[0]
        if self.source_index + 1 < len(self.source):
            return self.source[self.source_index + 1]
        if self.repeat == "all" and self.source:
            return self.source[0]
        return None

    def advance(self, automatic=False):
        entry = self.peek(automatic)
        if entry is None:
            return None
        if automatic and self.repeat == "one" and entry is self.current:
            return entry
        self._remember()
        if self.manual and entry is self.manual[0]:
            self.manual.pop(0)
        else:
            self.source_index = self.source.index(entry)
        self.current = entry
        return entry

    def previous(self):
        if not self.history:
            return None
        # Replaying history does not put consumed manual entries back in the queue.
        self.current = self.history.pop()
        anchor = self._history_sources.pop()
        self.source_index = next((index for index, entry in enumerate(self.source) if entry["key"] == anchor), -1)
        return self.current

    def clear_manual(self):
        self.manual = []

    def remove(self, index):
        if not 0 <= index < len(self.entries):
            return False
        entry = self.entries[index]
        was_current = entry is self.current
        if entry in self.manual:
            self.manual.remove(entry)
        if entry in self.source:
            location = self.source.index(entry)
            preceding = self.source[location - 1]["key"] if location else None
            self._history_sources = [preceding if key == entry["key"] else key for key in self._history_sources]
            self.source.pop(location)
            self._original.remove(entry["key"])
            if location <= self.source_index:
                self.source_index -= 1
        history = [(prior, anchor) for prior, anchor in zip(self.history, self._history_sources) if prior["key"] != entry["key"]]
        self.history = [prior for prior, anchor in history]
        self._history_sources = [anchor for prior, anchor in history]
        if was_current:
            self.current = None
            self.advance()
        return was_current

    def move(self, source, destination):
        entries = self.entries
        if not (0 <= source < len(entries) and 0 <= destination < len(entries)):
            return
        moving, target = entries[source], entries[destination]
        if moving is self.current or target is self.current:
            return
        if moving in self.manual and target in self.manual:
            group = self.manual
        elif moving in self.remaining and target in self.remaining:
            group = self.source
        else:
            return
        origin, end = group.index(moving), group.index(target)
        group.insert(end, group.pop(origin))
        if group is self.source:
            self._original = [entry["key"] for entry in self.source]

    def _shuffle_remaining(self):
        remaining = self.source[self.source_index + 1:]
        random.shuffle(remaining)
        self.source[self.source_index + 1:] = remaining

    def shuffle_all(self):
        self.shuffled = True
        random.shuffle(self.source)
        self.source_index = 0 if self.source else -1
        self.current = self.source[0] if self.source else None
        self.history, self._history_sources = [], []

    def toggle_shuffle(self):
        self.shuffled = not self.shuffled
        if self.shuffled:
            self._shuffle_remaining()
        else:
            order = {key: index for index, key in enumerate(self._original)}
            self.source[self.source_index + 1:] = sorted(self.source[self.source_index + 1:], key=lambda entry: order[entry["key"]])

    def cycle_repeat(self):
        self.repeat = {"off": "all", "all": "one", "one": "off"}[self.repeat]

    def snapshot(self, position=0):
        return {"version": 2, "entries": self.all_entries, "source": [entry["key"] for entry in self.source],
                "source_index": self.source_index, "source_label": self.source_label, "history_sources": self._history_sources, "manual": [entry["key"] for entry in self.manual],
                "history": [entry["key"] for entry in self.history], "current": self.current["key"] if self.current else None,
                "position": position, "repeat": self.repeat, "shuffled": self.shuffled, "original": self._original}

    def restore(self, value):
        try:
            version, entries = value.get("version", 1), value["entries"]
            if version not in {1, 2} or not isinstance(entries, list) or len(entries) > 100000:
                return 0
            if not all(isinstance(entry, dict) and isinstance(entry.get("key"), str) and isinstance(entry.get("track"), dict) for entry in entries):
                return 0
            pool = {entry["key"]: entry for entry in entries}
            if len(pool) != len(entries):
                return 0
            position = float(value.get("position", 0))
            if not math.isfinite(position):
                return 0
            if version == 1:
                source, manual, history = entries, [], []
                index = max(-1, min(int(value.get("index", -1)), len(entries) - 1))
                current = entries[index] if index >= 0 else None
                label, history_sources = "", []
            else:
                def group(name, duplicates=False):
                    keys = value[name]
                    if not isinstance(keys, list) or len(keys) > 100000 or not all(isinstance(key, str) and key in pool for key in keys):
                        raise ValueError("Invalid queue references")
                    if not duplicates and len(set(keys)) != len(keys):
                        raise ValueError("Duplicate queue references")
                    return [pool[key] for key in keys]
                source, manual, history = group("source"), group("manual"), group("history", duplicates=True)
                label = value.get("source_label", "")
                history_sources = value.get("history_sources", [])
                if not isinstance(label, str) or len(label) > 4096 or not isinstance(history_sources, list) or len(history_sources) != len(history):
                    return 0
                source_keys = set(value["source"])
                if not all(key is None or isinstance(key, str) and key in source_keys for key in history_sources):
                    return 0
                current = pool[value["current"]] if value["current"] is not None else None
                index = int(value["source_index"])
                if not -1 <= index < max(1, len(source)) or (not source and index != -1):
                    return 0
                if set(value["source"]) & set(value["manual"]) or current in manual:
                    return 0
            keys = [entry["key"] for entry in source]
            original = value.get("original", [])
            if not isinstance(original, list) or len(original) != len(keys) or not all(isinstance(key, str) for key in original) or set(original) != set(keys):
                original = keys
            self.source, self.manual, self.history = source, manual, history[-1000:]
            self.source_label, self._history_sources = label, history_sources[-1000:]
            self.source_index, self.current, self._original = index, current, original
            self.repeat = value.get("repeat") if value.get("repeat") in ("off", "all", "one") else "off"
            self.shuffled = bool(value.get("shuffled"))
            return max(0, position)
        except (KeyError, TypeError, ValueError, OverflowError):
            return 0
