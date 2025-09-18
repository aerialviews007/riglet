#!/usr/bin/env python3
import subprocess, time, re, sys

# Ignore common virtual/system endpoints
IGNORE = [r"Through", r"Virtual", r"System"]

def should_ignore(name: str) -> bool:
    return any(re.search(p, name, re.I) for p in IGNORE)

def parse_aconnect(flag: str):
    """
    flag: '-i' => readable inputs (sources)
          '-o' => writable outputs (destinations)
    returns list of ('client:port', 'Device Name')
    """
    out = subprocess.run(["aconnect", flag], capture_output=True, text=True).stdout
    results = []
    cur = None
    for line in out.splitlines():
        if line.startswith("client "):
            # e.g., "client 20: 'Device Name'"
            m = re.match(r"client\s+(\d+):\s+'([^']+)'", line)
            if m:
                cur = (m.group(1), m.group(2))  # (client_id, name)
        else:
            # Port line; robustly capture leading integer with or without colon
            m = re.match(r"^\s*(\d+)\s*:?", line)
            if m and cur:
                port = m.group(1)
                cid, name = cur
                if not should_ignore(name):
                    results.append((f"{cid}:{port}", name))
    return results

def connect(src: str, dst: str):
    # aconnect prints errors for invalid/duplicate pairs; silence them.
    subprocess.run(["aconnect", src, dst],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    seen = set()
    while True:
        try:
            sources = parse_aconnect("-i")   # readable (sources)
            sinks   = parse_aconnect("-o")   # writable (destinations)

            # --- Guard: if either side empty, skip this cycle ---
            if not sources or not sinks:
                time.sleep(2)
                continue

            current_pairs = set()
            for s_id, s_name in sources:
                s_client = s_id.split(":")[0]
                for d_id, d_name in sinks:
                    d_client = d_id.split(":")[0]
                    # avoid self-loop and ignored endpoints
                    if s_client == d_client:
                        continue
                    if should_ignore(s_name) or should_ignore(d_name):
                        continue
                    pair = (s_id, d_id)
                    current_pairs.add(pair)
                    if pair not in seen:
                        connect(*pair)

            # Prune cache to only pairs that still make sense
            seen = seen & current_pairs

        except Exception as e:
            print(f"[autopatch] warning: {e}", file=sys.stderr)

        time.sleep(2)

if __name__ == "__main__":
    main()
