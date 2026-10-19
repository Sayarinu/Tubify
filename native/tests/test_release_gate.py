import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("release_gate", Path(__file__).parents[1] / "release_gate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def passing_report():
    return {"ticket": "LUNE-349", "matched_comparison": True, "soak_stable": True, "measurements": {"scroll_p95_frame_ms": 16, "local_input_p95_ms": 20, "cold_shell_max_ms": 500, "warm_shell_max_ms": 300, "local_audio_max_ms": 200, "native_steady_pss_mib": 250, "wrapper_steady_pss_mib": 600, "native_minimized_cpu_percent_one_core": 1, "native_stream_start_p95_ms": 500, "wrapper_stream_start_p95_ms": 600, "native_skip_p95_ms": 400, "wrapper_skip_p95_ms": 500, "mixed_use_soak_seconds": 1800}}


def test_complete_measurements_pass_and_missing_comparison_cannot_release():
    report = passing_report()
    module.verify(report)
    report["matched_comparison"] = False
    with pytest.raises(ValueError):
        module.verify(report)


@pytest.mark.parametrize("name,value", [("native_steady_pss_mib", 301), ("wrapper_steady_pss_mib", 400), ("local_audio_max_ms", float("nan")), ("local_input_p95_ms", True), ("mixed_use_soak_seconds", 1799), ("native_skip_p95_ms", 501)])
def test_incomplete_invalid_and_missed_targets_block_release(name, value):
    report = passing_report()
    report["measurements"][name] = value
    with pytest.raises(ValueError):
        module.verify(report)
