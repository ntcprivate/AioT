"""Byte-exact, bounded backup of every sector the bench images may touch."""
import hashlib,json
from pathlib import Path

def snapshot_flash(output,command,length=0x70000):
    output=Path(output);data=bytearray();parts=[]
    for offset in range(0,length,0x10000):
        size=min(0x10000,length-offset);file=output/f'backup_{offset:06x}.bin'
        command(['read_flash',hex(offset),hex(size),file],output/f'backup_{offset:06x}.log',timeout=45)
        raw=file.read_bytes()
        if len(raw)!=size:raise RuntimeError('Incomplete flash backup; refusing to flash')
        parts.append(dict(offset=offset,length=size,sha256=hashlib.sha256(raw).hexdigest()));data.extend(raw)
    image=output/'pre_test_touched_flash.bin';image.write_bytes(data)
    meta=dict(offset=0,length=len(data),sha256=hashlib.sha256(data).hexdigest(),parts=parts,verification='Each read verified by esptool MD5')
    (output/'backup_manifest.json').write_text(json.dumps(meta,indent=2));return image,meta
