#!/usr/bin/env python3
"""
Riglet: MIDI Autopatch (generic, robust)

- Auto-connects every real MIDI input to every real MIDI output.
- Ignores 'Through', 'Virtual', etc.
- Hot-plug safe (polls ALSA aconnect).
- Avoids duplicate connections by reading existing links correctly.
"""

import time, re, sys, subprocess
from typing import Set, Tuple, Dict

SCAN_SEC = 1.0
IGNORE_PATTERNS = [r'RtMidi', r'Through', r'Virtual', r'System', r'Announce', r'Midi Through']

def log(*a): 
    print("[midi-autopatch]", *a, file=sys.stderr, flush=True)

def should_ignore(name: str) -> bool:
    return any(re.search(p, name, re.I) for p in IGNORE_PATTERNS)

def list_ports() -> Tuple[Set[str], Set[str]]:
    """Return sets of ALSA client:port ids (e.g., '20:0') for inputs and outputs that aren't ignored."""
    try:
        ins_txt  = subprocess.check_output(["aconnect", "-i"], text=True)
        outs_txt = subprocess.check_output(["aconnect", "-o"], text=True)
    except Exception as e:
        log("aconnect query failed:", e)
        return set(), set()

    def parse(text: str) -> Dict[str,str]:
        mapping: Dict[str,str] = {}
        cur_client = None
        for line in text.splitlines():
            m = re.match(r"client\s+(\d+):\s+'([^']+)'", line)
            if m:
                cur_client = (m.group(1), m.group(2))
                continue
            m = re.match(r"\s*(\d+)\s+'([^']+)'", line)
            if m and cur_client:
                port, pname = m.group(1), m.group(2)
                cid = f"{cur_client[0]}:{port}"
                mapping[cid] = f"{cid} {cur_client[1]} {pname}"
        return mapping

    in_map  = parse(ins_txt)
    out_map = parse(outs_txt)

    ins  = {k for k,v in in_map.items()  if not should_ignore(v)}
    outs = {k for k,v in out_map.items() if not should_ignore(v)}
    return ins, outs

def existing_connections() -> Set[Tuple[str,str]]:
    """Return set of (src_id, dst_id) like ('20:0','24:0')."""
    try:
        txt = subprocess.check_output(["aconnect", "-l"], text=True)
    except Exception:
        return set()
    pairs: Set[Tuple[str,str]] = set()
    cur_client = None
    cur_src = None
    for line in txt.splitlines():
        m = re.match(r"client\s+(\d+):\s+'([^']+)'", line)
        if m:
            cur_client = m.group(1)
            cur_src = None
            continue
        m = re.match(r"\s*(\d+)\s+'([^']+)'", line)
        if m and cur_client is not None:
            cur_src = f"{cur_client}:{m.group(1)}"
            continue
        if "Connecting To:" in line and cur_src:
            for mm in re.finditer(r"(\d+):(\d+)", line):
                dst = f"{mm.group(1)}:{mm.group(2)}"
                pairs.add((cur_src, dst))
    return pairs

def connect(src: str, dst: str) -> bool:
    try:
        subprocess.check_call(["aconnect", src, dst])
        log("connected:", src, "->", dst)
        return True
    except subprocess.CalledProcessError:
        return False  # already connected or transient error

def main():
    log("starting…")
    known: Set[Tuple[str,str]] = set()
    while True:
        ins, outs = list_ports()
        if not ins and not outs:
            time.sleep(SCAN_SEC); continue

        current = existing_connections()
        known |= current
        made = 0
        for s in sorted(ins):
            for d in sorted(outs):
                if s == d: continue
                if (s,d) in known or (s,d) in current: continue
                if connect(s,d):
                    known.add((s,d)); made += 1
        if made:
            log(f"patched {made} new link(s). inputs={len(ins)} outputs={len(outs)} total_links={len(known)}")
        time.sleep(SCAN_SEC)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("exiting.")
