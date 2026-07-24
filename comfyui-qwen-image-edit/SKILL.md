---
name: comfyui-qwen-image-edit
description: Edit images via a local ComfyUI Qwen Image Edit workflow
metadata:
  hermes:
    required_environment_variables:
      - name: COMFYUI_URL
        description: Base URL of the running ComfyUI server
        default: http://127.0.0.1:8188
---

# ComfyUI Qwen Image Edit

Edit an existing image using the Qwen Image Edit 2511 model (lightning 4-step
or full 40-step pipeline) by running a pre-built ComfyUI workflow through
ComfyUI's HTTP API.

## When to use this skill

- The user wants to edit, modify, or transform an existing image.
- The user references Qwen Image Edit, image editing, or ComfyUI image editing.

Do NOT use for generating images from scratch (see `comfyui-zimage`) or video
generation (see `comfyui-ltx-video`).

## Prerequisites

- ComfyUI must be running and reachable at `COMFYUI_URL`
  (default `http://127.0.0.1:8188`). If Hermes runs in WSL2 and ComfyUI is
  on the Windows host, set `COMFYUI_URL` to the host IP, not `localhost`.
- The models named in `workflow.json` must be installed in ComfyUI:
  `qwen_image_edit_2511_fp8mixed.safetensors`,
  `qwen_2.5_vl_7b_fp8_scaled.safetensors`,
  `qwen_image_vae.safetensors`,
  `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors`.
  If a model is missing, the API returns a validation error.
- The FluxKontext custom node pack must be installed
  (`FluxKontextMultiReferenceLatentMethod`, `FluxKontextImageScale`).

## Steps

1. Take the user's input image path and edit prompt.
2. Run the helper script bundled with this skill using the `terminal` tool:

   ```bash
   python '<path-to>\skills\comfyui-qwen-image-edit\scripts\generate.py' /path/to/input.jpg "make the cat close its eyes"
   ```

   Optional flags: `--seed N` (default random each run),
   `--outdir DIR` (default cwd).

3. The script uploads the input image to ComfyUI, queues the workflow, waits
   for the result, and prints the saved output image path to stdout.

## Workflow Details

Key node IDs in `workflow.json`:

| Node ID       | Class                                  | Purpose                       |
|---------------|----------------------------------------|-----------------------------|
| `41`          | `LoadImage`                             | Input image (uploaded first) |
| `170:151`     | `TextEncodeQwenImageEditPlus`          | Positive prompt (edit desc)  |
| `170:149`     | `TextEncodeQwenImageEditPlus`          | Negative prompt (empty)       |
| `170:169`     | `KSampler`                              | Sampling (seed configurable) |
| `9`           | `SaveImage`                              | Output image                 |

## Notes

- The input image is uploaded to ComfyUI's `/upload/image/` endpoint before
  the workflow is submitted. The script uses the uploaded filename in the
  `LoadImage` node.
- The workflow supports both 4-step lightning and 40-step full mode via the
  `Enable 4steps LoRA?` toggle (node `170:168`). Default is 4-step mode.
- Only `SaveImage` node output (node `9`) is collected.
- The script blocks until the job finishes (up to 5 min timeout).

## Pitfalls

- The input image must be a real file path accessible from the Hermes
  environment. Remote URLs won't work directly — download first.
- If ComfyUI is on a Windows host and Hermes runs in WSL2, `localhost` won't
  reach it — set `COMFYUI_URL` to the Windows host IP.
- The image is uploaded to ComfyUI's `input/` directory before processing.
  If the filename already exists, ComfyUI may overwrite it.
- The `/view/` endpoint is used for download (NOT `/output/`, which often
  404s).
