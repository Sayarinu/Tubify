"""Owned stereo upmix filter; never changes the selected device or output layout."""

LABEL = "native-speaker-fill"
WAITING = "Play a stereo song on a 5.1 or 7.1 output to use speaker fill."
SURROUND = {"5.1": ("BL", "BR"), "5.1(side)": ("SL", "SR"),
            "7.1": ("BL", "BR", "SL", "SR")}


def channel_graph(layout):
    pairs = SURROUND.get(layout)
    if not pairs:
        return ""
    channels = ["FL=FL", "FR=FR", "FC=0.5*FL+0.5*FR", "LFE=0*FL"]
    channels.extend(f"{channel}={'FL' if channel.endswith('L') else 'FR'}" for channel in pairs)
    return "pan=" + layout + "|" + "|".join(channels)


class SpeakerFill:
    def __init__(self, player):
        self.player = player
        self.graph = ""
        self.failed = False

    def refresh(self, requested, ready):
        try:
            source = (self.player.audio_params or {}) if ready else {}
            output = (self.player.audio_out_params or {}) if ready else {}
            layout = output.get("channels", "")
            available = source.get("channels") == "stereo" and layout in SURROUND
            graph = channel_graph(layout) if requested and available else ""
            if graph != self.graph and (not self.failed or not graph):
                if self.graph:
                    self.player.command("af", "remove", "@" + LABEL)
                    self.graph = ""
                if graph:
                    self.player.command("af", "add", "@" + LABEL + ":lavfi=[" + graph + "]")
                    self.graph = graph
            if self.failed:
                message = "Speaker fill could not be applied. Normal output remains available; retry or turn it off."
            elif self.graph:
                message = "Speaker fill active on " + layout + ". The LFE channel remains silent."
            elif available:
                message = "Available on the current " + layout + " output. Copies stereo to surround speakers; LFE stays silent."
            else:
                message = WAITING
            return {"available": available and not self.failed, "active": bool(self.graph),
                    "failed": self.failed, "message": message}
        except Exception:
            # A rejected filter must not become an audio-device or track failure.
            self.failed = True
            return {"available": False, "active": bool(self.graph), "failed": True,
                    "message": "Speaker fill could not be changed. Retry or turn it off."}
