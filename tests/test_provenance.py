import numpy as np
from media_studio.images import pixel_fingerprint


def test_fingerprint_covers_exact_pixels_and_shape_not_memory_layout():
    image = np.arange(36, dtype=np.uint8).reshape(3, 4, 3)
    assert pixel_fingerprint(image) == pixel_fingerprint(np.asfortranarray(image))
    assert pixel_fingerprint(image) != pixel_fingerprint(image.reshape(4, 3, 3))
    changed = image.copy()
    changed[0, 0, 0] += 1
    assert pixel_fingerprint(image) != pixel_fingerprint(changed)


def test_desktop_runtime_failure_has_setup_guidance_without_traceback(monkeypatch, capsys):
    import tkinter as tk
    from media_studio import gui
    from media_studio.__main__ import main
    def fail():
        raise tk.TclError('Synthetic unavailable Tcl runtime')
    monkeypatch.setattr(gui, 'launch', fail)
    assert main([]) == 2
    output = capsys.readouterr().err
    assert 'base environment' in output and 'headless CLI' in output and 'Traceback' not in output
