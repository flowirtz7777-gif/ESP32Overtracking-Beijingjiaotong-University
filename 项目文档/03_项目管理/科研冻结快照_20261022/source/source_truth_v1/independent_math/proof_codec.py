"""Deterministic tagged JSON + gzip codec for exact proof objects.

Supported values: None, bool, int, finite float, str, Fraction, list, tuple,
and dict with supported hashable keys. Integers are encoded as <=1000-digit
base-10 chunks; sys.set_int_max_str_digits is never changed.
"""
from fractions import Fraction
import gzip
import io
import json
import math

MAGIC = "proof-rational-json-gzip"
VERSION = 1
CHUNK_DIGITS = 1000
_BASE = 10 ** CHUNK_DIGITS


def _int_chunks(value):
    if type(value) is not int:
        raise TypeError("exact int required")
    if value == 0:
        return 0, ["0"]
    sign = -1 if value < 0 else 1
    value = abs(value)
    chunks = []
    while value:
        value, rem = divmod(value, _BASE)
        chunks.append(str(rem))
    chunks.reverse()
    for i in range(1, len(chunks)):
        chunks[i] = chunks[i].zfill(CHUNK_DIGITS)
    return sign, chunks


def _read_int(sign, chunks):
    if type(sign) is not int or sign not in (-1, 0, 1) or type(chunks) is not list or not chunks:
        raise ValueError("invalid integer encoding")
    if any(type(s) is not str or not s.isascii() or not s.isdigit() for s in chunks):
        raise ValueError("invalid integer chunks")
    if not (1 <= len(chunks[0]) <= CHUNK_DIGITS) or (len(chunks[0]) > 1 and chunks[0][0] == "0"):
        raise ValueError("noncanonical leading integer chunk")
    if any(len(s) != CHUNK_DIGITS for s in chunks[1:]):
        raise ValueError("noncanonical integer chunk width")
    if sign == 0:
        if chunks != ["0"]:
            raise ValueError("noncanonical zero")
        return 0
    if chunks[0] == "0":
        raise ValueError("noncanonical signed zero")
    value = 0
    for s in chunks:
        value = value * _BASE + int(s)
    return sign * value


def _encode_node(value, active):
    t = type(value)
    if value is None:
        return ["n"]
    if t is bool:
        return ["b", value]
    if t is int:
        sign, chunks = _int_chunks(value)
        return ["i", sign, chunks]
    if t is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite float is not encodable")
        return ["f", value.hex()]
    if t is str:
        return ["s", value]
    if t is Fraction:
        return ["q", _encode_node(value.numerator, active), _encode_node(value.denominator, active)]
    if t not in (list, tuple, dict):
        raise TypeError("unsupported proof value type: " + t.__name__)
    ident = id(value)
    if ident in active:
        raise ValueError("cyclic containers are not encodable")
    active.add(ident)
    try:
        if t is list:
            return ["l", [_encode_node(x, active) for x in value]]
        if t is tuple:
            return ["t", [_encode_node(x, active) for x in value]]
        return ["d", [[_encode_node(k, active), _encode_node(v, active)] for k, v in value.items()]]
    finally:
        active.remove(ident)


def _decode_node(node):
    if type(node) is not list or not node or type(node[0]) is not str:
        raise ValueError("malformed tagged node")
    tag = node[0]
    if tag == "n" and len(node) == 1:
        return None
    if tag == "b" and len(node) == 2 and type(node[1]) is bool:
        return node[1]
    if tag == "i" and len(node) == 3:
        return _read_int(node[1], node[2])
    if tag == "f" and len(node) == 2 and type(node[1]) is str:
        value = float.fromhex(node[1])
        if not math.isfinite(value) or value.hex() != node[1]:
            raise ValueError("noncanonical or nonfinite float")
        return value
    if tag == "s" and len(node) == 2 and type(node[1]) is str:
        return node[1]
    if tag == "q" and len(node) == 3:
        n, d = _decode_node(node[1]), _decode_node(node[2])
        if type(n) is not int or type(d) is not int or d <= 0:
            raise ValueError("invalid Fraction encoding")
        result = Fraction(n, d)
        if result.numerator != n or result.denominator != d:
            raise ValueError("noncanonical Fraction encoding")
        return result
    if tag in ("l", "t") and len(node) == 2 and type(node[1]) is list:
        values = [_decode_node(x) for x in node[1]]
        return values if tag == "l" else tuple(values)
    if tag == "d" and len(node) == 2 and type(node[1]) is list:
        result = {}
        for pair in node[1]:
            if type(pair) is not list or len(pair) != 2:
                raise ValueError("malformed dict pair")
            key, value = _decode_node(pair[0]), _decode_node(pair[1])
            try:
                if key in result:
                    raise ValueError("duplicate decoded dict key")
                result[key] = value
            except TypeError as exc:
                raise ValueError("decoded dict key is unhashable") from exc
        return result
    raise ValueError("unknown tag or invalid tagged node shape")


def encode(value):
    envelope = [MAGIC, VERSION, _encode_node(value, set())]
    raw = json.dumps(envelope, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    sink = io.BytesIO()
    with gzip.GzipFile(fileobj=sink, mode="wb", filename="", compresslevel=9, mtime=0) as stream:
        stream.write(raw)
    return sink.getvalue()


def decode(blob):
    if type(blob) is not bytes:
        raise TypeError("gzip bytes required")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as stream:
            raw = stream.read()
        envelope = json.loads(raw.decode("ascii"))
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid gzip/JSON proof blob") from exc
    if (type(envelope) is not list or len(envelope) != 3
            or envelope[0] != MAGIC or type(envelope[1]) is not int or envelope[1] != VERSION):
        raise ValueError("unsupported proof codec envelope")
    return _decode_node(envelope[2])
