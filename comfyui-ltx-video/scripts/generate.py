#!/usr/bin/env python3
"""
Run the LTX-2.3 Director ComfyUI workflow (video + synced audio) via the
ComfyUI HTTP API.

Usage:
    python generate.py "your video prompt here" [--seed N] [--outdir DIR]

Env:
    COMFYUI_URL   Base URL of the running ComfyUI server (default http://127.0.0.1:8188)

Prints the path to the saved video (audio is already muxed in) on success.
Stdlib only.
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_PATH = os.path.join(HERE, "workflow.json")

# Node IDs specific to this workflow (see workflow.json):
DIRECTOR_NODE = "131"  # LTXDirector -> inputs.timeline_data is a JSON *string*
                        # whose "global_prompt" key holds the actual prompt.
SEED_NODE = "30"       # RandomNoise -> inputs.noise_seed (drives both sampling stages)
SAVE_NODE = "37"       # SaveVideo   -> where the output filename comes back


def _post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{COMFYUI_URL}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get(path):
    with urllib.request.urlopen(f"{COMFYUI_URL}{path}", timeout=30) as r:
        return json.loads(r.read())


def _describe_validation_error(body_bytes):
    """ComfyUI returns 400 + {"error": {...}, "node_errors": {...}} when the
    workflow doesn't validate (most commonly: a model file isn't installed)."""
    try:
        body = json.loads(body_bytes)
    except ValueError:
        return body_bytes.decode(errors="replace")
    lines = [body.get("error", {}).get("message", "Prompt validation failed")]
    for node_id, info in body.get("node_errors", {}).items():
        for err in info.get("errors", []):
            lines.append(f"  node {node_id} ({info.get('class_type', '?')}): "
                         f"{err.get('message')} - {err.get('details', '')}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", help="video description; becomes the LTX Director global_prompt")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--outdir", default=os.getcwd(),
                    help="where to save the downloaded video")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="max seconds to wait for the render (default 1800s - "
                         "this is a slow two-stage 22B video+audio pipeline)")
    args = ap.parse_args()

    with open(WORKFLOW_PATH) as f:
        wf = json.load(f)

    # --- override inputs (global_prompt only) ---
    timeline = json.loads(wf[DIRECTOR_NODE]["inputs"]["timeline_data"])
    timeline["global_prompt"] = args.prompt
    wf[DIRECTOR_NODE]["inputs"]["timeline_data"] = json.dumps(timeline)

    seed = args.seed if args.seed is not None else random.randint(0, 2**63 - 1)
    wf[SEED_NODE]["inputs"]["noise_seed"] = seed

    # --- queue the job ---
    try:
        resp = _post("/prompt", {"prompt": wf})
    except urllib.error.HTTPError as e:
        detail = _describe_validation_error(e.read())
        sys.exit(f"ERROR: ComfyUI rejected the workflow ({e.code}):\n{detail}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: can't reach ComfyUI at {COMFYUI_URL} ({e}). "
                 f"Is it running? Set COMFYUI_URL if it's elsewhere.")
    prompt_id = resp["prompt_id"]
    print(f"queued: {prompt_id} (seed {seed})", file=sys.stderr)

    # --- poll history until done ---
    poll_interval = 2
    max_polls = max(1, args.timeout // poll_interval)
    hist = None
    for _ in range(max_polls):
        h = _get(f"/history/{prompt_id}")
        if prompt_id in h:
            hist = h[prompt_id]
            break
        time.sleep(poll_interval)
    else:
        sys.exit(f"ERROR: timed out after {args.timeout}s waiting for the render to finish.")

    status = hist.get("status", {})
    if status.get("status_str") == "error":
        for msg_type, data in status.get("messages", []):
            if msg_type == "execution_error":
                sys.exit(f"ERROR: node {data.get('node_id')} ({data.get('node_type')}) failed: "
                         f"{data.get('exception_message')}")
        sys.exit("ERROR: the render failed. Check the ComfyUI server log for details.")

    # SaveVideo reuses ComfyUI's generic "images" preview key for its UI output.
    outputs = hist.get("outputs", {})
    videos = outputs.get(SAVE_NODE, {}).get("images", [])
    if not videos:
        sys.exit("ERROR: job finished but no video came back from the SaveVideo node.")

    vid = videos[0]
    q = urllib.parse.urlencode({
        "filename": vid["filename"],
        "subfolder": vid.get("subfolder", ""),
        "type": vid.get("type", "output"),
    })
    os.makedirs(args.outdir, exist_ok=True)
    dest = os.path.join(args.outdir, vid["filename"])
    with urllib.request.urlopen(f"{COMFYUI_URL}/view?{q}", timeout=300) as r, \
            open(dest, "wb") as out:
        out.write(r.read())

    print(dest)  # stdout = the final video path


if __name__ == "__main__":
    main()
