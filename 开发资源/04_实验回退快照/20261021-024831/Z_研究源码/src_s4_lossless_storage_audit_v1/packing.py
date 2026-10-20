from __future__ import annotations

import hashlib
import numpy as np


def array_hash(value):
    value = np.ascontiguousarray(value)
    sha = hashlib.sha256(str((value.dtype.str, value.shape)).encode('ascii'))
    sha.update(value.tobytes())
    return sha.hexdigest()


def unsigned_type(maximum):
    if maximum < 0:
        raise ValueError('Unsigned payload requires nonnegative values')
    for dtype in (np.uint16, np.uint32, np.uint64):
        if maximum <= np.iinfo(dtype).max:
            return dtype
    raise ValueError('Integer value outside lossless unsigned range')


def pack_points(arrays, time):
    time = np.asarray(time)
    if time.ndim != 1 or not len(time) or not np.isfinite(time).all() or not np.all(np.diff(time) > 0):
        raise ValueError('Strictly increasing finite observation times required')
    packed, metadata = {}, {'time_sha256': array_hash(time), 'arrays': {}}
    for name, original in arrays.items():
        value = np.asarray(original)
        if value.ndim != 1:
            raise ValueError('Per-target arrays must be one-dimensional')
        record = {'dtype': value.dtype.str, 'shape': list(value.shape), 'array_sha256': array_hash(value)}
        if name.endswith(('_raw', '_first', '_valid')):
            if value.dtype.kind != 'f' or np.isinf(value).any():
                raise ValueError('Alarm times must be floating observation times or NaN')
            dtype = unsigned_type(len(time))
            sentinel = np.iinfo(dtype).max
            result = np.full(value.shape, sentinel, dtype=dtype)
            finite = np.isfinite(value)
            indices = np.searchsorted(time, value[finite])
            if np.any(indices >= len(time)) or not np.array_equal(time[indices], value[finite]):
                raise ValueError('Alarm timestamp is not an exact observation time')
            result[finite] = indices
            record.update(kind='observation_index', sentinel=int(sentinel))
        else:
            if value.dtype.kind not in 'iu' or np.any(value < 0):
                raise ValueError('Confusion/support counts must be nonnegative integers')
            result = value.astype(unsigned_type(int(value.max()) if len(value) else 0))
            record.update(kind='integer_count')
        packed[name], metadata['arrays'][name] = result, record
    restored = unpack_points(packed, metadata, time)
    if any(array_hash(restored[key]) != array_hash(value) for key, value in arrays.items()):
        raise AssertionError('Packing is not byte-exact; preserve original arrays')
    return packed, metadata


def unpack_points(packed, metadata, time):
    time = np.asarray(time)
    if array_hash(time) != metadata['time_sha256'] or set(packed) != set(metadata['arrays']):
        raise AssertionError('Time reference or array inventory changed')
    arrays = {}
    for name, record in metadata['arrays'].items():
        value = np.asarray(packed[name])
        if list(value.shape) != record['shape'] or value.dtype.kind != 'u':
            raise AssertionError('Packed shape or integer representation changed')
        if record['kind'] == 'observation_index':
            result = np.full(value.shape, np.nan, dtype=np.dtype(record['dtype']))
            finite = value != record['sentinel']
            if np.any(value[finite] >= len(time)):
                raise AssertionError('Observation index outside frozen reference')
            result[finite] = time[value[finite]]
        elif record['kind'] == 'integer_count':
            result = value.astype(np.dtype(record['dtype']))
        else:
            raise AssertionError('Unknown lossless representation')
        if array_hash(result) != record['array_sha256']:
            raise AssertionError('Reconstructed per-point bytes differ from original')
        arrays[name] = result
    return arrays
