"""Native desktop workbench: practical defaults, inspectable advanced experiments."""

from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

import numpy as np

from .images import demo_image, metric_text, write_new, json_bytes
from .palettes import read_palette, palette_text
from .transforms import block_details, quant_tables, ZIGZAG
from .jobs import Job
from .widgets import ImageView, PaletteView

BG, INK, BLUE = "#f3f5fa", "#19283e", "#255bcb"
METHODS = {"Fast (recommended)": "fast", "Exact, unique colors": "unique", "Exact, all pixels": "direct", "Reference loops (small images)": "reference"}
STRATEGIES = {"Adaptive (recommended)": "adaptive", "Most frequent RGB (classic)": "frequency"}


class Studio:
    def __init__(self, root):
        self.root = root
        root.title("Image Compression Studio")
        root.geometry("1280x900")
        root.minsize(1000, 760)
        self.sessions = []
        self.session = None
        self.serial = 0
        self.result_serial = 0
        self.active_result = None
        self.shared_palette = None
        self.shared_info = None
        self.job = None
        self.after_id = None
        self.callback = None
        self.photo_pairs = []
        self.run_buttons = []
        self.status = tk.StringVar(value="Open an image or try an example. Your original files are never modified.")
        self.notice = tk.StringVar(value="Reduce colors, save JPEGs, and explore how compression works.")
        self._style()
        self._build()
        self.add_image(demo_image(), "Example: color & detail")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-o>", lambda e: self.open_image())
        root.bind("<Escape>", lambda e: self.cancel())
        root.bind("<F1>", lambda e: self.tabs.select(self.help_tab))

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=BG, foreground=INK)
        style.configure("TButton", padding=(8, 6))
        style.configure("Accent.TButton", background=BLUE, foreground="white")
        style.map("Accent.TButton", background=[("active", "#17469e"), ("disabled", "#91a4bd")])
        style.configure("TNotebook.Tab", padding=(13, 8))
        style.map("TNotebook.Tab", foreground=[("selected", BLUE)], background=[("selected", "white")])
        style.configure("Treeview", background="white", fieldbackground="white", rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Muted.TLabel", foreground="#526680")

    def _build(self):
        header = tk.Frame(self.root, bg="#15273e", padx=16, pady=8)
        header.pack(fill="x")
        tk.Label(header, text="Image Compression Studio", font=("Segoe UI", 18, "bold"), bg="#15273e", fg="white").pack(side="left")
        top = ttk.Frame(self.root, padding=(12, 8))
        top.pack(fill="x")
        ttk.Button(top, text="Open image  Ctrl+O", command=self.open_image, style="Accent.TButton").pack(side="left")
        self.source_name = tk.StringVar()
        self.sources = ttk.Combobox(top, textvariable=self.source_name, state="readonly", width=24)
        self.sources.pack(side="left", padx=8)
        self.sources.bind("<<ComboboxSelected>>", self.switch_image)
        ttk.Button(top, text="Close image", command=self.remove_image).pack(side="left")
        self.example = tk.StringVar(value="Color & detail")
        ttk.Combobox(top, textvariable=self.example, values=("Color & detail", "Gradients", "Geometric shapes"), state="readonly", width=18).pack(side="left", padx=(15, 5))
        ttk.Button(top, text="Try example", command=lambda: self.add_image(demo_image(self.example.get()), "Example: "+self.example.get())).pack(side="left")
        self.cancel_button = ttk.Button(top, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="right")
        ttk.Label(self.root, textvariable=self.notice, padding=(14, 5), style="Muted.TLabel", wraplength=950).pack(fill="x")
        footer = ttk.Frame(self.root, padding=(12, 6))
        footer.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(footer, length=150, maximum=100)
        self.progress.pack(side="right", padx=(8, 0))
        ttk.Label(footer, textvariable=self.status, wraplength=800).pack(side="left", fill="x", expand=True)
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        self.palette_tab, self.jpeg_tab, self.dct_tab, self.compare_tab, self.results_tab, self.help_tab = [ttk.Frame(self.tabs, padding=10) for _ in range(6)]
        for frame, title in [(self.palette_tab, "Color palettes"), (self.jpeg_tab, "JPEG compression"), (self.dct_tab, "DCT explorer"), (self.compare_tab, "Compare images"), (self.results_tab, "Results & exports"), (self.help_tab, "Help")]:
            self.tabs.add(frame, text=title)
        self._palette_tab()
        self._jpeg_tab()
        self._dct_tab()
        self._compare_tab()
        self._results_tab()
        self._help_tab()
        self.tabs.bind("<<NotebookTabChanged>>", self.tab_changed)

    def button(self, parent, text, command, accent=False):
        button = ttk.Button(parent, text=text, command=command, style="Accent.TButton" if accent else "TButton")
        button.pack(fill="x", pady=3)
        self.run_buttons.append(button)
        return button

    @staticmethod
    def choice(parent, label, values, default):
        ttk.Label(parent, text=label, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
        variable = tk.StringVar(value=default)
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=25).pack(fill="x")
        return variable

    def workspace(self, tab):
        left = ttk.Frame(tab, width=260, padding=(0, 0, 12, 0))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        right = ttk.Frame(tab)
        right.pack(side="left", fill="both", expand=True)
        return left, right

    def previews(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1, uniform="views")
        frame.columnconfigure(1, weight=1, uniform="views")
        frame.rowconfigure(0, weight=1)
        a, b = ImageView(frame, "Original"), ImageView(frame, "Result")
        a.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        b.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.photo_pairs.append((a, b))
        return a, b

    def _palette_tab(self):
        left, right = self.workspace(self.palette_tab)
        ttk.Label(left, text="Reduce image colors", font=("Segoe UI", 11, "bold"), wraplength=240).pack(anchor="w")
        self.colors = self.choice(left, "Palette size", (16, 32, 64, 128, 256), "256")
        self.strategy = self.choice(left, "Choose colors", tuple(STRATEGIES), next(iter(STRATEGIES)))
        self.mapping = self.choice(left, "Map pixels", tuple(METHODS), next(iter(METHODS)))
        self.button(left, "Use image-specific palette", self.run_selected, True)
        ttk.Separator(left).pack(fill="x", pady=8)
        ttk.Label(left, text="Shared palette", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.button(left, "Build from image folder...", self.build_dataset)
        self.button(left, "Build from built-in examples", self.build_demo_palette)
        row = ttk.Frame(left)
        row.pack(fill="x")
        ttk.Button(row, text="Load palette...", command=self.load_palette).pack(side="left")
        ttk.Button(row, text="Save...", command=lambda: self.export("shared_palette")).pack(side="right")
        self.shared_note = tk.StringVar(value="Build or load a shared palette first.")
        ttk.Label(right, textvariable=self.shared_note, wraplength=850, style="Muted.TLabel").pack(fill="x", pady=(0, 4))
        self.button(left, "Apply shared palette", self.run_shared)
        self.palette_metric = tk.StringVar(value="Choose either method to see the result and measured quality.")
        ttk.Label(right, textvariable=self.palette_metric, wraplength=850).pack(fill="x", pady=(0, 8))
        self.palette_original, self.palette_output = self.previews(right)
        self.swatches = PaletteView(right)
        self.swatches.pack(fill="x", pady=(8, 0))
        self._result_actions(right, "palette")

    def _jpeg_tab(self):
        left, right = self.workspace(self.jpeg_tab)
        ttk.Label(left, text="Save a real JPEG", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.jpeg_mode = self.choice(left, "Codec", ("Standard JPEG (recommended)", "Educational JPEG-style (MCS)"), "Standard JPEG (recommended)")
        ttk.Label(left, text="Quality: higher keeps more detail", font=("Segoe UI", 10, "bold"), wraplength=240).pack(anchor="w", pady=(12, 3))
        self.quality = tk.DoubleVar(value=80)
        self.quality_label = tk.StringVar(value="80 / 100")
        ttk.Scale(left, from_=1, to=100, variable=self.quality, command=lambda v: self.quality_label.set(f"{round(float(v))} / 100")).pack(fill="x")
        ttk.Label(left, textvariable=self.quality_label).pack(anchor="w")
        self.sampling = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Smaller color detail (4:2:0)", variable=self.sampling).pack(anchor="w", pady=8)
        self.button(left, "Compress & compare", self.run_jpeg, True)
        self.button(left, "Open .mcs stream...", self.open_stream)
        ttk.Label(left, text="Standard JPEG creates a file other apps can open. MCS exposes our DCT, quantization, zigzag, DC differences, AC runs and Huffman codec. MCS is not a JPEG file.", wraplength=235, style="Muted.TLabel").pack(anchor="w", pady=12)
        self.jpeg_metric = tk.StringVar(value="The preview is decoded from the actual encoded bytes.")
        ttk.Label(right, textvariable=self.jpeg_metric, wraplength=850).pack(fill="x", pady=(0, 8))
        self.jpeg_original, self.jpeg_output = self.previews(right)
        self._result_actions(right, "jpeg")

    def _dct_tab(self):
        left, right = self.workspace(self.dct_tab)
        ttk.Label(left, text="How much detail matters?", font=("Segoe UI", 12, "bold"), wraplength=240).pack(anchor="w")
        ttk.Label(left, text="Keep the first k frequency coefficients in each 8x8 block. No quantization or entropy coding here.", wraplength=235).pack(anchor="w", pady=8)
        self.keep = tk.StringVar(value="4, 7, 8, 16")
        ttk.Label(left, text="Coefficient counts (1 to 64)").pack(anchor="w")
        ttk.Entry(left, textvariable=self.keep).pack(fill="x", pady=5)
        self.button(left, "Compare coefficient counts", self.run_dct, True)
        ttk.Label(left, text="Inspect a luminance block", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(15, 5))
        coordinates = ttk.Frame(left)
        coordinates.pack(fill="x")
        self.block_x, self.block_y = tk.StringVar(value="0"), tk.StringVar(value="0")
        for label, variable in [("X", self.block_x), ("Y", self.block_y)]:
            ttk.Label(coordinates, text=label).pack(side="left", padx=3)
            ttk.Entry(coordinates, textvariable=variable, width=5).pack(side="left")
        self.button(left, "Inspect block & quantization", self.inspect_block)
        ttk.Label(left, text="Select a row to view its reconstruction. 64/k is a coefficient-count ratio, not file compression. All result images can be compared and exported.", wraplength=235, style="Muted.TLabel").pack(anchor="w", pady=10)
        self.dct_table = self.table(right, ("k", "psnr", "mse", "kept"), ("Kept / 64", "PSNR (dB)", "MSE", "Coefficients kept"), height=5)
        self.dct_table.bind("<<TreeviewSelect>>", self.select_dct)
        self.dct_original, self.dct_output = self.previews(right)
        self._result_actions(right, "dct")

    def _result_actions(self, parent, family):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(7, 0))
        ttk.Button(bar, text="Save result...", command=lambda: self.family_action(family, "save")).pack(side="left")
        ttk.Button(bar, text="Compare / zoom", command=lambda: self.family_action(family, "compare")).pack(side="left", padx=5)
        ttk.Button(bar, text="Details & all exports", command=lambda: self.family_action(family, "details")).pack(side="right")

    def family_result(self, family):
        results = self.session["results"] if self.session else {}
        current = results.get(self.active_result)
        if current and current["family"] == family:
            return self.active_result
        return next((name for name in reversed(results) if results[name]["family"] == family), None)

    def family_action(self, family, action):
        name = self.family_result(family)
        if name is None:
            self.error("Run this tool first to create a result.")
            return
        self.display_result(name)
        if action == "save":
            self.export("image")
        elif action == "compare":
            self.show_comparison()
        else:
            self.tabs.select(self.results_tab)

    def tab_changed(self, event=None):
        families = {str(self.palette_tab): "palette", str(self.jpeg_tab): "jpeg", str(self.dct_tab): "dct"}
        family = families.get(self.tabs.select())
        if family:
            name = self.family_result(family)
            if name:
                self.display_result(name)

    def _compare_tab(self):
        bar = ttk.Frame(self.compare_tab)
        bar.pack(fill="x", pady=(0, 8))
        self.compare_left, self.compare_right = tk.StringVar(value="Original"), tk.StringVar(value="Original")
        self.left_choice = ttk.Combobox(bar, textvariable=self.compare_left, state="readonly", width=28)
        self.right_choice = ttk.Combobox(bar, textvariable=self.compare_right, state="readonly", width=28)
        for widget in [self.left_choice, self.right_choice]:
            widget.pack(side="left", padx=(0, 8))
            widget.bind("<<ComboboxSelected>>", lambda e: self.refresh_comparison())
        self.zoom = tk.StringVar(value="Fit")
        zoom = ttk.Combobox(bar, textvariable=self.zoom, values=("Fit", "100%", "200%"), state="readonly", width=7)
        zoom.pack(side="left")
        zoom.bind("<<ComboboxSelected>>", lambda e: self.refresh_comparison())
        self.difference = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Difference x4", variable=self.difference, command=self.refresh_comparison).pack(side="left", padx=8)
        self.compare_metric = tk.StringVar(value="Choose two images. At pixel zoom, scroll or drag to inspect detail.")
        ttk.Label(self.compare_tab, textvariable=self.compare_metric, wraplength=1000).pack(fill="x", pady=(0, 8))
        self.compare_a, self.compare_b = self.previews(self.compare_tab)

    @staticmethod
    def table(parent, columns, labels, height=8):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 8))
        table = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
        for key, label in zip(columns, labels):
            table.heading(key, text=label)
            table.column(key, width=110, minwidth=65)
        table.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frame, command=table.yview)
        scrollbar.pack(side="right", fill="y")
        table.configure(yscrollcommand=scrollbar.set)
        return table

    def _results_tab(self):
        ttk.Label(self.results_tab, text="Results for the selected source image", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Label(self.results_tab, text="Select a result to inspect or export. Settings stay with it; the newest 16 results are kept.", style="Muted.TLabel", wraplength=900).pack(anchor="w", pady=(0, 8))
        self.result_table = self.table(self.results_tab, ("name", "psnr", "mse", "bytes", "time"), ("Result / settings", "PSNR (dB)", "MSE", "File bytes", "Time (ms)"), height=6)
        self.result_table.column("name", width=330)
        self.result_table.bind("<<TreeviewSelect>>", self.select_result)
        actions = ttk.Frame(self.results_tab)
        actions.pack(fill="x", pady=4)
        self.export_buttons = {}
        for kind, title in [("image", "PNG image"), ("encoded", "JPEG / MCS file"), ("palette", "Palette text"), ("indices", "Index array"), ("report", "JSON report"), ("text", "Text report")]:
            button = ttk.Button(actions, text=title, command=lambda k=kind: self.export(k), state="disabled")
            button.pack(side="left", padx=(0, 5))
            self.export_buttons[kind] = button
        ttk.Button(self.results_tab, text="Clear results for this image", command=self.clear_results).pack(anchor="w", pady=6)
        self.details = ScrolledText(self.results_tab, wrap="word", font=("Consolas", 10), height=8, state="disabled")
        self.details.pack(fill="both", expand=True)

    def _help_tab(self):
        text = ScrolledText(self.help_tab, wrap="word", font=("Segoe UI", 11), padx=16, pady=12)
        text.pack(fill="both", expand=True)
        text.insert("1.0", """START HERE

1. Try the built-in example, or Open image. The original file is read-only.
2. Color palettes: click Use image-specific palette. Adaptive colors and Fast mapping are the practical defaults. Build a shared palette from a folder or the examples to compare an image-specific palette with a reusable one.
3. JPEG compression: choose quality, then Compress & compare. Standard JPEG is a real .jpg; the educational MCS codec shows each stage and can save/reopen its own .mcs file.
4. DCT explorer: compare 4, 7, 8 and 16 retained coefficients. Select a row to view it. Inspect block shows actual spatial samples, transformed coefficients, quantization and zigzag order.
5. Compare images: choose any two current-image results, zoom to 100% or 200%, and drag/scroll. Difference x4 amplifies their absolute RGB differences; it is not another compression result.
6. Results & exports: select a result to read its settings, stages, measurements and available exports. Save result writes lossless PNG, including an actual indexed PNG for palette results. JPEG / MCS saves the exact encoded bytes, with no second lossy encode.

WHAT THE NUMBERS MEAN

MSE is average squared RGB error: lower is better. PSNR is derived from MSE: higher means less pixel error; identical pixels have infinite PSNR. Neither score measures human perception perfectly.
Ratios compare raw 24-bit RGB bytes with complete encoded file bytes. They do not predict savings relative to an already-compressed input JPEG. Small images or detailed noise may grow. Reports distinguish palette/index payload, PNG bytes, codec payload and complete stream overhead.
DCT coefficient-count ratios are not file-size ratios. That experiment performs no entropy coding or quantization.

FAST AND CLASSIC METHODS

Adaptive image palettes use Pillow median cut. Adaptive shared palettes use thumbnails of at most 65,536 pixels, then sample at most 4,096 evenly spaced pixels per image before median cut. This bounds work and balances image contributions. Classic mode counts exact RGB frequencies across all pixels and accepts dataset images up to 2 million pixels each. Frequent colors are not guaranteed to minimize error or cover gradients well.
Fast mapping uses Pillow's approximate fixed-palette lookup without dithering. Exact modes use bounded NumPy distance batches with deterministic ties; reference loops are limited to small images. These options intentionally trade speed and exact matching.

FILES, PRIVACY AND LIMITS

Up to 8 open images and the newest 16 results across them; older results are removed from memory. Export anything you need to keep. Source photos up to 50 million pixels are accepted; large imports become a labelled working copy of at most 2 million pixels. All processing, dimensions, quality scores and exports refer to that working copy. Adaptive datasets accept high-resolution photos using bounded thumbnails. Dataset: at most 200 files and 60 million processed pixels. Input/stream files: 64 MiB. One cancellable job runs in an isolated process with a 120-second timeout. Cancel or Escape stops it; original files and previous results remain safe.
Transparency is flattened over white or black, or explicitly ignored, on import. EXIF orientation is applied; source metadata is dropped. Only still images are supported. Color profiles are not transformed; comparisons use decoded RGB values.
Exports refuse to overwrite existing files: choose a new name. No user images or datasets are bundled, uploaded or automatically saved. Setup downloads dependencies; processing itself is local. Closing an image discards in-memory results; export anything you want to keep.
The educational MCS format uses a bounded JSON header, canonical Huffman data and SHA-256 integrity check. It is not a standard JPEG and does not load Python objects or pickle files.

SHORTCUTS
Ctrl+O: open image | Escape: cancel job | F1: help
""")
        text.configure(state="disabled")
        settings = ttk.Frame(self.help_tab, padding=(0, 8))
        settings.pack(fill="x", before=text)
        self.background = self.choice(settings, "Transparency on future image imports", ("white", "black", "ignore"), "white")

    def add_image(self, rgb, name, path=None, import_info=None):
        if len(self.sessions) >= 8:
            self.error("Close an image before opening another (maximum 8).")
            return False
        self.cancel(silent=True)
        self.serial += 1
        self.session = {"name": f"{self.serial}. {name}", "rgb": rgb, "results": {}, "path": path,
                        "import_info": {k:v for k,v in import_info.items() if k != "rgb"} if import_info else None}
        self.sessions.append(self.session)
        self.sources.configure(values=[s["name"] for s in self.sessions])
        self.source_name.set(self.session["name"])
        self.render_session()
        h, w = rgb.shape[:2]
        self.notice.set(f"{name} | {w} x {h} pixels | Original kept unchanged. Choose a tool below.")
        if import_info and import_info["resized"]:
            ow, oh = import_info["original_size"]
            self.notice.set(f"{name} | Working copy {w} x {h} (source {ow} x {oh}). All processing and metrics use this resized copy; source file unchanged.")
        self.status.set("Ready. Try an image-specific palette or a standard JPEG.")
        return True

    def switch_image(self, event=None):
        self.cancel(silent=True)
        self.session = next((s for s in self.sessions if s["name"] == self.source_name.get()), None)
        self.render_session()

    def remove_image(self):
        if self.session is None:
            return
        if self.session["results"] and not messagebox.askyesno("Close image", "Discard this image's in-memory results? Export anything you want to keep first.", parent=self.root):
            return
        self.cancel(silent=True)
        self.sessions.remove(self.session)
        self.session = self.sessions[-1] if self.sessions else None
        self.sources.configure(values=[s["name"] for s in self.sessions])
        self.source_name.set(self.session["name"] if self.session else "")
        self.render_session()

    def open_image(self):
        path = filedialog.askopenfilename(parent=self.root, title="Open a still image", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"), ("All files", "*.*")])
        if path:
            self.start("load", {"path": path, "background": self.background.get()}, lambda info: self.add_image(info["rgb"], Path(path).name, path, info))

    def start(self, task, args, callback):
        if self.job:
            self.error("A job is running. Cancel it before starting another.")
            return
        try:
            self.job = Job(task, args)
        except (OSError, RuntimeError, ValueError) as exc:
            self.error(exc)
            return
        self.callback = callback
        self.progress["value"] = 0
        for button in self.run_buttons:
            button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status.set("Processing in the background. Escape cancels.")
        self.after_id = self.root.after(40, self.poll)

    def poll(self):
        self.after_id = None
        if not self.job:
            return
        try:
            for kind, value in self.job.poll():
                if kind == "progress":
                    self.progress["value"] = value[0]*100
                    self.status.set(value[1])
                elif kind in {"done", "error"}:
                    callback = self.callback
                    self.cancel(silent=True)
                    if kind == "error":
                        self.error(value)
                    else:
                        self.progress["value"] = 100
                        self.status.set("Finished. Results are ready to compare and export.")
                        callback(value)
                    return
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            self.cancel(silent=True)
            self.error(exc)
            return
        self.after_id = self.root.after(40, self.poll)

    def cancel(self, silent=False):
        had_job = self.job is not None
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        if self.job:
            self.job.close()
            self.job = None
        self.callback = None
        for button in self.run_buttons:
            button.configure(state="normal")
        if hasattr(self, "cancel_button"):
            self.cancel_button.configure(state="disabled")
        if had_job:
            self.progress["value"] = 0
            if not silent:
                self.status.set("Cancelled. Your original and previous results are unchanged.")

    def require_image(self):
        if self.session is None:
            self.error("Open an image or try an example first.")
            return False
        return True

    def palette_options(self):
        try:
            k = int(self.colors.get())
        except ValueError as exc:
            raise ValueError("Choose a palette size from 1 to 256.") from exc
        if not 1 <= k <= 256:
            raise ValueError("Choose a palette size from 1 to 256.")
        return k, STRATEGIES[self.strategy.get()], METHODS[self.mapping.get()]

    def run_selected(self):
        if not self.require_image():
            return
        try:
            k, strategy, mode = self.palette_options()
            self.start("palette", {"rgb": self.session["rgb"], "k": k, "strategy": strategy, "mode": mode}, lambda result: self.store_result(f"Image palette {k} / {strategy} / {mode}", result, "palette"))
        except ValueError as exc:
            self.error(exc)

    def build_dataset(self):
        folder = filedialog.askdirectory(parent=self.root, title="Choose a folder of still images")
        if folder:
            try:
                k, strategy, _ = self.palette_options()
                self.start("dataset", {"folder": folder, "k": k, "strategy": strategy, "background": self.background.get()}, self.set_shared)
            except ValueError as exc:
                self.error(exc)

    def build_demo_palette(self):
        try:
            k, strategy, _ = self.palette_options()
            self.start("demo_palette", {"k": k, "strategy": strategy}, self.set_shared)
        except ValueError as exc:
            self.error(exc)

    def set_shared(self, result):
        self.shared_palette = result["palette"]
        self.shared_info = {k:v for k,v in result.items() if k != "palette"}
        detail = f"{len(self.shared_palette)} colors | {result.get('images', 0)} images | {result.get('strategy', 'loaded')}"
        if "sample_pixels" in result:
            detail += f" | {result['sample_pixels']:,} pixels sampled/counted"
        self.shared_note.set(detail)
        self.swatches.show(self.shared_palette)

    def load_palette(self):
        path = filedialog.askopenfilename(parent=self.root, title="Load RGB palette text", filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if path:
            try:
                palette = read_palette(path)
            except (OSError, ValueError, UnicodeError) as exc:
                self.error(exc)
                return
            self.cancel(silent=True)
            self.set_shared({"palette": palette})

    def run_shared(self):
        if not self.require_image():
            return
        if self.shared_palette is None:
            self.error("Build or load a shared palette first, or use the built-in examples.")
            return
        try:
            _, _, mode = self.palette_options()
            info = dict(self.shared_info or {})
            def completed(result):
                result["settings"]["shared_palette_origin"] = info
                self.store_result(f"Shared palette {len(result['palette'])} / {mode}", result, "palette")
            self.start("palette", {"rgb": self.session["rgb"], "palette": self.shared_palette.copy(), "mode": mode}, completed)
        except ValueError as exc:
            self.error(exc)

    def run_jpeg(self):
        if not self.require_image():
            return
        try:
            q = round(self.quality.get())
            quant_tables(q)
        except (ValueError, tk.TclError) as exc:
            self.error(exc)
            return
        sampling = self.sampling.get()
        task = "standard_jpeg" if self.jpeg_mode.get().startswith("Standard") else "jpeg"
        label = f"{'JPEG' if task == 'standard_jpeg' else 'MCS'} q{q} / {'4:2:0' if sampling else '4:4:4'}"
        self.start(task, {"rgb": self.session["rgb"], "quality": q, "sampling": sampling}, lambda r: self.store_result(label, r, "jpeg"))

    def run_dct(self):
        if not self.require_image():
            return
        try:
            keep = [int(v.strip()) for v in self.keep.get().split(",")]
            if not 1 <= len(keep) <= 8 or len(set(keep)) != len(keep) or any(not 1 <= k <= 64 for k in keep):
                raise ValueError("Use 1 to 8 distinct counts from 1 to 64, separated by commas.")
        except ValueError:
            self.error("Use 1 to 8 distinct counts from 1 to 64, separated by commas.")
            return
        self.start("dct", {"rgb": self.session["rgb"], "keep": keep}, self.store_dct)

    def store_dct(self, results):
        for result in results:
            self.store_result(f"DCT {result['settings']['kept_coefficients']} / 64", result, "dct")

    def open_stream(self):
        path = filedialog.askopenfilename(parent=self.root, title="Decode an educational MCS stream", filetypes=[("Image Compression Studio", "*.mcs")])
        if path:
            self.start("decode", {"path": path}, lambda rgb: self.add_image(rgb, "Decoded: " + Path(path).name))

    def store_result(self, name, result, family):
        if not self.session:
            return
        self.result_serial += 1
        label = f"{self.result_serial}. {name}"
        result.update(name=label, family=family)
        outputs = self.session["results"]
        outputs[label] = result
        all_results = [(int(key.split('.')[0]), s, key) for s in self.sessions for key in s["results"]]
        if len(all_results) > 16:
            _, old_session, old_key = min(all_results, key=lambda item: item[0])
            del old_session["results"][old_key]
            self.status.set("Finished. Oldest in-memory result removed (16-result limit); saved exports are kept.")
        self.active_result = label
        self.refresh_result_lists()
        self.display_result(label)
        self.notice.set(f"{name} | {metric_text(result['metrics'])} | Original unchanged.")

    def render_session(self):
        rgb = self.session["rgb"] if self.session else None
        for a, b in self.photo_pairs:
            a.show(rgb, "Original")
            b.show(None, "Result")
        self.active_result = next(reversed(self.session["results"]), None) if self.session else None
        self.refresh_result_lists()
        if self.active_result:
            for family in ("palette", "jpeg", "dct"):
                name = self.family_result(family)
                if name:
                    self.display_result(name)
            self.tab_changed()
        else:
            self.swatches.show(self.shared_palette)
            self.palette_metric.set("Choose an image-specific or shared palette to see results.")
            self.jpeg_metric.set("Compress to compare the actual decoded result.")
            self.set_details("Run a tool, then select its result to see measured quality, settings and exports.")
        if self.session:
            h, w = rgb.shape[:2]
            imported = self.session.get("import_info")
            if imported and imported["resized"]:
                self.notice.set(f"{self.session['name']} | Resized working copy {w} x {h}; source {imported['original_size'][0]} x {imported['original_size'][1]}. Metrics and exports use the working copy.")
            else:
                self.notice.set(f"{self.session['name']} | {w} x {h} pixels | Results belong to this image only.")
        else:
            self.notice.set("Open an image or try an example to begin.")

    def refresh_result_lists(self):
        results = self.session["results"] if self.session else {}
        self.result_table.delete(*self.result_table.get_children())
        self.dct_table.delete(*self.dct_table.get_children())
        for name, result in results.items():
            m = result["metrics"]
            psnr = "identical" if m["psnr_db"] is None else f"{m['psnr_db']:.2f}"
            encoded = result.get("jpeg", result.get("stream", result["png"]))
            self.result_table.insert("", "end", iid=name, values=(name, psnr, f"{m['mse']:.3f}", len(encoded), f"{result['stats']['elapsed_ms']:.1f}"))
            if result["family"] == "dct":
                k = result["settings"]["kept_coefficients"]
                self.dct_table.insert("", "end", iid=name, values=(k, psnr, f"{m['mse']:.3f}", f"{100*k/64:.1f}%"))
        names = ["Original", *results]
        self.left_choice.configure(values=names)
        self.right_choice.configure(values=names)
        if self.compare_left.get() not in names:
            self.compare_left.set("Original")
        if self.compare_right.get() not in names:
            self.compare_right.set("Original")
        self.update_exports()
        self.refresh_comparison()

    def display_result(self, name):
        result = self.session["results"].get(name) if self.session else None
        if result is None:
            return
        self.active_result = name
        resized = self.session.get("import_info") and self.session["import_info"]["resized"]
        self.notice.set(name + " | " + metric_text(result["metrics"]) + (" | Resized working copy; source unchanged." if resized else " | Original unchanged."))
        family = result["family"]
        if family == "palette":
            self.palette_output.show(result["image"], name)
            self.swatches.show(result["palette"])
            self.palette_metric.set(name + " | " + metric_text(result["metrics"]))
        elif family == "jpeg":
            self.jpeg_output.show(result["image"], name)
            self.jpeg_metric.set(name + " | " + metric_text(result["metrics"]))
        else:
            self.dct_output.show(result["image"], name)
        self.set_details(self.text_report(result))
        self.update_exports()

    def select_result(self, event=None):
        selected = self.result_table.selection()
        if selected:
            self.display_result(selected[0])

    def select_dct(self, event=None):
        selected = self.dct_table.selection()
        if selected:
            self.display_result(selected[0])

    def current_result(self):
        return self.session["results"].get(self.active_result) if self.session else None

    def update_exports(self):
        result = self.current_result()
        for kind, button in self.export_buttons.items():
            enabled = result is not None and (kind not in {"palette", "indices", "encoded"} or
                      (kind in result if kind != "encoded" else "jpeg" in result or "stream" in result))
            button.configure(state="normal" if enabled else "disabled")

    def clear_results(self):
        if not self.session:
            return
        if self.session["results"] and not messagebox.askyesno("Clear results", "Discard all in-memory results for this image? Saved exports and the original are kept.", parent=self.root):
            return
        self.cancel(silent=True)
        self.session["results"].clear()
        self.render_session()

    def show_comparison(self):
        if self.active_result:
            self.compare_left.set("Original")
            self.compare_right.set(self.active_result)
        self.tabs.select(self.compare_tab)
        self.refresh_comparison()

    def refresh_comparison(self):
        if not self.session:
            self.compare_a.show(None)
            self.compare_b.show(None)
            return
        def image(name):
            return self.session["rgb"] if name == "Original" else self.session["results"][name]["image"]
        a, b = image(self.compare_left.get()), image(self.compare_right.get())
        self.compare_a.show(a, self.compare_left.get(), self.zoom.get())
        if self.difference.get():
            delta = np.clip(np.abs(a.astype(np.int16) - b.astype(np.int16))*4, 0, 255).astype(np.uint8)
            self.compare_b.show(delta, "Absolute RGB difference x4", self.zoom.get())
        else:
            self.compare_b.show(b, self.compare_right.get(), self.zoom.get())
        from .images import metrics
        self.compare_metric.set(metric_text(metrics(a, b)) + " | Drag or scroll at pixel zoom. Difference is amplified for visibility.")

    def inspect_block(self):
        if not self.require_image():
            return
        try:
            x, y = int(self.block_x.get()), int(self.block_y.get())
            spatial, coefficients = block_details(self.session["rgb"], x, y)
            quality = round(self.quality.get())
            table = quant_tables(quality)[0]
        except (ValueError, tk.TclError) as exc:
            self.error(exc)
            return
        window = tk.Toplevel(self.root)
        window.title(f"Luminance block ({x}, {y})")
        window.geometry("820x680")
        text = ScrolledText(window, font=("Consolas", 10), wrap="none")
        text.pack(fill="both", expand=True)
        for title, array in [("Level-shifted spatial samples", spatial), ("Unrounded orthonormal DCT", coefficients),
                             (f"Luminance quantization table (quality {quality})", table),
                             ("Rounded DCT / quantization table, rounded to integer", np.rint(np.rint(coefficients)/table)),
                             ("Zigzag frequency order (positions 0..63)", np.argsort(ZIGZAG).reshape(8, 8))]:
            text.insert("end", title + "\n" + np.array2string(array, precision=2, suppress_small=True, max_line_width=110) + "\n\n")
        text.configure(state="disabled")

    def report(self, result):
        return {"application": "Image Compression Studio", "source": self.session["name"],
                "width": self.session["rgb"].shape[1], "height": self.session["rgb"].shape[0],
                "import": self.session.get("import_info"), "result": result["name"], "settings": result["settings"], "metrics": result["metrics"],
                "statistics": result["stats"], "steps": result["steps"],
                "notes": ["Processing and metrics use the imported working image, resized when the source exceeds 2 million pixels.", "PSNR null means identical pixels (positive infinity).", "Size ratios compare raw RGB bytes with complete encoded files, not the input file size.", "DCT 64/k is a coefficient-count ratio, not file compression."]}

    def text_report(self, result):
        report = self.report(result)
        lines = [report["application"], report["source"], f"Working image: {report['width']} x {report['height']}", result["name"], metric_text(result["metrics"])]
        if report["import"]:
            info = report["import"]
            lines += [f"Source dimensions: {info['original_size'][0]} x {info['original_size'][1]}",
                      f"Resized on import: {info['resized']} | Transparency: {info['background']}"]
        lines += ["", "SETTINGS"]
        lines += [f"{key}: {value}" for key, value in result["settings"].items()]
        lines += ["", "MEASUREMENTS"] + [f"{key}: {value:.3f}" if isinstance(value, float) else f"{key}: {value}" for key, value in result["stats"].items()]
        lines += ["", "PROCESSING"] + result["steps"] + ["", "INTERPRETATION"] + report["notes"]
        return "\n".join(lines)

    def set_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def export(self, kind):
        result = self.current_result()
        try:
            if kind == "shared_palette":
                if self.shared_palette is None:
                    raise ValueError("Build or load a shared palette first.")
                suffix, data = ".txt", palette_text(self.shared_palette).encode("utf-8")
            else:
                if result is None:
                    raise ValueError("Run a tool or select a result first.")
                if kind == "image":
                    suffix, data = ".png", result["png"]
                elif kind == "encoded":
                    if "jpeg" in result:
                        suffix, data = ".jpg", result["jpeg"]
                    elif "stream" in result:
                        suffix, data = ".mcs", result["stream"]
                    else:
                        raise ValueError("Select a JPEG or MCS result to export its encoded file.")
                elif kind == "palette":
                    suffix, data = ".txt", palette_text(result["palette"]).encode("utf-8")
                elif kind == "indices":
                    from io import StringIO
                    out = StringIO()
                    np.savetxt(out, result["indices"], fmt="%d", delimiter="\t")
                    suffix, data = ".txt", out.getvalue().encode("utf-8")
                elif kind == "report":
                    suffix, data = ".json", json_bytes(self.report(result))
                elif kind == "text":
                    suffix, data = ".txt", self.text_report(result).encode("utf-8")
                else:
                    raise ValueError("Unknown export format.")
            path = filedialog.asksaveasfilename(parent=self.root, title="Save a new file (existing files are protected)", initialfile="media-result"+suffix, defaultextension=suffix, filetypes=[(suffix.lstrip('.').upper(), "*"+suffix)])
            if not path:
                return
            if Path(path).suffix.lower() not in ({".jpg", ".jpeg"} if suffix == ".jpg" else {suffix}):
                raise ValueError(f"Use a {suffix} filename for this export format.")
            write_new(path, data)
            self.status.set(f"Saved {Path(path).name}. Original unchanged.")
        except (OSError, ValueError, KeyError) as exc:
            self.error("Choose a new filename; existing files are never overwritten." if isinstance(exc, FileExistsError) else exc)

    def error(self, message):
        self.status.set(str(message))
        messagebox.showerror("Image Compression Studio", str(message), parent=self.root)

    def close(self):
        if any(s["results"] for s in self.sessions):
            if not messagebox.askyesno("Close Image Compression Studio", "Close and discard in-memory results? Saved exports are kept.", parent=self.root):
                return
        self.cancel(silent=True)
        self.root.destroy()


def launch():
    import sys
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    root = tk.Tk()
    Studio(root)
    root.mainloop()
