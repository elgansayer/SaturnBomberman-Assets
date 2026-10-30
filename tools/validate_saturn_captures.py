"""Check private RGB capture bytes; provenance declarations need host evidence."""
import binascii
import hashlib
import json
from pathlib import Path
import struct
import zlib


def sha(value):
    return hashlib.sha256(value).hexdigest()


def validate(directory):
    meta = json.loads((directory / 'provenance.json').read_text())
    assert meta['schema'] == 'neptune.private-rgb-capture.v1'
    assert meta['image'] == 'source-pattern.png'
    assert 0 < meta['width'] <= 512 and 0 < meta['height'] <= 512
    raw = (directory / meta['image']).read_bytes()
    assert len(raw) <= 2 * 1024**2 and sha(raw) == meta['png_sha256']
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    cursor, packed, header, ended = 8, bytearray(), None, False
    while cursor < len(raw):
        assert not ended and cursor + 12 <= len(raw)
        size = struct.unpack_from('>I', raw, cursor)[0]
        assert cursor + size + 12 <= len(raw)
        tag, data = raw[cursor+4:cursor+8], raw[cursor+8:cursor+8+size]
        assert binascii.crc32(tag + data) & 0xffffffff == struct.unpack_from('>I', raw, cursor+8+size)[0]
        if tag == b'IHDR':
            assert header is None and cursor == 8
            header = struct.unpack('>IIBBBBB', data)
        elif tag == b'IDAT':
            assert header is not None
            packed.extend(data)
        elif tag == b'IEND':
            assert not data
            ended = True
        else:
            raise ValueError('Unsupported source-pattern PNG chunk')
        cursor += size + 12
    width, height = meta['width'], meta['height']
    assert ended and header == (width, height, 8, 6, 0, 0, 0)
    limit = height * (1 + width * 4)
    inflater = zlib.decompressobj()
    data = inflater.decompress(packed, limit + 1)
    assert len(data) == limit and inflater.eof and not inflater.unused_data
    pixels, words = bytearray(), []
    for row in range(height):
        start = row * (1 + width * 4)
        assert data[start] == 0
        pixels.extend(data[start+1:start+1+width*4])
    assert sha(pixels) == meta['rgba_sha256']
    for offset in range(0, len(pixels), 4):
        r, g, b, alpha = pixels[offset:offset+4]
        assert alpha in (0, 255)
        assert all(channel == 8*(channel >> 3) + (channel >> 3)//4 for channel in (r, g, b))
        assert alpha or not (r or g or b)
        words.append(0 if not alpha else 0x8000 | (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10))
    native = struct.pack('>' + str(len(words)) + 'H', *words)
    assert sha(native) == meta['native_words_sha256']
    assert meta['source_span']['bytes'] == len(native)
    return {'directory': str(directory), 'pixels': len(words), 'native_sha256': sha(native)}


if __name__ == '__main__':
    roots = sorted(Path('saturn').glob('*/runtime-captures/*/*/provenance.json'))
    if not 0 < len(roots) <= 1000:
        raise SystemExit('A bounded non-empty capture selection is required')
    for record in roots:
        print(json.dumps(validate(record.parent)))
