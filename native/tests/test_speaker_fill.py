import array
import shutil
import subprocess

import pytest

from youtube_music_native.speaker_fill import LABEL, SpeakerFill, channel_graph


class Output:
    def __init__(self, source="stereo", output="5.1"):
        self.audio_params = {"channels": source}
        self.audio_out_params = {"channels": output}
        self.af = [{"label": "other", "name": "volume"}]
        self.commands = []
        self.reject = False

    def command(self, *args):
        self.commands.append(args)
        if self.reject:
            raise RuntimeError("synthetic failure")
        if args[1] == "add":
            self.af.append({"label": LABEL})
        else:
            self.af = [item for item in self.af if item["label"] != LABEL]


@pytest.mark.parametrize("layout,tail", [("5.1", "BL=FL|BR=FR"),
                                          ("5.1(side)", "SL=FL|SR=FR"),
                                          ("7.1", "BL=FL|BR=FR|SL=FL|SR=FR")])
def test_owned_mapping_default_off_and_idempotent_without_device_changes(layout, tail):
    output = Output(output=layout)
    fill = SpeakerFill(output)
    state = fill.refresh(False, True)
    assert state["available"] and not state["active"] and not output.commands
    assert channel_graph(layout).endswith(tail)
    state = fill.refresh(True, True)
    assert state["active"] and len(output.commands) == 1
    assert "FC=0.5*FL+0.5*FR|LFE=0*FL" in output.commands[0][2]
    assert fill.refresh(True, True) == state and len(output.commands) == 1
    state = fill.refresh(False, True)
    assert not state["active"] and output.af == [{"label": "other", "name": "volume"}]
    assert all(command[0] == "af" for command in output.commands)


@pytest.mark.parametrize("source,output", [("mono", "5.1"), ("5.1", "5.1"),
                                            ("stereo", "stereo"), ("stereo", "unknown"),
                                            ("", "")])
def test_unsupported_source_or_output_removes_only_our_filter(source, output):
    device = Output()
    fill = SpeakerFill(device)
    fill.refresh(True, True)
    device.audio_params, device.audio_out_params = {"channels": source}, {"channels": output}
    state = fill.refresh(True, True)
    assert not state["available"] and not state["active"]
    assert device.af == [{"label": "other", "name": "volume"}]
    assert not channel_graph("unknown")


def test_track_load_device_loss_and_retry_keep_normal_output_reachable():
    output = Output()
    fill = SpeakerFill(output)
    assert fill.refresh(True, True)["active"]
    assert not fill.refresh(True, False)["active"]
    output.reject = True
    assert fill.refresh(True, True)["failed"]
    count = len(output.commands)
    assert not fill.refresh(True, True)["active"] and len(output.commands) == count
    output.reject = False
    fill.failed = False
    assert fill.refresh(True, True)["active"]
    output.audio_out_params = None
    assert not fill.refresh(True, True)["active"]
    assert output.af == [{"label": "other", "name": "volume"}]
    output.audio_out_params = {"channels": "7.1"}
    assert fill.refresh(True, True)["active"]


@pytest.mark.parametrize("layout,channels", [("5.1", 6), ("5.1(side)", 6), ("7.1", 8)])
def test_ffmpeg_synthetic_channel_values(layout, channels):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg required for synthetic PCM mapping")
    result = subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
        "aevalsrc=0.1|0.2:c=stereo:s=48000:d=0.01", "-af", channel_graph(layout),
        "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"], capture_output=True, check=True, timeout=10)
    samples = array.array("f", result.stdout)
    import sys
    if sys.byteorder != "little":
        samples.byteswap()
    expected = [0.1, 0.2, 0.15, 0, 0.1, 0.2] + ([0.1, 0.2] if channels == 8 else [])
    assert len(samples) >= channels * 10
    for index in range(0, len(samples), channels):
        assert list(samples[index:index + channels]) == pytest.approx(expected, abs=1e-6)


def test_failed_removal_is_reported_truthfully_and_can_be_retried():
    output = Output()
    fill = SpeakerFill(output)
    assert fill.refresh(True, True)["active"]
    output.reject = True
    state = fill.refresh(False, True)
    assert state["failed"] and state["active"] and "could not be changed" in state["message"]
    assert len(output.af) == 2
    output.reject = False
    fill.failed = False
    state = fill.refresh(False, True)
    assert not state["failed"] and not state["active"]
    assert len(output.af) == 1
