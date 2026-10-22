from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import json

from PIL import Image

from media_studio.images import demo_image
from media_studio.jobs import Job


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.image = self.folder/'test.png'
        Image.fromarray(demo_image(width=23,height=17)).save(self.image)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable,'-X','utf8','-m','media_studio',*map(str,args)], capture_output=True, text=True, timeout=30)

    def test_cli_palette_jpeg_dct_and_mcs_decode(self):
        for command, options in [('palette',[]),('jpeg',[]),('dct',['--keep','4','64']),('jpeg',['--educational'])]:
            out=self.folder/(command+str(len(options)))
            result=self.cli(command,self.image,out,*options)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads((out/'report.json').read_text())
            self.assertTrue(report['results'])
            if '--educational' in options:
                decoded=self.folder/'decoded'
                result=self.cli('decode',out/'compression.mcs',decoded)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue((decoded/'decoded.png').is_file())

    def test_cli_dataset_and_shared_palette(self):
        output=self.folder/'dataset-output'
        result=self.cli('dataset',self.folder,output,'--colors','16')
        self.assertEqual(result.returncode,0,result.stderr)
        result=self.cli('palette',self.image,self.folder/'mapped','--palette',output/'palette.txt','--mapping','direct')
        self.assertEqual(result.returncode,0,result.stderr)

    def test_cli_invalid_inputs_and_existing_output_leave_source_unchanged(self):
        original=self.image.read_bytes()
        for command,options in [('jpeg',['--quality','0']),('palette',['--colors','0']),('dct',['--keep','0'])]:
            output=self.folder/'invalid-output'
            result=self.cli(command,self.image,output,*options)
            self.assertEqual(result.returncode,2)
            self.assertFalse(output.exists())
        result=self.cli('palette',self.image,self.folder)
        self.assertEqual(result.returncode,2)
        result=self.cli('jpeg',self.folder/'missing.png',self.folder/'out')
        self.assertEqual(result.returncode,2)
        self.assertEqual(self.image.read_bytes(),original)

    def test_worker_returns_progress_result_and_errors(self):
        for task,args,expected in [('standard_jpeg',{'rgb':demo_image(width=41,height=31)},'done'),('load',{'path':str(self.folder/'missing.png')},'error')]:
            job=Job(task,args)
            try:
                deadline=time.monotonic()+15
                result=None
                while time.monotonic()<deadline and result is None:
                    for kind,value in job.poll():
                        if kind in {'done','error'}:result=(kind,value)
                    time.sleep(.02)
                self.assertIsNotNone(result)
                self.assertEqual(result[0],expected)
            finally:job.close()

    def test_worker_hard_timeout_and_cancel(self):
        job=Job('jpeg',{'rgb':demo_image()},timeout=.001)
        time.sleep(.01)
        with self.assertRaises(TimeoutError):job.poll()
        self.assertFalse(job.process.is_alive())
        job=Job('jpeg',{'rgb':demo_image()})
        job.close()
        self.assertFalse(job.process.is_alive())


if __name__=='__main__':unittest.main()
