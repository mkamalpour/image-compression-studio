from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import json
import sys

if sys.platform == 'win32':
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()

import numpy as np
from PIL import Image

from media_studio.gui import Studio
from media_studio.images import demo_image


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A desktop session owns one Tcl interpreter. Repeated destruction and
        # reinitialization can intermittently fail while sourcing Conda's Tk
        # library on Windows; recreate widgets, not the interpreter, per test.
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.root.withdraw()
        self.app=Studio(self.root)
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)
        self.errors=[]
        self.patcher=patch('media_studio.gui.messagebox.showerror',side_effect=lambda title,message,**kw:self.errors.append(message))
        self.patcher.start()
        self.root.update()

    def tearDown(self):
        self.app.cancel(silent=True)
        for callback in self.root.tk.call('after', 'info'):
            # Leave each command registered with its owning widget; destroying
            # that widget removes it once. Root.after_cancel would delete a
            # widget-owned command before the widget's own cleanup.
            self.root.tk.call('after', 'cancel', callback)
        for child in self.root.winfo_children():
            child.destroy()
        self.root.update_idletasks()
        self.patcher.stop()
        self.tmp.cleanup()

    def wait(self):
        end=time.monotonic()+20
        while self.app.job and time.monotonic()<end:
            self.root.update()
            time.sleep(.01)
        self.assertIsNone(self.app.job,'Worker did not finish')
        self.root.update()

    def test_all_feature_tabs_and_fast_defaults(self):
        self.assertEqual(len(self.app.tabs.tabs()),6)
        self.assertEqual(self.app.mapping.get(),'Fast (recommended)')
        self.assertTrue(self.app.jpeg_mode.get().startswith('Standard'))
        self.assertIsNotNone(self.app.session)
        self.app.colors.set('16')
        self.app.run_selected();self.wait()
        result=self.app.current_result()
        self.assertEqual(result['family'],'palette')
        self.assertEqual(result['settings']['mapping'],'fast')
        self.assertTrue(self.app.swatches.palette is not None)
        self.assertFalse(self.errors)

    def test_shared_palette_demo_build_save_load_and_apply(self):
        self.app.colors.set('16')
        self.app.build_demo_palette();self.wait()
        self.assertEqual(len(self.app.shared_palette),16)
        path=self.folder/'shared.txt'
        with patch('media_studio.gui.filedialog.asksaveasfilename',return_value=str(path)):
            self.app.export('shared_palette')
        original=self.app.shared_palette.copy()
        self.app.shared_palette=None
        with patch('media_studio.gui.filedialog.askopenfilename',return_value=str(path)):
            self.app.load_palette()
        np.testing.assert_array_equal(self.app.shared_palette,original)
        self.app.run_shared();self.wait()
        self.assertIn('Shared palette',self.app.current_result()['name'])
        self.assertFalse(self.errors)

    def test_standard_jpeg_and_mcs_export_decode(self):
        self.app.run_jpeg();self.wait()
        jpeg=self.app.current_result()
        self.assertIn('jpeg',jpeg)
        path=self.folder/'output.jpg'
        with patch('media_studio.gui.filedialog.asksaveasfilename',return_value=str(path)):
            self.app.export('encoded')
        self.assertEqual(path.read_bytes(),jpeg['jpeg'])
        self.app.jpeg_mode.set('Educational JPEG-style (MCS)')
        self.app.run_jpeg();self.wait()
        mcs=self.app.current_result()
        path=self.folder/'output.mcs'
        with patch('media_studio.gui.filedialog.asksaveasfilename',return_value=str(path)):
            self.app.export('encoded')
        with patch('media_studio.gui.filedialog.askopenfilename',return_value=str(path)):
            self.app.open_stream();self.wait()
        np.testing.assert_array_equal(self.app.session['rgb'],mcs['image'])
        self.assertEqual(len(self.app.sessions),2)
        self.assertFalse(self.errors)

    def test_dct_rows_selection_and_block_inspection(self):
        self.app.keep.set('4,16,64')
        self.app.run_dct();self.wait()
        rows=self.app.dct_table.get_children()
        self.assertEqual(len(rows),3)
        self.app.dct_table.selection_set(rows[0]);self.app.select_dct()
        self.assertEqual(self.app.current_result()['settings']['kept_coefficients'],4)
        self.app.inspect_block()
        windows=[child for child in self.root.winfo_children() if isinstance(child,tk.Toplevel)]
        self.assertEqual(len(windows),1)
        self.assertFalse(self.errors)

    def test_multiple_images_keep_results_and_failed_open_preserves_input(self):
        self.app.run_jpeg();self.wait()
        first=self.app.session
        self.app.add_image(demo_image('Geometric shapes'),'second')
        self.assertFalse(self.app.session['results'])
        self.app.source_name.set(first['name']);self.app.switch_image()
        self.assertIs(self.app.session,first)
        self.assertEqual(len(first['results']),1)
        with patch('media_studio.gui.filedialog.askopenfilename',return_value=str(self.folder/'missing.png')):
            self.app.open_image();self.wait()
        self.assertIs(self.app.session,first)
        self.assertEqual(len(first['results']),1)
        self.assertTrue(self.errors)

    def test_cancel_and_switch_never_attach_stale_results(self):
        self.app.run_jpeg()
        process=self.app.job.process
        self.app.add_image(demo_image('Gradients'),'new source')
        self.assertIsNone(self.app.job)
        self.assertFalse(process.is_alive())
        self.assertFalse(self.app.session['results'])
        self.assertEqual(str(self.app.cancel_button['state']),'disabled')

    def test_family_actions_never_export_another_tools_result(self):
        self.app.run_selected();self.wait()
        palette=self.app.current_result()
        self.app.run_jpeg();self.wait()
        path=self.folder/'palette.png'
        with patch('media_studio.gui.filedialog.asksaveasfilename',return_value=str(path)):
            self.app.family_action('palette','save')
        self.assertEqual(path.read_bytes(),palette['png'])
        self.assertEqual(self.app.current_result()['family'],'palette')
        self.assertFalse(self.errors)

    def test_settings_snapshots_and_comparison_zoom_difference(self):
        self.app.quality.set(40);self.app.run_jpeg();self.wait()
        first=self.app.current_result()
        self.app.quality.set(90);self.app.run_jpeg();self.wait()
        self.assertEqual(first['settings']['quality'],40)
        self.assertEqual(len(self.app.session['results']),2)
        self.app.show_comparison()
        self.app.zoom.set('200%');self.app.difference.set(True)
        self.app.refresh_comparison()
        self.assertEqual(self.app.compare_b.title.get(),'Absolute RGB difference x4')
        expected=np.clip(np.abs(self.app.session['rgb'].astype(np.int16)-self.app.current_result()['image'].astype(np.int16))*4,0,255).astype(np.uint8)
        np.testing.assert_array_equal(np.array(self.app.compare_b.image),expected)

    def test_export_indices_palette_reports_and_overwrite_protection(self):
        self.app.colors.set('16');self.app.run_selected();self.wait()
        for kind,suffix in [('image','.png'),('palette','.txt'),('indices','.txt'),('report','.json'),('text','.txt')]:
            path=self.folder/(kind+suffix)
            with patch('media_studio.gui.filedialog.asksaveasfilename',return_value=str(path)):
                self.app.export(kind)
                original=path.read_bytes()
                self.app.export(kind)
                self.assertEqual(path.read_bytes(),original)
            self.assertTrue(path.is_file())
        report=json.loads((self.folder/'report.json').read_text())
        self.assertEqual(report['settings']['colors'],16)
        self.assertEqual(len(self.errors),5)

    def test_invalid_controls_and_missing_palette_are_helpful(self):
        self.app.colors.set('0');self.app.run_selected()
        self.app.keep.set('4,4');self.app.run_dct()
        self.app.run_shared()
        self.app.block_x.set('99999');self.app.inspect_block()
        self.assertEqual(len(self.errors),4)
        self.assertIsNone(self.app.job)

    def test_clear_and_close_respect_cancel_and_preserve_original(self):
        self.app.run_jpeg();self.wait()
        original=self.app.session['rgb'].copy()
        with patch('media_studio.gui.messagebox.askyesno',return_value=False):
            self.app.clear_results();self.app.remove_image()
        self.assertEqual(len(self.app.session['results']),1)
        with patch('media_studio.gui.messagebox.askyesno',return_value=True):self.app.clear_results()
        self.assertFalse(self.app.session['results'])
        np.testing.assert_array_equal(self.app.session['rgb'],original)
        self.assertIsNone(self.app.current_result())
        self.assertTrue(all(str(b['state'])=='disabled' for b in self.app.export_buttons.values()))

    def test_primary_controls_visible_at_small_window(self):
        self.root.deiconify();self.root.geometry('1000x760');self.root.update()
        for tab in [self.app.palette_tab,self.app.jpeg_tab,self.app.dct_tab]:
            self.app.tabs.select(tab);self.root.update()
            for button in self.app.run_buttons:
                if str(button).startswith(str(tab) + '.'):
                    self.assertTrue(button.winfo_ismapped(),button['text'])
                    self.assertGreater(button.winfo_height(),20)
                    self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),tab.winfo_rooty()+tab.winfo_height())

    def test_high_resolution_import_report_uses_resized_working_copy(self):
        path=self.folder/'large.png'
        Image.new('RGB',(2001,1001),(40,90,170)).save(path)
        original=path.read_bytes()
        with patch('media_studio.gui.filedialog.askopenfilename',return_value=str(path)):
            self.app.open_image();self.wait()
        self.assertTrue(self.app.session['import_info']['resized'])
        self.assertLessEqual(self.app.session['rgb'].size//3,2_000_000)
        self.assertIn('working copy',self.app.notice.get().lower())
        self.app.run_jpeg();self.wait()
        report=self.app.report(self.app.current_result())
        self.assertTrue(report['import']['resized'])
        json.dumps(report,allow_nan=False)
        self.assertEqual(path.read_bytes(),original)
        self.assertFalse(self.errors)

    def test_retention_limit_is_global_and_keeps_source_images(self):
        from media_studio.codec import standard_jpeg
        result=standard_jpeg(demo_image(width=4,height=4))
        first=self.app.session
        for i in range(16):self.app.store_result('test JPEG',dict(result),'jpeg')
        old=next(iter(first['results']))
        self.app.add_image(demo_image(width=4,height=4),'second')
        self.app.store_result('new JPEG',dict(result),'jpeg')
        self.assertNotIn(old,first['results'])
        self.assertEqual(sum(len(s['results']) for s in self.app.sessions),16)
        self.assertEqual(len(self.app.sessions),2)

    def test_wrong_export_extension_and_cancel_create_no_files(self):
        self.app.run_jpeg();self.wait()
        path=self.folder/'wrong.jpg'
        with patch('media_studio.gui.filedialog.asksaveasfilename',return_value=str(path)):
            self.app.export('image')
        self.assertFalse(path.exists())
        with patch('media_studio.gui.filedialog.asksaveasfilename',return_value=''):
            self.app.export('image')
        self.assertEqual(len(self.errors),1)


if __name__=='__main__':unittest.main()
