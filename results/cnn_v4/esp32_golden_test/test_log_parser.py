"""Synthetic parser tests only. Never evidence of device golden PASS."""
import json,unittest
from pathlib import Path
from verify_board_log import verify
class ParserTests(unittest.TestCase):
 def setUp(self):
  self.meta=json.loads((Path(__file__).parent/'fixtures.json').read_text());m=self.meta
  rows=['V4_GOLDEN_BEGIN source=STATIC_FIXTURES',f"V4_GOLDEN_MODEL sha256={m['model_sha256']} arena_allocated=65536 arena_used=6124"]
  for f in m['fixtures']:
   c=f['reference_code'];rows.append(f"V4_GOLDEN_SAMPLE i={f['fixture']} code={c} reference={c} probability={(c+128)/256:.9f} predicted={int(c>=98)} expected_predicted={int(c>=98)} delta=0 prep_exact=1 inference_us=100 status=EXACT")
  rows.extend(['V4_GOLDEN_MEMORY arena_used=6124 arena_allocated=65536',f"V4_GOLDEN_RESULT status=PASS exact={m['count']} total={m['count']} prep_exact={m['count']} max_code_delta=0 model_sha256={m['model_sha256']}",'V4_GOLDEN_END']);self.text='\n'.join(rows)
 def test_complete_synthetic(self):self.assertEqual(verify(self.text,self.meta)['exact'],self.meta['count'])
 def test_missing_end(self):
  with self.assertRaises(AssertionError):verify(self.text.replace('V4_GOLDEN_END',''),self.meta)
 def test_missing_sample(self):
  with self.assertRaises(AssertionError):verify('\n'.join(x for x in self.text.splitlines() if 'SAMPLE i=0 ' not in x),self.meta)
 def test_corrupt_output(self):
  with self.assertRaises(AssertionError):verify(self.text.replace('code=-120','code=-12',1),self.meta)
 def test_wrong_model_hash(self):
  with self.assertRaises(AssertionError):verify(self.text.replace(self.meta['model_sha256'],'wrong'),self.meta)
if __name__=='__main__':unittest.main()
