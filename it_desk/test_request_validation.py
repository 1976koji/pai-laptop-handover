import io
import unittest
import zipfile
from email.message import Message
from request_validation import read_payload

def headers(value):
    h=Message();h['Content-Length']=value;return h

def body(large=False):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in ('q','top','side','target','noise_seed'):
            z.writestr(name+'.npy',b'0'*(2_000_001 if large and name=='q' else 8))
    return b.getvalue()

class RequestTests(unittest.TestCase):
    def test_accept_bounded_container(self):
        b=body();self.assertEqual(read_payload(headers(str(len(b))),io.BytesIO(b)),b)
    def test_invalid_lengths(self):
        for value in ('-1','0','2000001','abc'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                read_payload(headers(value),io.BytesIO())
    def test_ambiguous_headers(self):
        h=headers('10');h['Content-Length']='10'
        with self.assertRaises(ValueError):read_payload(h,io.BytesIO())
        h=headers('10');h['Transfer-Encoding']='chunked'
        with self.assertRaises(ValueError):read_payload(h,io.BytesIO())
    def test_truncated(self):
        with self.assertRaises(ValueError):read_payload(headers('10'),io.BytesIO(b'x'))
    def test_expansion_limit(self):
        b=body(True)
        with self.assertRaises(ValueError):read_payload(headers(str(len(b))),io.BytesIO(b))
if __name__=='__main__':unittest.main()
