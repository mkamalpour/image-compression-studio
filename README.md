# Image Compression Studio

**[Explore the interactive project presentation](docs/overview.html)** — open locally in your browser; works offline.

Try smaller palettes and JPEG settings, compare the image quality, and save the version you prefer. The desktop app includes an example image and an educational DCT/Huffman codec alongside standard image exports.

## Try it first

Use the built-in image first. Try **Use image-specific palette**, then **Compress & compare** to inspect the size and quality difference. Open your own image when ready and save the output separately from the original.

<details>
<summary>Using the existing managed Windows workspace</summary>

Assigned environment: **base**. From this repository folder in PowerShell:

```powershell
.\run.cmd --check
.\run.cmd
```

The repo-local launcher selects `G:\AnaConda\install`
and imports required startup modules. It installs nothing and downloads
no models. On a standalone clone where that interpreter is absent, it uses your
active `python`; activate a compatible environment first. `--check` reports the
actual interpreter; it does not validate optional models or every workflow.

</details>

## Start on Windows

1. Open a terminal and activate an existing compatible Python/Conda environment with NumPy, Pillow, and Tkinter.
2. Run **run.bat** from that activated terminal. The launcher uses your active environment; it creates no environments and installs nothing.
3. Use the built-in example, or **Open image**, then choose **Use image-specific palette** or **Compress & compare**.

Activate an existing environment with NumPy, Pillow, and Tkinter before launching. `run.bat --check` checks imports without opening the app. Processing stays local; the application does not upload images, modify originals, or automatically save results.

Manual setup:

```powershell
conda activate base  # Or use your existing compatible environment.
# Install dependencies if they are not already available in your environment.
python -m pip install -r requirements.txt
python -m media_studio
```

Verified baseline: CPython **3.11.0**, NumPy **2.4.4**, Pillow **12.2.0**, Tcl/Tk **8.6.12**, Windows. On Linux/macOS use `python`; Tkinter may need installation separately. Those platforms have not been verified. CLI processing does not import Tkinter. No SciPy, browser, web server, or external multimedia executable is required.

## Desktop workflows

| Tab | What you can do |
| --- | --- |
| Color palettes | Build image-specific or reusable shared palettes; choose adaptive or classic colors; use fast, exact, or reference mapping; inspect clickable swatches; save/load palette text. |
| JPEG compression | Save interoperable JPEGs with adjustable quality and 4:2:0/4:4:4 color sampling; alternatively run and reopen the educational MCS codec. |
| DCT explorer | Compare user-selected retained coefficient counts; inspect a block's spatial samples, DCT, quantization table, and zigzag order. |
| Compare images | Compare any two results or the original working image, use fit/100%/200% zoom, drag/scroll, and inspect amplified RGB differences. |
| Results & exports | Select a result, inspect its actual settings/stages/measurements, and export PNG, exact JPEG/MCS bytes, palette text, index arrays, JSON, or text reports as applicable. |
| Help | Read plain-language instructions, method trade-offs, limits, shortcuts, and import-transparency settings. |

Open multiple images through the source selector. Results belong to their source image and retain their settings: changing quality or palette controls does not relabel earlier results. Each tool's save/compare action uses that tool's result. Up to eight images and the newest sixteen results across them are retained; export anything you want to keep. Closing an image or clearing its results asks before discarding results.

Large photos are accepted up to **50 million source pixels** and **64 MiB** per file. For responsiveness, imports above **2 million pixels** become a labelled working copy, with JPEG draft decoding where available. Processing, previews, metrics and exports use that copy, not full-resolution source pixels. Reports record the import size and resizing. Originals stay unchanged. EXIF orientation is applied; transparency is flattened over white/black or explicitly ignored. Outputs drop source metadata. Animated/multi-page files are rejected. ICC color profiles are not transformed.

Jobs run in a separate process, with cancellation and a 120-second timeout. Switching/closing the source cancels the active job rather than attaching its result to another image. Exports require a new filename and refuse to overwrite existing files. Keyboard: Ctrl+O open, Escape cancel, F1 help.

## Algorithms and honest measurements

