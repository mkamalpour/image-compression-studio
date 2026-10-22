"""Scrollable image previews with fit and pixel zoom; palette inspection."""

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk


class ImageView(ttk.Frame):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.title = tk.StringVar(value=title)
        heading = ttk.Label(self, textvariable=self.title, font=("Segoe UI", 11, "bold"), wraplength=230)
        heading.pack(anchor="w", pady=(0, 5))
        self.bind("<Configure>", lambda e: heading.configure(wraplength=max(100,e.width-10)) if e.widget == self else None)
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="#e7edf5", highlightthickness=0, width=180, height=160)
        sx = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        sy = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.image = None
        self.photo = None
        self.zoom = "Fit"
        self.redraw_id = None
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.bind("<Destroy>", self._destroy)

    def _destroy(self, event):
        if event.widget == self and self.redraw_id:
            self.after_cancel(self.redraw_id)
            self.redraw_id = None

    def _resize(self, event=None):
        if self.redraw_id:
            self.after_cancel(self.redraw_id)
        self.redraw_id = self.after(50, self.redraw)

    def show(self, array=None, title=None, zoom=None):
        self.image = None if array is None else Image.fromarray(array)
        if title is not None:
            self.title.set(title)
        if zoom is not None:
            self.zoom = zoom
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.redraw()

    def redraw(self):
        if self.redraw_id:
            self.after_cancel(self.redraw_id)
        self.redraw_id = None
        self.canvas.delete("all")
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if self.image is None:
            self.photo = None
            self.canvas.create_text(w//2, h//2, text="Open an image or try an example", fill="#53647c", width=max(80, w-20))
            self.canvas.configure(scrollregion=(0, 0, w, h))
            return
        factor = min(w/self.image.width, h/self.image.height, 1) if self.zoom == "Fit" else int(self.zoom.rstrip("%"))/100
        size = (max(1, round(self.image.width*factor)), max(1, round(self.image.height*factor)))
        resized = self.image.resize(size, Image.Resampling.LANCZOS if factor < 1 else Image.Resampling.NEAREST)
        self.photo = ImageTk.PhotoImage(resized, master=self.canvas)
        self.canvas.create_image(max(w, size[0])//2, max(h, size[1])//2, image=self.photo)
        self.canvas.configure(scrollregion=(0, 0, max(w, size[0]), max(h, size[1])))


class PaletteView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.caption = tk.StringVar(value="Palette colors appear here. Click a swatch to inspect it.")
        ttk.Label(self, textvariable=self.caption).pack(anchor="w")
        self.canvas = tk.Canvas(self, height=85, background="white", highlightthickness=0)
        self.canvas.pack(fill="x", pady=(4, 0))
        self.palette = None
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", self.inspect)

    def show(self, palette):
        self.palette = palette
        self.caption.set("No palette yet" if palette is None else f"{len(palette)} colors | RGB overhead: {palette.size} bytes | Click a swatch")
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        if self.palette is None:
            return
        width = max(1, self.canvas.winfo_width())
        for i, rgb in enumerate(self.palette):
            col, row = i % 64, i // 64
            color = "#" + "".join(f"{int(v):02x}" for v in rgb)
            self.canvas.create_rectangle(col*width/64, row*21, (col+1)*width/64, (row+1)*21, fill=color, outline="#ffffff", tags=(str(i),))

    def inspect(self, event):
        found = self.canvas.find_withtag("current")
        if found and self.palette is not None:
            i = int(self.canvas.gettags(found[0])[0])
            rgb = tuple(int(v) for v in self.palette[i])
            self.caption.set(f"Index {i} | RGB {rgb} | #" + "".join(f"{v:02X}" for v in rgb))
