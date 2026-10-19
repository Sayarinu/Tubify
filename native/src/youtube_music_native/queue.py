"""Queue order and selection, independent of audio devices and the provider."""

import random
from uuid import uuid4


class Queue:
    def __init__(self):
        self.entries = []
        self.index = -1
        self.repeat = "off"
        self.shuffled = False
        self._original = []

    @property
    def current(self):
        return self.entries[self.index] if 0 <= self.index < len(self.entries) else None

    def replace(self, tracks, index=0):
        self.entries = [{"key": uuid4().hex, "track": dict(track)} for track in tracks]
        self.index = max(0, min(int(index), len(self.entries) - 1)) if self.entries else -1
        self._original = [entry["key"] for entry in self.entries]
        if self.shuffled:
            self._shuffle_remaining()

    def append(self, tracks, next=False):
        entries = [{"key": uuid4().hex, "track": dict(track)} for track in tracks]
        position = self.index + 1 if next else len(self.entries)
        self.entries[position:position] = entries
        if self.index < 0 and entries:
            self.index = 0
        keys = [entry["key"] for entry in entries]
        if next and self.current:
            location = self._original.index(self.current["key"]) + 1 if self.current["key"] in self._original else 0
            self._original[location:location] = keys
        else:
            self._original.extend(keys)
        if self.shuffled and not next:
            self._shuffle_remaining()

    def select(self, index):
        if 0 <= index < len(self.entries):
            self.index = index
            return self.current
        return None

    def advance(self, automatic=False):
        if not self.entries:
            return None
        if automatic and self.repeat == "one":
            return self.current
        if self.index + 1 < len(self.entries):
            self.index += 1
        elif self.repeat == "all":
            self.index = 0
        else:
            return None
        return self.current

    def previous(self):
        return self.select(max(0, self.index - 1))

    def remove(self, index):
        if not 0 <= index < len(self.entries):
            return False
        was_current = index == self.index
        removed = self.entries.pop(index)
        self._original.remove(removed["key"])
        if index < self.index:
            self.index -= 1
        if self.index >= len(self.entries):
            self.index = len(self.entries) - 1
        return was_current

    def move(self, source, destination):
        if not (0 <= source < len(self.entries) and 0 <= destination < len(self.entries)):
            return
        selected = self.current["key"] if self.current else None
        self.entries.insert(destination, self.entries.pop(source))
        self.index = next((i for i, entry in enumerate(self.entries) if entry["key"] == selected), -1)
        self._original = [entry["key"] for entry in self.entries]

    def _shuffle_remaining(self):
        remaining = self.entries[self.index + 1:]
        random.shuffle(remaining)
        self.entries[self.index + 1:] = remaining

    def shuffle_all(self):
        self.shuffled = True
        random.shuffle(self.entries)
        self.index = 0 if self.entries else -1

    def toggle_shuffle(self):
        self.shuffled = not self.shuffled
        if self.shuffled:
            self._shuffle_remaining()
        else:
            order = {key: index for index, key in enumerate(self._original)}
            self.entries[self.index + 1:] = sorted(self.entries[self.index + 1:], key=lambda entry: order[entry["key"]])

    def cycle_repeat(self):
        self.repeat = {"off": "all", "all": "one", "one": "off"}[self.repeat]

    def snapshot(self, position=0):
        return {"version": 1, "entries": self.entries, "index": self.index, "position": position, "repeat": self.repeat, "shuffled": self.shuffled, "original": self._original}

    def restore(self, value):
        try:
            entries = value["entries"]
            if not isinstance(entries, list) or len(entries) > 100000:
                return 0
            if not all(isinstance(entry, dict) and isinstance(entry.get("key"), str) and isinstance(entry.get("track"), dict) for entry in entries):
                return 0
            keys = [entry["key"] for entry in entries]
            if len(set(keys)) != len(keys):
                return 0
            self.entries = entries
            self.index = max(-1, min(int(value.get("index", -1)), len(entries) - 1))
            self.repeat = value.get("repeat") if value.get("repeat") in {"off", "all", "one"} else "off"
            self.shuffled = bool(value.get("shuffled"))
            original = value.get("original", [])
            self._original = original if isinstance(original, list) and set(original) == set(keys) else keys
            return max(0, float(value.get("position", 0)))
        except (KeyError, TypeError, ValueError):
            self.entries, self.index, self._original = [], -1, []
            return 0
