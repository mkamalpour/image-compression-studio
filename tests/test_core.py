from collections import Counter
from io import BytesIO
from pathlib import Path
import hashlib
import json
import struct
import tempfile
import unittest

import numpy as np
from PIL import Image

from media_studio.images import (demo_image, metrics, load_rgb, png_bytes, write_new, json_bytes, MAX_PIXELS)
from media_studio.palettes import (selected_palette, map_colors, dataset_palette, quantize,
                                   palette_text, read_palette, validate_palette)
from media_studio.transforms import (DCT, ZIGZAG, blocks, merge, dct, idct, subsample,
                                    rgb_to_ycbcr, ycbcr_to_rgb, quant_tables, block_details)
from media_studio.codec import encode, decode, compress, coefficient_study, standard_jpeg, parse_stream
from media_studio.entropy import (encode_channels, BitReader, decode_channel, canonical,
                                  huffman_lengths, amplitude, signed, category)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_color_conversion_and_metric_math(self):
        rgb = np.random.default_rng(3).integers(0, 256, (17, 19, 3), dtype=np.uint8)
        np.testing.assert_array_equal(ycbcr_to_rgb(rgb_to_ycbcr(rgb)), rgb)
        self.assertEqual(metrics(rgb, rgb), {"mse": 0, "psnr_db": None})
        self.assertEqual(metrics(np.zeros((1,1,3), np.uint8), np.full((1,1,3), 255, np.uint8)), {"mse": 65025, "psnr_db": 0})
        self.assertIn(b'null', json_bytes(metrics(rgb, rgb)))

    def test_dct_matches_independent_scalar_formula_and_inverse(self):
        rng = np.random.default_rng(4)
        samples = rng.normal(size=(3,8,8))
        np.testing.assert_allclose(DCT @ DCT.T, np.eye(8), atol=1e-14)
        np.testing.assert_allclose(idct(dct(samples)), samples, atol=1e-14)
        expected = np.zeros((8,8))
        for u in range(8):
            for v in range(8):
                for x in range(8):
                    for y in range(8):
                        expected[u,v] += samples[0,x,y] * np.cos((2*x+1)*u*np.pi/16)*np.cos((2*y+1)*v*np.pi/16)
                expected[u,v] *= (.25 / (np.sqrt(2) if u==0 else 1) / (np.sqrt(2) if v==0 else 1))
        np.testing.assert_allclose(dct(samples)[0], expected, atol=1e-13)

    def test_padding_sampling_and_zigzag_invariants(self):
        self.assertEqual(ZIGZAG[:10].tolist(), [0,1,8,16,9,2,3,10,17,24])
        self.assertEqual(sorted(ZIGZAG.tolist()), list(range(64)))
        for shape in [(1,1),(1,17),(17,1),(13,19),(16,16)]:
            a = np.arange(np.prod(shape)).reshape(shape).astype(float)
            np.testing.assert_array_equal(merge(blocks(a), shape), a)
            small = subsample(a)
            self.assertEqual(small.shape, ((shape[0]+1)//2, (shape[1]+1)//2))
        self.assertAlmostEqual(dct(np.full((8,8), 5.0))[0,0], 40)

    def test_classic_palette_frequencies_and_ties(self):
        rgb = np.array([[[255,0,0],[0,255,0],[255,0,0],[0,0,255]]], np.uint8)
        self.assertEqual(selected_palette(rgb, 2, 'frequency').tolist(), [[255,0,0],[0,0,255]])
        with self.assertRaises(ValueError): selected_palette(rgb, 0)
        for bad in [[], [[1,2]], [[-1,0,0]], [[256,1,1]], [[1.2,2,3]]]:
            with self.assertRaises(ValueError): validate_palette(bad)

    def test_exact_mapping_modes_match_brute_force_without_overflow(self):
        rgb = np.random.default_rng(8).integers(0,256,(19,21,3),dtype=np.uint8)
        palette = np.array([[0,0,0],[255,255,255],[100,170,200],[255,0,0]],np.uint8)
        expected = map_colors(rgb, palette, 'reference')
        for mode in ['direct','unique']:
            np.testing.assert_array_equal(map_colors(rgb, palette, mode), expected)
        self.assertEqual(int(map_colors(np.array([[[127,0,0]]],np.uint8), [[0,0,0],[254,0,0]], 'direct')[0,0]), 0)
        blackwhite = np.array([[[255,255,255],[0,0,0]]],np.uint8)
        np.testing.assert_array_equal(map_colors(blackwhite, [[0,0,0],[255,255,255]], 'direct'), [[1,0]])

    def test_adaptive_and_fast_mapping_stay_in_palette(self):
        for kind in ['Color & detail','Gradients','Geometric shapes']:
            rgb = demo_image(kind, 47, 31)
            for k in [1,16,256]:
                result = quantize(rgb, k)
                self.assertLessEqual(len(result['palette']), k)
                np.testing.assert_array_equal(result['palette'][result['indices']], result['image'])
                with Image.open(BytesIO(result['png'])) as loaded:
                    self.assertEqual(loaded.mode, 'P')
                    np.testing.assert_array_equal(np.array(loaded.convert('RGB')), result['image'])
                self.assertEqual(result['stats']['png_file_bytes'], len(result['png']))

    def test_palette_text_roundtrip_and_strict_validation(self):
        p = self.folder/'palette.txt'
        palette = np.array([[1,2,3],[254,255,0]],np.uint8)
        p.write_text(palette_text(palette),encoding='utf-8')
        np.testing.assert_array_equal(read_palette(p),palette)
        p.write_text('0 1 2 3\n3 4 5 6\n')
        with self.assertRaises(ValueError): read_palette(p)
        p.write_text('255 0 0\n0 0 255\n')
        self.assertEqual(read_palette(p).shape,(2,3))

    def test_dataset_classic_is_aggregate_exact_and_adaptive_bounded(self):
        a = np.array([[[255,0,0],[255,0,0],[0,255,0]]],np.uint8)
        b = np.array([[[0,0,255],[0,0,255],[0,255,0]]],np.uint8)
        Image.fromarray(a).save(self.folder/'a.png')
        Image.fromarray(b).save(self.folder/'b.png')
        result = dataset_palette(self.folder, 2, strategy='frequency')
        self.assertEqual(result['palette'].tolist(),[[0,0,255],[0,255,0]])
        self.assertEqual(result['pixels'],6)
        adaptive = dataset_palette(self.folder, 3)
        self.assertEqual(adaptive['images'],2)
        self.assertEqual(adaptive['sample_pixels'],6)
        (self.folder/'broken.png').write_bytes(b'not an image')
        with self.assertRaisesRegex(ValueError,'broken.png'): dataset_palette(self.folder)

    def test_image_import_orientation_transparency_and_metadata(self):
        path = self.folder/'alpha.png'
        Image.new('RGBA',(2,3),(255,0,0,0)).save(path)
        self.assertTrue(np.all(load_rgb(path,'white')==255))
        self.assertTrue(np.all(load_rgb(path,'black')==0))
        np.testing.assert_array_equal(load_rgb(path,'ignore')[0,0], [255,0,0])
        image = Image.new('RGB',(3,2),'red'); exif=Image.Exif(); exif[274]=6; exif[270]='private description'
        image.save(path.with_suffix('.jpg'),exif=exif)
        rgb=load_rgb(path.with_suffix('.jpg'));self.assertEqual(rgb.shape,(3,2,3))
        with Image.open(BytesIO(png_bytes(rgb))) as output:self.assertFalse(output.getexif())
        Image.new('L',(MAX_PIXELS+1,1)).save(path)
        with self.assertRaisesRegex(ValueError,'exceeds'):load_rgb(path,resize=False)
        self.assertLessEqual(load_rgb(path).size//3,MAX_PIXELS)

    def test_multiframe_and_corrupt_images_rejected(self):
        path=self.folder/'animation.tiff'
        Image.new('RGB',(2,2)).save(path,save_all=True,append_images=[Image.new('RGB',(2,2),'red')])
        with self.assertRaisesRegex(ValueError,'still image'): load_rgb(path)
        path.write_bytes(b'bad')
        with self.assertRaises(OSError):load_rgb(path)

    def test_amplitude_and_entropy_roundtrip_including_last_nonzero(self):
        for value in range(-4095,4096):
            size=category(value)
            self.assertEqual(signed(amplitude(value,size),size),value)
        vectors=np.zeros((5,64),np.int32)
        vectors[:,0]=[0,100,-100,100,0]
        vectors[0,63]=-12;vectors[1,20]=1;vectors[2,17]=3;vectors[4,1]=14
        data,bits,lengths=encode_channels([vectors])
        reader=BitReader(data,bits,lengths)
        np.testing.assert_array_equal(decode_channel(reader,len(vectors)),vectors)
        self.assertEqual(reader.position,bits)
        self.assertEqual(huffman_lengths(Counter({1:10})),[[1,1]])
        with self.assertRaises(ValueError):canonical([[0,1],[1,1],[2,1]])
        with self.assertRaises(ValueError):canonical([[0,1],[0,2]])

    def test_mcs_stream_is_self_contained_odd_tiny_and_regular_sizes(self):
        for shape in [(1,1),(1,9),(9,1),(9,13),(16,16),(23,25)]:
            rgb=demo_image(width=shape[1],height=shape[0])
            for sampling in [False,True]:
                stream,stats=encode(rgb,80,sampling)
                reconstructed=decode(bytes(stream))
                self.assertEqual(reconstructed.shape,rgb.shape)
                self.assertEqual(stats['stream_file_bytes'],len(stream))
                self.assertEqual(stats['payload_bytes']+stats['metadata_and_checksum_bytes'],len(stream))
                np.testing.assert_array_equal(decode(stream),reconstructed)
        result=compress(demo_image(width=32,height=32))
        self.assertEqual(result['stats']['raw_to_stream_ratio'],result['image'].size/len(result['stream']))

    def test_mcs_integrity_and_bounded_header_validation(self):
        stream,_=encode(demo_image(width=9,height=9))
        for bad in [b'',stream[:-1],stream+b'junk',stream[:20]+bytes([stream[20]^1])+stream[21:]]:
            with self.assertRaises(ValueError):decode(bad)
        header,payload=parse_stream(stream)
        for changes in [{'width':MAX_PIXELS+1},{'height':True},{'sampling':1},{'quality':0},{'bit_count':1},{'huffman':[[0,1],[1,1],[2,1]]}]:
            metadata={**header,**changes};raw=json.dumps(metadata).encode()
            body=b'MCS1'+struct.pack('>I',len(raw))+raw+payload
            with self.assertRaises(ValueError):decode(body+hashlib.sha256(body).digest())

    def test_dct_study_full_reconstruction_and_quality_progression(self):
        rgb=demo_image(width=39,height=29)
        results=coefficient_study(rgb,[1,4,16,64])
        self.assertEqual(results[-1]['metrics']['mse'],0)
        errors=[r['metrics']['mse'] for r in results]
        self.assertGreater(errors[0],errors[2])
        for r in results:
            self.assertFalse(r['settings']['quantization'])
            self.assertNotIn('raw_to_stream_ratio',r['stats'])
        for bad in [[],[0],[65],[4,4],list(range(1,10))]:
            with self.assertRaises(ValueError):coefficient_study(rgb,bad)

    def test_real_jpeg_export_matches_measured_reconstruction(self):
        rgb=demo_image(width=71,height=49)
        low,high=standard_jpeg(rgb,20,False),standard_jpeg(rgb,95,False)
        self.assertLess(high['metrics']['mse'],low['metrics']['mse'])
        with Image.open(BytesIO(high['jpeg'])) as image:
            self.assertEqual(image.format,'JPEG')
            np.testing.assert_array_equal(np.array(image),high['image'])
        self.assertEqual(len(high['jpeg']),high['stats']['jpeg_file_bytes'])
        with self.assertRaises(ValueError):standard_jpeg(rgb,101)

    def test_block_inspection_and_quality_validation(self):
        rgb=demo_image(width=9,height=9)
        spatial,coefficients=block_details(rgb,1,1)
        np.testing.assert_allclose(idct(coefficients),spatial,atol=1e-12)
        with self.assertRaises(ValueError):block_details(rgb,2,0)
        self.assertTrue(np.all(quant_tables(100)[0]==1))
        for bad in [0,101,True,1.5]:
            with self.assertRaises(ValueError):quant_tables(bad)

    def test_exports_never_overwrite_existing_input(self):
        path=self.folder/'input.png';path.write_bytes(b'original')
        with self.assertRaises(FileExistsError):write_new(path,b'changed')
        self.assertEqual(path.read_bytes(),b'original')

    def test_representative_still_formats_and_thumbnail_budget(self):
        rgb=demo_image(width=31,height=21)
        for extension in ['png','jpg','bmp','tiff','webp']:
            path=self.folder/('sample.'+extension)
            Image.fromarray(rgb).save(path)
            loaded=load_rgb(path)
            self.assertEqual(loaded.shape,rgb.shape)
        path=self.folder/'gray.png';Image.new('L',(9,11),77).save(path)
        self.assertEqual(load_rgb(path).shape,(11,9,3))
        from media_studio.images import fit_size
        for w,h in [(50_000_000,1),(1,50_000_000),(8192,5461)]:
            a,b=fit_size(w,h,65_536)
            self.assertLessEqual(a*b,65_536)

    def test_adaptive_folder_accepts_large_sources_and_classic_is_explicit(self):
        Image.new('RGB',(2001,1001),(11,22,33)).save(self.folder/'large.png')
        result=dataset_palette(self.folder,16)
        self.assertLessEqual(result['pixels'],65_536)
        self.assertLessEqual(result['sample_pixels'],4096)
        self.assertEqual(result['palette'].tolist(),[[11,22,33]])
        with self.assertRaisesRegex(ValueError,'Adaptive'):
            dataset_palette(self.folder,16,strategy='frequency')


if __name__=='__main__':unittest.main()
