import json
import unittest
import zlib
from capture_v4_adc_uart import inspect_line


class ParserTests(unittest.TestCase):
    def frame(self):
        b=json.dumps({'type':'status','source':'HARDWARE'}).encode()
        return b'ECG1 '+format(zlib.crc32(b),'08x').encode()+b' '+b

    def test_valid(self):
        self.assertEqual(inspect_line(self.frame())['source'],'HARDWARE')

    def test_changed_payload_rejected(self):
        with self.assertRaises(ValueError): inspect_line(self.frame()[:-1]+b'!')

    def test_non_frame(self):
        self.assertIsNone(inspect_line(b'boot log'))

    def test_missing_checksum_character(self):
        with self.assertRaises(ValueError): inspect_line(self.frame()[:5]+self.frame()[6:])


if __name__=='__main__': unittest.main()
