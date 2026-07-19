---
name: comfyui-ltx-video
description: Generate AI video with synced audio via a local ComfyUI LTX-2.3 Director workflow.
version: 0.1.0
author: Hermes
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

Stdlib-only Python script — no pip dependencies required.

## When to Use

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
  minutes even on capable GPUs. `generate.py` only queues the job (it does
  not wait); use `check.py` afterward to see if it's done.

## How to Run

Two scripts, split so an LLM caller never blocks on a long render:

1. `generate.py` — fire-and-forget. Submits the workflow and returns
   immediately with a `prompt_id`.
2. `check.py <prompt_id>` — single lookup (no polling loop). Reports
   "still running" or downloads the finished video.

```bash
python '<path-to>\\skills\\comfyui-ltx-video\\scripts\\generate.py' "a cat closes its eyes and opens them again with shiny blue eyes, then yawns"
# -> queued: <prompt_id> (seed ...)

python '<path-to>\\skills\\comfyui-ltx-video\\scripts\\check.py' <prompt_id>
# -> status: still running (not yet in history)   [exit 1]
# -> <path to saved .mp4>                          [exit 0]
```

## Quick Reference

`generate.py`

| Flag | Default | Purpose |
|------|---------|---------|
| `--seed N` | random | Fixed seed for reproducibility |

`check.py`

| Flag | Default | Purpose |
|------|---------|---------|
| `--outdir DIR` | cwd | Save output video here |

Exit codes for `check.py`: `0` done (path on stdout), `1` still running,
`2` render failed.

Key node IDs in `workflow.json`:
- `131` — LTXDirector (prompt lives in `timeline_data.global_prompt`)
- `30` — RandomNoise (`noise_seed`)
- `37` — SaveVideo (output)

## Procedure

1. Take the user's video description as the prompt (`global_prompt`).
2. Queue the job:

   ```bash
   python '<path-to>\\skills\\comfyui-ltx-video\\scripts\\generate.py' "your prompt here"
   ```

3. Capture the `prompt_id` from the printed `queued: <prompt_id> (seed ...)`
   line. **Do not poll immediately in a loop.** Only call `check.py` when the
   user asks for the result, or after enough time has plausibly passed for
   the render to finish.
4. Run `check.py <prompt_id>`. If it exits 1 ("still running"), report that
   to the user rather than retrying repeatedly. If it exits 0, it printed the
   saved video path — audio is already muxed in, no separate audio step.
   Send the file to the user.

## Retrieving the Output Video

Always use `check.py` for retrieval — never rely on `generate.py`'s stdout,
since the render usually isn't done by the time it returns (it doesn't even
wait). `check.py` downloads via the `/view/` endpoint (NOT `/output/`,
which often 404s).

## Pitfalls

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
- If ComfyUI is on Windows host and Hermes runs in WSL2, `localhost` won't
  reach it — set `COMFYUI_URL` to the Windows host IP.
- **The `/output/` download path returns 404.** Always use `/view/` with
  `?filename=&subfolder=&type=` query parameters to download generated files.
- **Do not retry or spin up a new generation while one is processing.** The
  queue handles one prompt at a time — wait for the existing run to complete
  before submitting another.

## Verification

Run `generate.py` with a short prompt and check that stdout contains
`queued: <prompt_id> ...`:

```bash
python '<path-to>\\skills\\comfyui-ltx-video\\scripts\\generate.py' "test"
```

If the command exits with an error, verify ComfyUI is running and reachable.

After running `generate.py`, don't poll `check.py` in a loop or wait for the
result. Only call `check.py` if the user asks for it.