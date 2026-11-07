"""Numerical protocol unit fixtures only, not ESP32 logs or ECG evidence."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import compare_operator_trace as trace


def wire(body):
    return body+' line_fnv='+trace.fnv(body.encode('ascii'))


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='trace_protocol_unit_')
        self.addCleanup(self.temp.cleanup)
        folder=Path(self.temp.name)
        self.ref=folder/'unit_reference.json';self.log=folder/'unit.log';self.out=folder/'unit_report.json'
        self.values=[bytes(range(37)),b'\x07']
        self.expected={'sample':5,'input_fnv':'unit_input','model_sha256':'unit_model','samples_sha256':'unit_samples',
            'operators':[{'op':i,'tag':'UNIT_TEST','version':1,'tensor':i+15,'bytes':len(raw),
                          'hex':raw.hex(),'scale':1.0,'zero':0} for i,raw in enumerate(self.values)]}
        self.ref.write_text(json.dumps(self.expected))
        self.lines=self.fixture(self.values)

    def fixture(self,values):
        lines=['UNIT_FIXTURE_NOT_HARDWARE',
               'ECG_ASSETS model_sha256=unit_model samples_sha256=unit_samples verified=1',
               wire(f'ECG_TRACE_BEGIN protocol=2 sample=5 input_fnv=unit_input nodes=2 model_schema=3 chunk_bytes=16 bytes_total=38 status=CAPTURED')]
        chunks=0
        for i,raw in enumerate(values):
            lines.append(wire(f'ECG_TRACE_TENSOR sample=5 op={i} tag=UNIT_TEST version=1 tensor={i+15} bytes={len(raw)} fnv={trace.fnv(raw)} scale=1 zero=0'))
            for offset in range(0,len(raw),16):
                chunk=raw[offset:offset+16];chunks+=1
                lines.append(wire(f'ECG_TRACE_DATA sample=5 op={i} tensor={i+15} offset={offset} nbytes={len(chunk)} hex_chars={2*len(chunk)} chunk_fnv={trace.fnv(chunk)} hex={chunk.hex()}'))
        lines.append(wire(f'ECG_TRACE_END sample=5 nodes=2 bytes_total=38 chunks_total={chunks} stream_fnv={trace.fnv(b"".join(values))} generation_errors=0 write_errors=0 status=COMPLETE'))
        lines.append(wire(f'ECG_TRACE_RESULT sample=5 code={values[-1][0]} invoke_ok=1 trace_ok=1 write_errors=0'))
        return lines

    def run_compare(self,lines):
        self.log.write_text('\n'.join(lines)+'\n')
        with contextlib.redirect_stdout(io.StringIO()):
            trace.compare(self.ref,self.log,self.out)
        return json.loads(self.out.read_text())

    def mutate(self,marker,old,new,rehash=True):
        lines=list(self.lines);index=next(i for i,l in enumerate(lines) if marker in l)
        body=lines[index].split(' line_fnv=')[0].replace(old,new,1)
        lines[index]=wire(body) if rehash else lines[index].replace(old,new,1)
        return lines

    def test_valid_protocol(self):
        self.assertEqual(self.run_compare(self.lines)['status'],'ALL_TRACED_TENSORS_EXACT')

    def test_real_numerical_difference_kept(self):
        r=self.run_compare(self.fixture([bytes([99])+self.values[0][1:],b'\x07']))
        self.assertEqual(r['status'],'FIRST_DIVERGENCE_LOCATED')
        self.assertEqual(r['first_divergence']['op'],0)

    def test_one_character_missing(self):
        lines=self.mutate('ECG_TRACE_DATA','hex=000102','hex=00102',False)
        with self.assertRaisesRegex(ValueError,'line checksum'):self.run_compare(lines)

    def test_literal_field_character_missing(self):
        # The real old log also contains "ffset=960" instead of "offset=960".
        lines=self.mutate('ECG_TRACE_DATA','offset=0','ffset=0',False)
        with self.assertRaisesRegex(ValueError,'line checksum'):self.run_compare(lines)

    def test_odd_hex_rejected_even_with_valid_line_hash(self):
        with self.assertRaisesRegex(ValueError,'HEX length'):
            self.run_compare(self.mutate('ECG_TRACE_DATA','hex=000102','hex=00102'))

    def test_even_length_byte_loss(self):
        with self.assertRaisesRegex(ValueError,'HEX length'):
            self.run_compare(self.mutate('ECG_TRACE_DATA','hex=000102','hex=0102'))

    def test_marker_missing(self):
        for marker in ['ECG_TRACE_BEGIN','ECG_TRACE_END','ECG_TRACE_RESULT']:
            with self.subTest(marker=marker),self.assertRaises(ValueError):
                self.run_compare([l for l in self.lines if marker not in l])

    def test_duplicate_chunk(self):
        lines=list(self.lines);i=next(i for i,l in enumerate(lines) if 'ECG_TRACE_DATA' in l)
        lines.insert(i,lines[i])
        with self.assertRaisesRegex(ValueError,'Duplicate chunk'):self.run_compare(lines)

    def test_missing_chunk(self):
        lines=[l for l in self.lines if not ('ECG_TRACE_DATA' in l and 'offset=16 ' in l)]
        with self.assertRaises(ValueError):self.run_compare(lines)

    def test_chunk_checksum(self):
        with self.assertRaisesRegex(ValueError,'chunk checksum'):
            self.run_compare(self.mutate('ECG_TRACE_DATA','hex=000102','hex=990102'))

    def test_tensor_checksum(self):
        h=trace.fnv(self.values[0])
        with self.assertRaisesRegex(ValueError,'tensor'):
            self.run_compare(self.mutate('ECG_TRACE_TENSOR','fnv='+h,'fnv=00000000'))

    def test_stream_checksum(self):
        h=trace.fnv(b''.join(self.values))
        with self.assertRaisesRegex(ValueError,'stream checksum'):
            self.run_compare(self.mutate('ECG_TRACE_END','stream_fnv='+h,'stream_fnv=00000000'))

    def test_result_code(self):
        with self.assertRaisesRegex(ValueError,'RESULT code'):
            self.run_compare(self.mutate('ECG_TRACE_RESULT','code=7','code=0'))

    def test_firmware_write_failure(self):
        with self.assertRaisesRegex(ValueError,'transport failure'):
            self.run_compare(self.mutate('ECG_TRACE_END','write_errors=0','write_errors=1'))


if __name__=='__main__':
    unittest.main()
