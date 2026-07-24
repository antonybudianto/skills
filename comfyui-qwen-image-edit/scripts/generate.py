#!/usr/bin/env python3
"""
Run the Qwen Image Edit ComfyUI workflow via the ComfyUI HTTP API.

Usage:
    python generate.py INPUT_IMAGE "edit prompt" [--image2 SECOND_IMAGE] [--seed N]

Env:
    COMFYUI_URL   Base URL of the running ComfyUI server (default http://127.0.0.1:8188)

Prints the path to the saved image on success. Stdlib only.
"""
import argparse
import json
import mimetypes
import os
import random
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import io

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_PATH = os.path.join(HERE, "workflow.json")

# Node IDs specific to this workflow (see workflow.json):
POSITIVE_PROMPT_NODE = "170:151"   # TextEncodeQwenImageEditPlus (Positive) -> inputs.prompt
NEGATIVE_PROMPT_NODE = "170:149"   # TextEncodeQwenImageEditPlus (negative) -> inputs.prompt
SEED_NODE = "170:169"              # KSampler -> inputs.seed
LOAD_IMAGE_NODE = "41"             # LoadImage -> inputs.image (filename after upload)
LOAD_IMAGE2_NODE = "83"            # LoadImage (optional second image) -> inputs.image
IMAGE2_CONSUMER_NODES = ["170:149", "170:151"]  # nodes that reference image2
SAVE_NODE = "9"                     # SaveImage (where output filenames come back)


def _post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{COMFYUI_URL}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get(path):
    with urllib.request.urlopen(f"{COMFYUI_URL}{path}", timeout=30) as r:
        return json.loads(r.read())


def _upload_image(image_path):
    """Upload an image to ComfyUI's /upload/image endpoint.
    Returns the filename as ComfyUI stores it (basename)."""
    if not os.path.isfile(image_path):
        sys.exit(f"ERROR: input image not found: {image_path}")

    # Read the file
    with open(image_path, "rb") as f:
        file_data = f.read()

    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type is None:
        mime_type = "application/octet-stream"

    # Build multipart form data
    boundary = "----ComfyUIUploadBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{os.path.basename(image_path)}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode() + file_data + (
        f"\r\n--{boundary}--\r\n"
    ).encode()

    req = urllib.request.Request(
        f"{COMFYUI_URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    # ComfyUI upload endpoint uses POST
    with urllib.request.urlopen(req, timeout=30) as r:
        # Success returns 200/201 with JSON or empty body
        result = r.read()
        if result:
            try:
                resp = json.loads(result)
                # Some versions return {"name": "..."} or the filename
                if "name" in resp:
                    return resp["name"]
            except (json.JSONDecodeError, KeyError):
                pass

    return os.path.basename(image_path)


def main():
    ap = argparse.ArgumentParser(
        description="Edit an image using Qwen Image Edit via ComfyUI"
    )
    ap.add_argument("input_image", help="path to the input image file")
    ap.add_argument("prompt", help="text prompt describing the edit")
    ap.add_argument("--image2", default=None,
                    help="optional path to a second reference image")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--outdir", default=os.getcwd(),
                    help="where to save the downloaded result")
    args = ap.parse_args()

    # --- load workflow ---
    with open(WORKFLOW_PATH) as f:
        wf = json.load(f)

    # --- upload input image(s) to ComfyUI ---
    try:
        uploaded_name = _upload_image(args.input_image)
        uploaded_name2 = _upload_image(args.image2) if args.image2 else None
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: can't reach ComfyUI at {COMFYUI_URL} ({e}). "
                 f"Is it running? Set COMFYUI_URL if it's elsewhere.")
    except Exception as e:
        sys.exit(f"ERROR: failed to upload image: {e}")

    # --- override workflow inputs ---
    wf[POSITIVE_PROMPT_NODE]["inputs"]["prompt"] = args.prompt
    wf[NEGATIVE_PROMPT_NODE]["inputs"]["prompt"] = ""
    wf[LOAD_IMAGE_NODE]["inputs"]["image"] = uploaded_name
    wf[SEED_NODE]["inputs"]["seed"] = (
        args.seed if args.seed is not None
        else random.randint(0, 2**63 - 1)
    )

    # --- handle the optional second image ---
    if uploaded_name2:
        wf[LOAD_IMAGE2_NODE]["inputs"]["image"] = uploaded_name2
    else:
        # No second image: drop node 83 and the image2 references so ComfyUI
        # doesn't try to load the placeholder file baked into workflow.json.
        for node_id in IMAGE2_CONSUMER_NODES:
            wf.get(node_id, {}).get("inputs", {}).pop("image2", None)
        wf.pop(LOAD_IMAGE2_NODE, None)

    # --- queue the job ---
    try:
        resp = _post("/prompt", {"prompt": wf})
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit(f"ERROR: ComfyUI rejected the workflow ({e.code}):\n{body}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: can't reach ComfyUI at {COMFYUI_URL} ({e}). "
                 f"Is it running? Set COMFYUI_URL if it's elsewhere.")

    prompt_id = resp["prompt_id"]
    seed = wf[SEED_NODE]["inputs"]["seed"]
    imgs_desc = uploaded_name + (f" + {uploaded_name2}" if uploaded_name2 else "")
    print(f"queued: {prompt_id} (seed {seed}, image: {imgs_desc})", file=sys.stderr)

    # --- poll history until done ---
    for _ in range(600):  # ~5 min max
        try:
            hist = _get(f"/history/{prompt_id}")
        except urllib.error.URLError:
            time.sleep(0.5)
            continue
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