- **Adaptive palettes (default):** Pillow median cut. Shared palettes use thumbnails up to 65,536 pixels and at most 4,096 evenly spaced samples per dataset image, then median cut. This gives bounded work and more balanced image contributions; it is not an exact full-dataset histogram. Folders are nonrecursive, with at most 200 supported files. An unreadable image produces an explicit failure, rather than a silently partial palette.
- **Classic palettes:** exact most-frequent RGB colors, with deterministic RGB tie-breaking. Exact dataset mode accepts images up to 2 million pixels each and 60 million total pixels. High-resolution folders should use Adaptive. Frequency palettes are useful for comparison but do not guarantee minimum error or superior visual quality.
- **Fast mapping (default):** Pillow fixed-palette lookup without dithering. It uses approximate RGB lookup. Exact modes compare squared RGB distances in bounded NumPy batches; unique-color mode avoids repeated searches. Reference Python loops offer a small-image baseline, capped at 65,536 pixels. Exact methods agree on ties and avoid integer overflow.
- **Standard JPEG (default codec):** Pillow's native JPEG encoder. Preview and quality scores come from decoding the actual exported bytes. PNG exports preserve those decoded pixels without an additional lossy encode.
- **Educational MCS:** manual RGB/YCbCr conversion, optional 2x2 chroma averaging, edge padding, orthonormal 8x8 DCT using NumPy matrix operations, coefficient rounding, quality-scaled quantization, zigzag, DC differences, AC zero runs, canonical Huffman encoding, and the inverse pipeline. `.mcs` is a self-contained **custom format, not a standard JPEG**. Decoding uses only stream bytes. Its bounded JSON header and packed payload are integrity-checked with SHA-256; no external pickle or executable objects are loaded. This is an integrity check, not authentication.
- **DCT study:** retains the first k zigzag coefficients in every channel, without rounding, quantization or entropy coding. The transform is reused across counts. `64/k` is a coefficient-count ratio, **not a file compression ratio**. Displayed study times are cumulative, including shared transform preparation and earlier reconstructions.

MSE is average squared error over decoded RGB channels. PSNR is `10*log10(255²/MSE)`; identical pixels have infinite PSNR, represented as `null` in JSON. These are pixel-error measures, not perceptual-quality guarantees.

File ratios compare **raw 24-bit working RGB bytes** with **complete encoded file bytes**, including codec metadata. They do not indicate savings relative to an already-compressed source JPEG. Palette/index payload, actual PNG bytes, Huffman payload, and complete MCS bytes are reported separately. Tiny images or noise may grow. DCT reconstructions can be exported as PNG, whose size is distinct from coefficient retention.

## Command line

Use the environment's Python executable. Output folders must be new; existing folders/files are protected. Source and exported images remain local.

```text
python -m media_studio palette photo.jpg exports/palette --colors 64
python -m media_studio dataset my-images exports/shared --colors 256
python -m media_studio palette photo.jpg exports/mapped --palette exports/shared/palette.txt
python -m media_studio jpeg photo.jpg exports/jpeg --quality 85
python -m media_studio jpeg photo.jpg exports/mcs --quality 50 --educational
python -m media_studio decode exports/mcs/compression.mcs exports/decoded
python -m media_studio dct photo.jpg exports/dct --keep 4 7 8 16 64
python -m media_studio --help
```

Create the output parent folder first. Exit status: `0` success; `2` invalid arguments, inputs, setup, or file errors. CLI processing is synchronous; the desktop's process timeout/cancellation applies only to desktop jobs. Large imports use the same working-copy policy. Exact methods: `--strategy frequency`, `--mapping unique`, `--mapping direct`, or `--mapping reference`. Transparency: `--background white|black|ignore`.

Palette files contain `index R G B` columns, or three RGB columns, with 1–256 entries. Index-array exports are tab-separated rows. JSON/text reports summarize measurements and settings without embedding image pixels; review filenames and exported data before sharing.

## Project structure

```text
media_studio/
  __main__.py    desktop/CLI entry points and headless exports
  gui.py         multi-image, multi-tab workflows and result state
  widgets.py     image zoom/scroll previews and palette inspection
  images.py      bounded imports, working copies, demos, metrics, safe writes
  palettes.py    adaptive/classic palette creation and mapping
  transforms.py  color conversion, padding, DCT, sampling, quantization tables
  entropy.py     DC/AC events, canonical Huffman coding and packed bit I/O
  codec.py       standard JPEG adapter, MCS encoder/decoder, DCT experiments
  jobs.py        isolated, cancellable background processing
  __init__.py    package identity and version
tests/           numerical invariants, codec corruption, I/O, CLI and real UI checks
requirements.txt pinned runtime libraries
run.bat          Windows setup and launcher
```

The original assignment implementations and datasets are preserved outside this project. Their `.txt` source duplicates, PDFs, archives, generated files, and personal images are not copied into this repository. Built-in examples are generated in code. Documentation is text-only. No open-source license has been selected.

## Verification and limitations

Run `python -X utf8 -m unittest discover -s tests -v`. See `VERIFICATION.md` for actual checks, measurements, and remaining limits.

This is an image-compression workbench, not an audio/video editor. It has no batch export UI, perceptual-quality model, color-managed workflow, or full-resolution processing beyond the documented working-copy limit. The custom codec is educational and not intended to replace mature JPEG encoders. Bounded input and worker cancellation reduce resource risk; they do not provide an operating-system memory sandbox. Filesystem/image decoding errors can still occur and are reported.

Checked on Windows with Python 3.13.5 (Conda base): **43 tests passed** with the non-GUI suite and GUI workflows run in fresh activated processes. Repeated Tk interpreter creation in one batch remains intermittently unstable on this Windows runtime; this is not claimed fixed.

Worker setup failures release their queues, cancellation is repeatable, and invalid timeout or working-pixel budgets fail before allocating work.

See the [engineering audit](docs/ENGINEERING_AUDIT.md) for the dated test baseline,
project assessment, environment assignment and remaining work.
