"""Refuse a native release until the measured Linux performance gate passes."""

import json
import math
from pathlib import Path
import sys


def verify(report):
    if report.get("ticket") != "LUNE-349" or report.get("matched_comparison") is not True or report.get("soak_stable") is not True:
        raise ValueError("Matched benchmarks and the stable soak must be complete.")
    values = report.get("measurements", {})
    def value(name):
        result = values.get(name)
        if type(result) not in (int, float) or not math.isfinite(result) or result < 0:
            raise ValueError("Missing or invalid performance measurement: " + name)
        return result
    limits = {"scroll_p95_frame_ms": 16.7, "local_input_p95_ms": 100, "cold_shell_max_ms": 2000, "warm_shell_max_ms": 1000, "local_audio_max_ms": 250, "native_steady_pss_mib": 300, "native_minimized_cpu_percent_one_core": 2}
    for name, limit in limits.items():
        if value(name) > limit:
            raise ValueError("Performance target missed: " + name)
    if value("native_steady_pss_mib") > value("wrapper_steady_pss_mib") * .6:
        raise ValueError("The matched memory reduction is below 40 percent.")
    for operation in ("stream_start", "skip"):
        if value("native_" + operation + "_p95_ms") > value("wrapper_" + operation + "_p95_ms"):
            raise ValueError("Streaming regression: " + operation)
    if value("mixed_use_soak_seconds") < 1800:
        raise ValueError("The mixed-use soak is shorter than 30 minutes.")


def main():
    try:
        path = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).parent / "evidence" / "linux-performance.json"
        verify(json.loads(path.read_text()))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print("Native release gate is incomplete: " + str(error), file=sys.stderr)
        return 1
    print("Native Linux performance release gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
