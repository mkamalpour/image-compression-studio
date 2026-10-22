# Verification — 2026-10-22

Verified on Windows using the project's isolated environment: CPython **3.11.0**, NumPy **2.4.4**, Pillow **12.2.0**, Tcl/Tk **8.6.12**.

```text
.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
Ran 39 tests — OK, no skipped tests

.venv\Scripts\python -m pip check
No broken requirements found.

.venv\Scripts\python -m compileall -q media_studio tests
Completed successfully.

run.bat --check
Setup ready.
```

The launcher was also checked in a separate temporary directory with no pre-existing environment: it created the environment, installed the two pinned libraries, passed its setup check, and ran the CLI help entry point.

## Checks performed

- **Numerical/core:** independent scalar DCT formula versus matrix DCT; inverse and orthogonality; zigzag permutation; padding/cropping; tiny, odd and regular dimensions; odd-size chroma sampling; RGB/YCbCr round trip; MSE/PSNR formula; coefficient-retention reconstruction; quality validation.
- **Palettes:** exact aggregate frequencies and deterministic ties; exact mapping versus independent reference loops; overflow-sensitive colors; fast mapping produces valid palette indices; adaptive/classic options; reusable palette text; actual indexed-PNG round trip; invalid datasets and explicit failure on corrupt files; bounded adaptive processing of high-resolution sources.
- **Codecs:** signed amplitudes; DC differences; long zero runs and final nonzero AC coefficients; Huffman validation; packed-byte round trip; MCS decode using stream bytes alone; odd/tiny image reconstruction; checksum failure; truncated/modified streams; oversized dimensions and malformed metadata; actual metadata/payload/file-size accounting. Real JPEG exports decode to the exact pixels used for reported metrics.
- **Image/file safety:** PNG/JPEG/BMP/TIFF/WebP and grayscale imports; alpha handling; EXIF orientation; dropped source metadata; animated/multi-page rejection; working-copy resize limits; refusal to overwrite existing inputs or exports.
- **CLI/workers:** palette, dataset, shared palette, standard JPEG, MCS encode/decode, and DCT workflows; JSON outputs; invalid arguments; missing input; existing output protection; worker error reporting, hard timeout, and cancellation.
- **15 real Tk tests:** all six tabs; practical defaults; palette build/load/save/apply; JPEG/MCS export and reopen; DCT selection and block inspection; multiple source images; cancellation on source change; correct result ownership for tool-specific save actions; retained settings; zoom/difference pixels; all result export types; malformed controls; clear/close cancellation; high-resolution import/report; global retention limit; wrong-extension rejection; primary controls at 1000x760 with Windows DPI awareness.

The six UI tabs were captured locally and visually inspected at 1280x900, with additional checks at 1000x760 and Windows high DPI. The audit corrected clipped controls, result ownership, delayed redraws and pending Tk callbacks. Captures are kept outside the repository; documentation is text-only.

## Local data and performance checks

The original local 20-photo dataset was tested without publishing or modifying it. All 20 high-resolution images successfully imported as bounded working copies and completed adaptive palette and standard JPEG processing; the local combined run took about **13.9 seconds**. The adaptive shared-palette build accepted all 20 images, processed 1,306,603 thumbnail pixels and 81,920 sampled pixels, and took about **9.1 seconds** in a separate run. These are local observations, not universal timing guarantees.

On the generated 512x512 Color & detail example, median function-call times over three warm runs after one warm-up were:

| Workflow | Median |
| --- | ---: |
| Adaptive palette + fast mapping | 83.1 ms |
| Adaptive palette + exact unique-color mapping | 290.0 ms |
| Standard JPEG | 25.4 ms |
| Educational MCS encode/decode | 272.2 ms |
| DCT study, k=4/7/8/16 | 173.6 ms |

The palette mapping methods have different exactness guarantees. Measurements include result construction and in-memory export preparation, but exclude GUI/process startup, source import, and disk writes. They are comparisons within this implementation, not claims about measured speedups over every legacy version.

Original source, specifications, assets and datasets were backed up outside the project before building the combined version. The original folders were preserved. Only implementation, tests, launcher, dependency/Git settings and text documentation are intended for publication.

## Remaining limits

Only Windows/Python 3.11 was verified locally. No independent user study, color-management validation, SSIM/perceptual metric, video/audio processing, batch-export UI, or standard-JPEG encoder implemented from scratch is claimed. Practical JPEG encoding uses Pillow; the manual codec exports MCS rather than interoperable JPEG. Fast palette lookup is approximate and adaptive shared palettes are sampled. Large-source metrics and exports refer to the resized working image. The input limits/process timeout do not constitute an operating-system memory sandbox. An integrity checksum is not a signature. Filesystem or decoder failures remain possible and are surfaced to the user.
