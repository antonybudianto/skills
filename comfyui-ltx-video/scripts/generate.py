#!/usr/bin/env python3
"""
Queue the LTX-2.3 Director ComfyUI workflow (video + synced audio) via the
ComfyUI HTTP API. Fire-and-forget: submits the prompt and returns
immediately with a prompt_id. Use check.py to poll/retrieve the result.

Usage:
    python generate.py "your video prompt here" [--seed N]

Env:
    COMFYUI_URL   Base URL of the running ComfyUI server (default http://127.0.0.1:8188)

Prints "queued: <prompt_id> (seed <seed>)" to stdout on success.
Stdlib only.
"""
import argparse
import json
import os
import random
import sys
import urllib.request
import urllib.error

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_PATH = os.path.join(HERE, "workflow.json")

# Node IDs specific to this workflow (see workflow.json):
DIRECTOR_NODE = "131"  # LTXDirector -> inputs.timeline_data is a JSON *string*
                        # whose "global_prompt" key holds the actual prompt.
SEED_NODE = "30"       # RandomNoise -> inputs.noise_seed (drives both sampling stages)


def _post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{COMFYUI_URL}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
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
    print(f"queued: {prompt_id} (seed {seed})")


if __name__ == "__main__":
    main()
