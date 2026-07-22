#!/usr/bin/env python3
"""
Check the status of a queued LTX-2.3 Director job and download the video if
it's done. Does a SINGLE lookup against ComfyUI's history API — no polling
loop. Call this again later if the job is still running.

Usage:
    python check.py <prompt_id> [--outdir DIR]

Env:
    COMFYUI_URL   Base URL of the running ComfyUI server (default http://127.0.0.1:8188)

Exit codes:
    0  done -> prints the saved video path to stdout
    1  still running / not yet in history -> prints a status message, no output file
    2  the render failed, or another error occurred
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
SAVE_NODE = "37"  # SaveVideo -> where the output filename comes back

# --- non-localhost warning (shared concern with generate.py) ---
_parsed = urllib.parse.urlparse(COMFYUI_URL)
if (_parsed.hostname or "").lower() not in ("localhost", "127.0.0.1", "::1", ""):
    print(
        f"WARN: COMFYUI_URL ({COMFYUI_URL}) is not localhost. "
        f"Job history will be fetched from that server.",
        file=sys.stderr,
    )


def _sanitize_filename(raw: str, outdir: str) -> str:
    """Reject filenames with path traversal or directory separators.
    Only allow the basename (no slashes, backslashes, or '..' components)."""
    # Strip to bare name — reject anything with directory separators
    name = os.path.basename(raw)
    if not name or name.startswith((".", "/")):
        raise ValueError(f"Invalid filename from server: {raw!r}")
    # Resolve and verify the destination stays inside outdir
    resolved = os.path.realpath(os.path.join(os.path.realpath(outdir), name))
    if not resolved.startswith(os.path.realpath(outdir) + os.sep) and resolved != os.path.realpath(outdir):
        raise ValueError(f"Filename escapes output directory: {raw!r}")
    return name


def _get(path):
    with urllib.request.urlopen(f"{COMFYUI_URL}{path}", timeout=30) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt_id")
    ap.add_argument("--outdir", default=os.getcwd(),
                    help="where to save the downloaded video")
    args = ap.parse_args()

    try:
        h = _get(f"/history/{args.prompt_id}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: can't reach ComfyUI at {COMFYUI_URL} ({e}). "
                 f"Is it running? Set COMFYUI_URL if it's elsewhere.")

    if args.prompt_id not in h:
        print("status: still running (not yet in history)")
        sys.exit(1)

    hist = h[args.prompt_id]
    status = hist.get("status", {})
    if status.get("status_str") == "error":
        for msg_type, data in status.get("messages", []):
            if msg_type == "execution_error":
                print(f"ERROR: node {data.get('node_id')} ({data.get('node_type')}) failed: "
                     f"{data.get('exception_message')}", file=sys.stderr)
                sys.exit(2)
        print("ERROR: the render failed. Check the ComfyUI server log for details.",
             file=sys.stderr)
        sys.exit(2)

    # SaveVideo reuses ComfyUI's generic "images" preview key for its UI output.
    outputs = hist.get("outputs", {})
    videos = outputs.get(SAVE_NODE, {}).get("images", [])
    if not videos:
        print("status: still running (in history but no output yet)")
        sys.exit(1)

    vid = videos[0]
    q = urllib.parse.urlencode({
        "filename": vid["filename"],
        "subfolder": vid.get("subfolder", ""),
        "type": vid.get("type", "output"),
    })
    os.makedirs(args.outdir, exist_ok=True)
    safe_name = _sanitize_filename(vid["filename"], args.outdir)
    dest = os.path.join(args.outdir, safe_name)
    with urllib.request.urlopen(f"{COMFYUI_URL}/view?{q}", timeout=300) as r, \
            open(dest, "wb") as out:
        out.write(r.read())

    print(dest)  # stdout = the final video path


if __name__ == "__main__":
    main()
