"""Cancellable, time-bounded processing; child processes never touch Tk widgets."""

import multiprocessing as mp
from pathlib import Path
import queue
import time


def perform(task, args, progress=lambda value, text: None):
    from .images import read_image, MAX_FILE_BYTES
    from .palettes import quantize, dataset_palette
    from .codec import compress, coefficient_study, decode, standard_jpeg
    if task == "load":
        return read_image(**args)
    if task == "palette":
        return quantize(**args, progress=progress)
    if task == "dataset":
        return dataset_palette(**args, progress=progress)
    if task == "jpeg":
        return compress(**args, progress=progress)
    if task == "standard_jpeg":
        return standard_jpeg(**args, progress=progress)
    if task == "demo_palette":
        from .images import demo_image
        from .palettes import selected_palette
        import numpy as np
        combined = np.concatenate([demo_image(kind) for kind in ["Color & detail", "Gradients", "Geometric shapes"]])
        return {"palette": selected_palette(combined, args["k"], args["strategy"]), "images": 3,
                "pixels": combined.shape[0]*combined.shape[1], "strategy": args["strategy"]}
    if task == "dct":
        return coefficient_study(**args, progress=progress)
    if task == "decode":
        path = Path(args["path"])
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Stream exceeds 64 MiB.")
        return decode(path.read_bytes(), progress=progress)
    raise ValueError("Unknown processing task.")


def _run(task, args, output):
    last = 0.0

    def progress(value, text):
        nonlocal last
        now = time.monotonic()
        if now-last < .08:
            return
        last = now
        try:
            output.put_nowait(("progress", (value, text)))
        except queue.Full:
            pass

    try:
        result = perform(task, args, progress)
        output.put(("done", result))
    except Exception as exc:
        output.put(("error", f"{type(exc).__name__}: {exc}"))


class Job:
    def __init__(self, task, args, timeout=120):
        ctx = mp.get_context("spawn")
        self.messages = ctx.Queue(maxsize=16)
        self.process = ctx.Process(target=_run, args=(task, args, self.messages), daemon=True)
        self.deadline = time.monotonic() + timeout
        self.dead_polls = 0
        self.process.start()

    def poll(self):
        if time.monotonic() > self.deadline:
            self.close()
            raise TimeoutError("Processing exceeded 120 seconds. Try a smaller image or dataset.")
        found = []
        while len(found) < 16:
            try:
                found.append(self.messages.get_nowait())
            except queue.Empty:
                break
        if not self.process.is_alive() and not found:
            self.dead_polls += 1
            if self.dead_polls > 3:
                raise RuntimeError("The worker stopped before returning a result.")
        else:
            self.dead_polls = 0
        return found

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=1)
        self.messages.close()
        self.messages.cancel_join_thread()
