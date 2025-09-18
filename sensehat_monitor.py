#!/usr/bin/env python3
import time, subprocess
from sense_hat import SenseHat

sense = SenseHat()
sense.low_light = True
sense.clear()

# Colors
RED   = (255, 0, 0)
GREEN = (0, 255, 0)
AMBER = (255, 120, 0)
OFF   = (0, 0, 0)

def cpu_usage():
    """Return fraction of CPU busy (0.0–1.0) averaged over 0.25s."""
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
    vals = list(map(int, parts))
    idle = vals[3] + vals[4]    # idle + iowait
    total = sum(vals)

    time.sleep(0.25)

    with open("/proc/stat") as f:
        parts2 = f.readline().split()[1:]
    vals2 = list(map(int, parts2))
    idle2 = vals2[3] + vals2[4]
    total2 = sum(vals2)

    didle = idle2 - idle
    dtotal = total2 - total
    if dtotal <= 0:
        return 0.0
    busy = dtotal - didle
    return max(0.0, min(1.0, busy / dtotal))

def service_ok(name):
    """Return True if systemd service is active."""
    r = subprocess.run(
        ["systemctl", "is-active", "--quiet", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return r.returncode == 0

def draw(cpu_frac, ok_autopatch, ok_clock2po):
    """
    Amber bars for CPU load.
    Top-left  pixel (0,0): midi-autopatch.service (green/red)
    Top-right pixel (7,0): clock2po.service       (green/red)
    """
    bars = int(round(cpu_frac * 8))
    pixels = []
    for y in range(8):
        for x in range(8):
            fill = (7 - y) < bars  # bottom-up
            pixels.append(AMBER if fill else OFF)

    # Set heartbeat pixels after filling bars
    idx_top_left  = 0 * 8 + 0
    idx_top_right = 0 * 8 + 7
    pixels[idx_top_left]  = GREEN if ok_autopatch else RED
    pixels[idx_top_right] = GREEN if ok_clock2po else RED

    sense.set_pixels(pixels)

def main():
    # gentle startup
    for _ in range(3):
        draw(0.0, service_ok("midi-autopatch.service"), service_ok("clock2po.service"))
        time.sleep(0.3)

    while True:
        c  = cpu_usage()
        ok1 = service_ok("midi-autopatch.service")
        ok2 = service_ok("clock2po.service")
        draw(c, ok1, ok2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sense.clear()
        except Exception:
            pass
