#!/usr/bin/env python3
import time, re, threading, sys
import mido, alsaaudio

# ---- Audio settings ----
CARD = 'default'        # 'default' for Pi jack OR your default DAC (/etc/asound.conf)
SAMPLE_RATE = 44100
PULSE_MS = 2.0
GAIN = 0.9
LEFT_ONLY = True
CLOCKS_PER_PULSE = 12   # 24 ppqn -> 12 ticks per 1/8 note (PO-friendly)

# Ignore common virtual/system endpoints
IGNORE = [r"Through", r"Virtual", r"System"]

def should_ignore(name: str) -> bool:
    return any(re.search(p, name, re.I) for p in IGNORE)

# ---- Prepare ALSA ----
pcm = alsaaudio.PCM(alsaaudio.PCM_PLAYBACK, device=CARD)
pcm.setchannels(2)
pcm.setrate(SAMPLE_RATE)
pcm.setformat(alsaaudio.PCM_FORMAT_S16_LE)
pcm.setperiodsize(256)

frames = int(SAMPLE_RATE * PULSE_MS / 1000.0)
amp = int(32767 * GAIN)
click = bytearray()
for _ in range(frames):
    L = amp
    R = 0 if LEFT_ONLY else amp
    click += bytes((L & 0xFF, (L >> 8) & 0xFF, R & 0xFF, (R >> 8) & 0xFF))
CLICK = bytes(click)
SILENCE = bytes(4 * 64)

# Prime DAC (reduces first-click pop)
for _ in range(10):
    pcm.write(SILENCE)

# ---- Shared state ----
lock = threading.Lock()
current_source = None          # str: mido port name
ticks_since_pulse = 0

def writer_click():
    try:
        pcm.write(CLICK)
        pcm.write(SILENCE)  # keep device primed
    except Exception as e:
        print(f"[clock2po] ALSA write: {e}", file=sys.stderr)

def listener(port_name: str):
    """Listen to one input port and, if elected, drive the click output."""
    global current_source, ticks_since_pulse
    try:
        with mido.open_input(port_name) as inp:
            for msg in inp:
                if msg.type in ('start', 'continue'):
                    with lock:
                        current_source = port_name
                        ticks_since_pulse = 0
                elif msg.type == 'stop':
                    with lock:
                        if current_source == port_name:
                            ticks_since_pulse = 0
                elif msg.type == 'clock':
                    with lock:
                        if current_source is None:
                            current_source = port_name
                        if current_source == port_name:
                            ticks_since_pulse += 1
                            if ticks_since_pulse >= CLOCKS_PER_PULSE:
                                ticks_since_pulse = 0
                                writer_click()
    except Exception as e:
        print(f"[clock2po] {port_name} closed ({e})", file=sys.stderr)

def main():
    global current_source
    spawned = set()  # ports we started threads for
    while True:
        try:
            present = set(n for n in mido.get_input_names() if not should_ignore(n))

            # Start listeners for new ports
            for name in sorted(present - spawned):
                t = threading.Thread(target=listener, args=(name,), daemon=True)
                t.start()
                spawned.add(name)

            # If current source vanished, allow reassignment
            with lock:
                if current_source and current_source not in present:
                    current_source = None

        except Exception as e:
            print(f"[clock2po] main loop: {e}", file=sys.stderr)

        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pcm.close()
        except Exception:
            pass
