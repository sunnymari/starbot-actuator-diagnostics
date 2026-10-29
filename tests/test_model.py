import json
from pathlib import Path
import struct
import unittest

from sim.actuator import JOINTS


class ModelTests(unittest.TestCase):
    def test_all_actuators_have_embedded_model_anchors_and_textures(self):
        data=(Path(__file__).resolve().parents[1]/'viz/web/robot.glb').read_bytes()
        magic,version,size=struct.unpack_from('<4sII',data)
        self.assertEqual((magic,version,size),(b'glTF',2,len(data)))
        length,kind=struct.unpack_from('<I4s',data,12)
        self.assertEqual(kind,b'JSON')
        model=json.loads(data[20:20+length])
        names={n['name'] for n in model['nodes']}
        self.assertTrue({j.name for j in JOINTS}.issubset(names))
        self.assertTrue(all('bufferView' in image for image in model['images']))
        self.assertLess(size,20_000_000)
