---
name: comfyui-ltx-video
description: Generate AI video (with synced audio) via a local ComfyUI LTX-2.3 Director workflow
metadata:
  hermes:
    required_environment_variables:
      - name: COMFYUI_URL
        description: Base URL of the running ComfyUI server
        default: http://127.0.0.1:8188
---

# ComfyUI LTX-2.3 Director (video)

Generate a short video clip with synced audio from a single text prompt by
running a pre-built ComfyUI workflow (LTX-2.3 22B distilled, two-stage
Director + latent-upscale pipeline) through ComfyUI's HTTP API.

## When to use this skill

- The user asks to "generate", "make", or "render" a video/clip locally.
- The user references ComfyUI, LTX, LTX Director, or a local video model.

Do NOT use for image-only generation (see `comfyui-zimage`) or editing/retaking
existing footage.

## Prerequisites

- ComfyUI must be running and reachable at `COMFYUI_URL`
  (default `http://127.0.0.1:8188`). If Hermes runs in WSL2 and ComfyUI is
  on the Windows host, set `COMFYUI_URL` to the host IP, not `localhost`.
- The LTX Director custom node pack and all models named in `workflow.json`
  must be installed (`gemma_3_12B_it_fp4_mixed.safetensors`,
  `ltx-2.3_text_projection_bf16.safetensors`,
  `ltx-2.3-22b-distilled-1.1-Q3_K_M.gguf`,
  `ltx-2.3-spatial-upscaler-x2-1.1.safetensors`,
  `LTX23_video_vae_bf16.safetensors`, `LTX23_audio_vae_bf16.safetensors`,
  `taeltx2_3.safetensors`). If a model is missing, the script reports the
  node id and message ComfyUI's `/prompt` validation returns.
- This is a heavy two-stage 22B video+audio pipeline — a run can take several
  minutes even on capable GPUs. The script polls for up to 30 minutes by
  default (`--timeout` to change).

## Steps

1. Take the user's video description as the prompt (this becomes `global_prompt`).
2. Run the helper script bundled with this skill using the `terminal` tool:

   ```bash
   python '<path-to>\skills\comfyui-ltx-video\scripts\generate.py' "a cat closes its eyes and opens them again with shiny blue eyes, then yawns"
   ```

   Optional flags: `--seed N` (default random each run), `--outdir DIR`
   (default cwd), `--timeout SECONDS` (default 1800).

3. The script prints the saved video path to stdout — audio is already muxed
   into that file, there's no separate audio download step. Send the file to
   the user. Progress/seed info goes to stderr.

## Notes

- Only `global_prompt` is configurable right now. Everything else (clip
  length, resolution, per-segment prompts, motion/audio guide segments,
  retake mode) stays at the values baked into `workflow.json` — don't add
  flags for those without being asked.
- The prompt is NOT a plain node field. It lives inside node `131`
  (`LTXDirector`), nested as the `global_prompt` key of the JSON-encoded
  `timeline_data` string. The script decodes that JSON, sets `global_prompt`,
  and re-encodes it — do not look for a `CLIPTextEncode` node, there isn't
  one for the main prompt.
- Output comes from node `37` (`SaveVideo`), fed by `CreateVideo` (node `2`),
  which already combines the decoded frames with the decoded audio — one
  output file.
- Default clip length baked into the template is 120 frames @ 24 fps (5s).
