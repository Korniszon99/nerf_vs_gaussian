# Reproducible 3D vision experiment

**Status: planned. No benchmark results are reported by this document.**

The next milestone is one reproducible scene with a defensible evaluation, followed by one narrowly scoped change. The Django application orchestrates Nerfstudio; it does not implement a new NeRF or Gaussian splatting model.

## Freeze the baseline

1. Choose a dataset that can legally be redistributed or linked. Record its source, licence, scene identifier, image count and resolution. Do not publish employer imagery without permission.
2. Pin the repository commit, Nerfstudio version, dependency environment, GPU, VRAM, driver and CUDA details. Store the exact command and configuration, not only a screenshot of the UI.
3. Write explicit lists of training, validation and test views. Fix them before tuning. Document scene overlap and any camera-pose estimation that uses held-out images; an image excluded from gradient updates is not automatically independent of all preprocessing.
4. Keep image resolution and preprocessing comparable. Use a fixed compute budget and state whether it is wall-clock time or iterations. Equal iteration counts across different methods do not necessarily represent equal compute.

## Evaluate the same views

Report held-out PSNR and SSIM, and LPIPS when supported by a pinned implementation. Record colour range, resolution, masks, aggregation and any exclusions. Report time and peak GPU memory with the measurement method. Keep training-log values separate from held-out evaluation.

Save matched ground truth, rendered views and error maps. Include difficult cases rather than selecting only good reconstructions. With a single run, explicitly report the lack of repeated-run variability; do not imply statistical significance.

## One change at a time

After a working baseline, choose one hypothesis. For a Rust learning extension, investigate [Brush](https://github.com/ArthurBrussee/brush), pin an upstream commit and retain its licence and attribution. A possible experiment is a schedule for an existing loss weight, after checking the current implementation. This is a proposed experiment, not an implemented feature or an expected improvement.

Run the unchanged and modified versions on the same split and budget. Describe the change, explain the relevant gradients or data flow, add an appropriate test and publish the outcome even if quality or speed does not improve. Keep framework differences explicit when comparing Brush against Nerfstudio.

## Definition of a publishable result

- A completed [experiment record](experiment-template.md), configuration and reproducible commands.
- Dataset provenance, exact split lists and software/hardware versions.
- Real metrics with units and evaluation details; missing measurements remain marked as missing.
- Matched visual examples, known failure cases and a short explanation of limitations.
- A clear account of the author's change versus upstream library functionality.

Application CI mocks external training. It verifies application behaviour, not successful GPU training or reconstruction quality. A PLY point-cloud preview also does not demonstrate a working Gaussian splat renderer.
