#!/usr/bin/env python3
"""
Run the z-image-turbo ComfyUI workflow via the ComfyUI HTTP API.

Usage:
    python generate.py "your prompt here" [--seed N] [--width 1024] [--height 1024]

Env:
    COMFYUI_URL   Base URL of the running ComfyUI server (default http://127.0.0.1:8188)

Prints the path to the saved image on success. Stdlib only.
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
PROMPT_NODE = "57:27"   # CLIPTextEncode -> inputs.text
SEED_NODE = "57:3"      # KSampler       -> inputs.seed
SIZE_NODE = "57:13"     # EmptySD3Latent -> inputs.width / height
SAVE_NODE = "9"         # SaveImage (where output filenames come back)


def _post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{COMFYUI_URL}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get(path):
    with urllib.request.urlopen(f"{COMFYUI_URL}{path}", timeout=30) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", help="text prompt for the image")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--outdir", default=os.getcwd(),
                    help="where to save the downloaded image")
    args = ap.parse_args()

    with open(WORKFLOW_PATH) as f:
        wf = json.load(f)

    # --- override inputs ---
    wf[PROMPT_NODE]["inputs"]["text"] = args.prompt
    wf[SEED_NODE]["inputs"]["seed"] = args.seed if args.seed is not None \
        else random.randint(0, 2**63 - 1)
    if args.width:
        wf[SIZE_NODE]["inputs"]["width"] = args.width
    if args.height:
        wf[SIZE_NODE]["inputs"]["height"] = args.height

    # --- queue the job ---
    try:
        resp = _post("/prompt", {"prompt": wf})
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: can't reach ComfyUI at {COMFYUI_URL} ({e}). "
                 f"Is it running? Set COMFYUI_URL if it's elsewhere.")
    prompt_id = resp["prompt_id"]
    print(f"queued: {prompt_id} (seed {wf[SEED_NODE]['inputs']['seed']})", file=sys.stderr)

    # --- poll history until done ---
    for _ in range(600):  # ~5 min max
        hist = _get(f"/history/{prompt_id}")
        if prompt_id in hist:
            break
        time.sleep(0.5)
    else:
        sys.exit("ERROR: timed out waiting for the job to finish.")

    outputs = hist[prompt_id]["outputs"]
    images = outputs.get(SAVE_NODE, {}).get("images", [])
    if not images:
        sys.exit("ERROR: job finished but no image came back from the SaveImage node.")

    img = images[0]
    q = urllib.parse.urlencode({
        "filename": img["filename"],
        "subfolder": img.get("subfolder", ""),
        "type": img.get("type", "output"),
    })
    os.makedirs(args.outdir, exist_ok=True)
    dest = os.path.join(args.outdir, img["filename"])
    with urllib.request.urlopen(f"{COMFYUI_URL}/view?{q}", timeout=60) as r, \
            open(dest, "wb") as out:
        out.write(r.read())

    print(dest)  # stdout = the final image path


if __name__ == "__main__":
    main()