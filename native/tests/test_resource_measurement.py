import os
import subprocess
import sys
import time

import pytest

from measure_resources import sample, summarize


@pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc resource measurements")
def test_resource_counter_includes_live_helpers_and_their_reaped_cpu():
    before = sample(os.getpid())
    process = subprocess.Popen([sys.executable, "-c", "import time; data=bytearray(16*1024*1024); end=time.monotonic()+.2\nwhile time.monotonic()<end: pass\ntime.sleep(.3)"])
    try:
        time.sleep(.15)
        during = sample(os.getpid())
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    after = sample(os.getpid())
    assert during["processes"] > before["processes"]
    assert during["pss_mib"] > before["pss_mib"]
    assert after["cpu_ticks"] >= during["cpu_ticks"] >= before["cpu_ticks"]
    report = summarize([{**before, "seconds": 0}, {**after, "seconds": 1}], os.sysconf("SC_CLK_TCK"))
    assert report["steady_cpu_one_core_percent"] > 0
