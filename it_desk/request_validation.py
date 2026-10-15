"""Bound HTTP and NPZ inputs before allocating inference arrays."""
import io
import zipfile

MAX_BYTES = 2_000_000

def read_payload(headers, stream):
    lengths = headers.get_all('Content-Length', [])
    if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
        raise ValueError('Invalid Content-Length')
    if headers.get('Transfer-Encoding') is not None:
        raise ValueError('Transfer-Encoding is unsupported')
    size = int(lengths[0])
    if not 0 < size <= MAX_BYTES:
        raise ValueError('Invalid body size')
    payload = stream.read(size)
    if len(payload) != size:
        raise ValueError('Truncated request')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        expected = {'q.npy', 'top.npy', 'side.npy', 'target.npy', 'noise_seed.npy'}
        if len(entries) != len(expected) or {x.filename for x in entries} != expected:
            raise ValueError('Invalid array fields')
        if sum(x.file_size for x in entries) > MAX_BYTES:
            raise ValueError('Expanded arrays too large')
        if any(x.flag_bits & 1 for x in entries):
            raise ValueError('Encrypted arrays are unsupported')
    return payload
