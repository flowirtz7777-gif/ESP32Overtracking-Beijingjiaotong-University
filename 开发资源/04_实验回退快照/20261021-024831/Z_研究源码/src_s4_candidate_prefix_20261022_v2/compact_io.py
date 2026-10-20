"""Lossless metadata encoding only; no geometric decisions or lossy transforms."""
import gzip
import io
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src_s4_candidate_prefix_20261022_v1'))
import candidate_driver as previous

base, r = previous.base, previous.r


def encode_record(raw):
    packed = gzip.compress(raw, mtime=0)
    if gzip.decompress(packed) != raw:
        raise RuntimeError('Lossless metadata byte roundtrip failed')
    record = json.loads(raw)
    stub = {'format': 'complete-original-metadata-gzip-v1', 'metadata_sha256': r.sha(raw),
            'metadata_gzip_sha256': r.sha(packed), 'metadata_bytes': len(raw),
            'npz_sha256': record['npz_sha256'], 'summary': record['summary']}
    return stub, packed


def decode_record(stub, packed):
    if (set(stub) != {'format', 'metadata_sha256', 'metadata_gzip_sha256', 'metadata_bytes', 'npz_sha256', 'summary'}
            or stub['format'] != 'complete-original-metadata-gzip-v1' or r.sha(packed) != stub['metadata_gzip_sha256']):
        raise RuntimeError('Metadata manifest or gzip signature differs')
    raw = gzip.decompress(packed)
    if len(raw) != stub['metadata_bytes'] or r.sha(raw) != stub['metadata_sha256']:
        raise RuntimeError('Complete decompressed metadata differs')
    record = json.loads(raw)
    if record['npz_sha256'] != stub['npz_sha256'] or record['summary'] != stub['summary']:
        raise RuntimeError('Manifest/body binding differs')
    return raw, record


def save_encoded(folder, blob, raw):
    stub, packed = encode_record(raw)
    decoded, record = decode_record(stub, packed)
    r.require(decoded == raw and record['npz_sha256'] == r.sha(blob), 'Original NPZ/metadata binding differs')
    r.batch([(folder / 'arrays.npz', blob), (folder / 'metadata.json.gz', packed),
             (folder / 'result.json', r.encoded(stub))])
    return {'result_sha256': r.file_hash(folder / 'result.json'), 'summary': record['summary']}


def save_arrays(folder, arrays, record):
    blob = base.npz_bytes(arrays)
    raw = r.encoded({**record, 'arrays': base.array_meta(arrays), 'npz_sha256': r.sha(blob)})
    return save_encoded(folder, blob, raw)


def read_arrays(folder):
    stub = r.read(folder / 'result.json')
    raw, record = decode_record(stub, (folder / 'metadata.json.gz').read_bytes())
    blob = (folder / 'arrays.npz').read_bytes()
    r.require(r.sha(blob) == record['npz_sha256'], 'Complete NPZ signature differs')
    with np.load(io.BytesIO(blob), allow_pickle=False) as z:
        arrays = {name: z[name] for name in z.files}
    r.require(base.array_meta(arrays) == record['arrays'], 'Every decoded array/dtype/NaN must remain exact')
    return arrays, record


def reuse(folder, origin):
    blob, raw = (origin / 'arrays.npz').read_bytes(), (origin / 'result.json').read_bytes()
    entry = save_encoded(folder, blob, raw)
    decoded, _ = decode_record(r.read(folder / 'result.json'), (folder / 'metadata.json.gz').read_bytes())
    r.require(decoded == raw and (folder / 'arrays.npz').read_bytes() == blob, 'Original full proof bytes changed')
    return entry
