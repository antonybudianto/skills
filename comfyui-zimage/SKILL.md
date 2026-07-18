---
name: comfyui-zimage
description: Generate images via a local ComfyUI z-image-turbo workflow
metadata:
  hermes:
    required_environment_variables:
      - name: COMFYUI_URL
        description: Base URL of the running ComfyUI server
        default: http://127.0.0.1:8188
---

# ComfyUI z-image-turbo

Generate an image from a text prompt by running a pre-built ComfyUI
workflow (`z_image_turbo`, 8-step, 1024x1024) through ComfyUI's HTTP API.

## When to use this skill

- The user asks to "generate", "make", or "render" an image locally.
- The user references ComfyUI, z-image, or a local image model.

Do NOT use for editing existing images or non-image tasks.

## Prerequisites

- ComfyUI must be running and reachable at `COMFYUI_URL`
  (default `http://127.0.0.1:8188`). If Hermes runs in WSL2 and ComfyUI is
  on the Windows host, set `COMFYUI_URL` to the host IP, not `localhost`.
- The models named in `workflow.json` must be installed in ComfyUI
  (`z_image_turbo_int8_convrot.safetensors`, `qwen_3_4b_fp8_mixed.safetensors`,
  `ae.safetensors`). If a model is missing the API returns a validation error.

## Steps

1. Take the user's image description as the prompt.
2. Run the helper script bundled with this skill using the `terminal` tool:

   ```bash
   python '<path-to>\skills\comfyui-zimage\scripts\generate.py' "generate a cat"
   ```

   Optional flags: `--seed N` (default random each run),
   `--width` / `--height` (default 1024), `--outdir DIR` (default cwd).

3. The script prints the saved image path to stdout. Send the file to the user.
   Progress/seed info goes to stderr.

## Notes

- Only `class_type: SaveImage` node output is collected (node `9`).
- cfg is 1 and negative prompt is zeroed out — this is a turbo/distilled model,
  so a negative prompt won't do much; don't add one.
- To change size, resolution should stay a multiple of 64.