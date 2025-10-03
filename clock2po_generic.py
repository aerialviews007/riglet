#!/usr/bin/env python3
"""
Riglet: MIDI Clock -> PO Sync Clicks (Pirate Audio / ALSA)

- Adopts the first active MIDI clock source (unless one is already running)
- Only emits clicks when transport is running (after START/CONTINUE; mutes on STOP)
- Hot-plugs MIDI devices (threads per input)
- Left channel only by default (PO listens on L = tip)
- Robust ALSA open with retries; logs but does not crash on transient errors
"""

import sys, time, re, threading, signal
from typing import Optional
import mido

# ---- USER SETTINGS -----------------------------------------------------------
ALSA_DEVICE = 'default'   # e.g. 'default' (via /etc/asound.conf) or 'hw:0,0'
SAMPLE_RATE = 44100
PULSE_MS    = 3.0         # 2.0–3.0 ms works well for Pocket Operators
GAIN        = 1.0         # 0.0–1.0; PO often prefers hot pulses
LEFT_ONLY   = True        # True = L only; False = L+R

CLOCKS_PER_PULSE = 12     # MIDI clock = 24 ppqn -> 12 = 1/8th; PO default
IGNORE_PATTERNS  = [r"Through", r"Virtual", r"System"]
MIDI_SCAN_SEC    = 1.0    # rescan inputs every N seconds

ALSA_OPEN_RETRIES = 20    # open() attempts
ALSA_OPEN_DELAY   = 0.5   # seconds between attempts
ALSA_PERIOD_FR    = 256   # ALSA period size (frames) for writes
# -----------------------------------------------------------------------------

# ---- Logging -----------------------------------------------------------------
def log(*args):
    print("[clock2po]", *args, file=sys.stderr, flush=True)

# ---- ALSA PCM (lazy import to speed failure when module missing) -------------
pcm = None
click_buf = b""
silence_buf = b""

def should_ignore(name: str) -> bool:
    return any(re.search(p, name, re.I) for p in IGNORE_PATTERNS)

def _open_alsa():
    """Open ALSA PCM with retries; prepare click & silence buffers."""
    global pcm, click_buf, silence_buf
    import alsaaudio

    for i in range(1, ALSA_OPEN_RETRIES + 1):
        try:
            pcm = alsaaudio.PCM(type=alsaaudio.PCM_PLAYBACK, device=ALSA_DEVICE)
            pcm.setchannels(2)
            pcm.setrate(SAMPLE_RATE)
            pcm.setformat(alsaaudio.PCM_FORMAT_S16_LE)
            pcm.setperiodsize(ALSA_PERIOD_FR)
            break
        except Exception as e:
            log(f"ALSA open attempt {i}/{ALSA_OPEN_RETRIES} failed on '{ALSA_DEVICE}': {e}")
            time.sleep(ALSA_OPEN_DELAY)
    if pcm is None:
        raise RuntimeError(f"Could not open ALSA device '{ALSA_DEVICE}'")

    # build click buffer
    frames = max(1, int(SAMPLE_RATE * (PULSE_MS / 1000.0)))
    amp = max(0, min(32767, int(32767 * GAIN)))
    # 16-bit little-endian interleaved stereo
    b = bytearray()
    for _ in range(frames):
        L = amp
        R = 0 if LEFT_ONLY else amp
        b += bytes((L & 0xFF, (L >> 8) & 0xFF, R & 0xFF, (R >> 8) & 0xFF))
    click_buf = bytes(b)
    # short silence chunk keeps DAC primed between clicks
    silence_buf = bytes(4 * 64)

    # Pre-prime output to reduce first-click pop
    try:
        for _ in range(8):
            pcm.write(silence_buf)
    except Exception as e:
        log(f"ALSA prime write error: {e}")

alsa_lock = threading.Lock()

def write_click():
    """Emit one click safely."""
    if pcm is None:
        return
    with alsa_lock:
        try:
            pcm.write(click_buf)
            pcm.write(silence_buf)
        except Exception as e:
            log(f"ALSA write error: {e}")

# ---- MIDI handling -----------------------------------------------------------
current_source: Optional[str] = None
running = False
ticks = 0
state_lock = threading.Lock()
threads = {}
stop_event = threading.Event()

def adopt_source(port_name: str):
    global current_source, running, ticks
    with state_lock:
        if current_source is None:
            current_source = port_name
            running = False
            ticks = 0
            log(f"Adopted clock source: {port_name}")

def clear_source_if_gone(present_ports):
    global current_source, running
    with state_lock:
        if current_source and current_source not in present_ports:
            log(f"Clock source vanished: {current_source}")
            current_source = None
            running = False

def listener(port_name: str):
    """Listen to one MIDI input; gate by global current_source & transport."""
    global current_source, running, ticks
    try:
        with mido.open_input(port_name) as inp:
            log(f"Listening on: {port_name}")
            for msg in inp:
                if stop_event.is_set():
                    break
                t = msg.type
                if t in ('start', 'continue'):
                    with state_lock:
                        if current_source is None:
                            current_source = port_name
                        if current_source == port_name:
                            running = True
                            ticks = 0
                elif t == 'stop':
                    with state_lock:
                        if current_source == port_name:
                            running = False
                            ticks = 0
                elif t == 'clock':
                    with state_lock:
                        if current_source is None:
                            adopt_source(port_name)
                        if current_source == port_name and running:
                            ticks += 1
                            if ticks >= CLOCKS_PER_PULSE:
                                ticks = 0
                                write_click()
                # ignore other messages
    except Exception as e:
        log(f"Listener for '{port_name}' ended: {e}")

def scan_and_spawn():
    """Spawn listeners for any new MIDI inputs (excluding ignored)."""
    present = set(n for n in mido.get_input_names() if not should_ignore(n))
    # start new threads
    for name in sorted(present - threads.keys()):
        t = threading.Thread(target=listener, args=(name,), daemon=True)
        threads[name] = t
        t.start()
    # cleanup dead threads
    for name, t in list(threads.items()):
        if not t.is_alive():
            threads.pop(name, None)
    # clear current source if it disappeared
    clear_source_if_gone(present)

# ---- Graceful shutdown -------------------------------------------------------
def handle_sig(signum, frame):
    stop_event.set()
signal.signal(signal.SIGINT, handle_sig)
signal.signal(signal.SIGTERM, handle_sig)

# ---- Main --------------------------------------------------------------------
def main():
    global pcm
    _open_alsa()  # Open ALSA (with retries)

    while not stop_event.is_set():
        try:
            scan_and_spawn()
        except Exception as e:
            log(f"Main scan loop error: {e}")
        time.sleep(MIDI_SCAN_SEC)

    # cleanup
    try:
        if pcm:
            with alsa_lock:
                pcm.close()
    except Exception:
        pass
    log("Exiting.")

if __name__ == "__main__":
    main()
