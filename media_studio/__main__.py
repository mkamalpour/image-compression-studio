"""Desktop entry point and a small headless command interface."""

import argparse
from pathlib import Path
import sys


def parser():
    p = argparse.ArgumentParser(description="Image Compression Studio: palettes, JPEG, and DCT experiments. No arguments opens the desktop app.")
    sub = p.add_subparsers(dest="command")
    for name in ("palette", "jpeg", "dct", "decode", "dataset"):
        cmd = sub.add_parser(name)
        cmd.add_argument("input", help="Input image, dataset folder, or MCS stream")
        cmd.add_argument("output", help="New output folder; must not already exist")
        if name in {"palette", "dataset"}:
            cmd.add_argument("--colors", type=int, default=256)
            cmd.add_argument("--strategy", choices=("adaptive", "frequency"), default="adaptive")
        if name == "palette":
            cmd.add_argument("--mapping", choices=("fast", "unique", "direct", "reference"), default="fast")
            cmd.add_argument("--palette", help="Use a saved shared palette instead of building one")
        if name == "jpeg":
            cmd.add_argument("--quality", type=int, default=80)
            cmd.add_argument("--educational", action="store_true", help="Use educational MCS instead of standard JPEG")
            cmd.add_argument("--no-subsampling", action="store_true")
        if name == "dct":
            cmd.add_argument("--keep", type=int, nargs="+", default=[4, 7, 8, 16])
        if name in {"palette", "jpeg", "dct", "dataset"}:
            cmd.add_argument("--background", choices=("white", "black", "ignore"), default="white")
    return p


def run_cli(args):
    from .images import read_image, png_bytes, json_bytes, write_new, MAX_FILE_BYTES
    from .palettes import quantize, dataset_palette, read_palette, palette_text
    from .codec import compress, standard_jpeg, decode, coefficient_study
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError("Choose a new output folder; existing files are protected.")
    if not destination.parent.is_dir():
        raise ValueError("The output parent folder does not exist.")
    if args.command == "dataset":
        result = dataset_palette(args.input, args.colors, args.background, args.strategy)
        files = {"palette.txt": palette_text(result.pop("palette")).encode("utf-8"), "report.json": json_bytes(result)}
    elif args.command == "decode":
        path = Path(args.input)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Stream exceeds 64 MiB.")
        files = {"decoded.png": png_bytes(decode(path.read_bytes()))}
    else:
        imported = read_image(args.input, args.background)
        rgb = imported.pop("rgb")
        if args.command == "palette":
            result = quantize(rgb, args.colors, read_palette(args.palette) if args.palette else None, args.mapping, args.strategy)
            results = [("palette", result)]
        elif args.command == "jpeg":
            function = compress if args.educational else standard_jpeg
            results = [("compression", function(rgb, args.quality, not args.no_subsampling))]
        else:
            results = [(f"dct-{r['settings']['kept_coefficients']}", r) for r in coefficient_study(rgb, args.keep)]
        files = {}
        reports = []
        for name, result in results:
            files[name+".png"] = result["png"]
            for key, extension in [("jpeg", ".jpg"), ("stream", ".mcs")]:
                if key in result:
                    files[name+extension] = result[key]
            if "palette" in result:
                from io import StringIO
                import numpy as np
                out = StringIO()
                np.savetxt(out, result["indices"], fmt="%d", delimiter="\t")
                files["palette.txt"] = palette_text(result["palette"]).encode("utf-8")
                files["indices.txt"] = out.getvalue().encode("utf-8")
            reports.append({"result": name, "settings": result["settings"], "metrics": result["metrics"], "statistics": result["stats"], "steps": result["steps"]})
        files["report.json"] = json_bytes({"application": "Image Compression Studio", "import": imported, "working_size": [rgb.shape[1],rgb.shape[0]], "results": reports,
                                           "notes": ["Processing and metrics use the imported working image, resized for sources over 2 million pixels.", "PSNR null means identical pixels.", "Ratios compare raw RGB with full encoded files; coefficient ratios are not file compression."]})
    destination.mkdir()  # Exclusive creation protects prior output and the input folder.
    created = []
    try:
        for name, data in files.items():
            write_new(destination / name, data)
            created.append(name)
    except BaseException:
        # Only remove files created by this invocation; preserve anything added externally.
        for name in created:
            target = destination / name
            if target.is_file():
                target.unlink()
        try:
            destination.rmdir()
        except OSError:
            pass
        raise
    print(f"Saved {len(files)} files to {destination}")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command is None:
            from .gui import launch
            launch()
        else:
            run_cli(args)
        return 0
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"Image Compression Studio: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
