"""Exercise the actual macOS signing-key guard using RFC 8032 test vector 1."""
import base64
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    seed = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
    public = bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
    secret = base64.b64encode(seed + public).decode()
    guard = Path(__file__).resolve().parents[2] / 'scripts/check-sparkle-key.swift'
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'public.txt'
        path.write_text(base64.b64encode(public).decode()+'\n')
        for value, valid in [(secret, True), (' \n'+secret+'\n', True), ('invalid', False), (base64.b64encode(b'x'*64).decode(), False)]:
            result = subprocess.run(['swift', str(guard), str(path)], env={**os.environ, 'TUBIFY_SPARKLE_PRIVATE_KEY':value}, capture_output=True, text=True)
            assert (result.returncode == 0) == valid, result.stderr
            assert not result.stdout
    print('Signing-key guard passed valid, whitespace, malformed and mismatched test vectors.')


if __name__ == '__main__':
    main()
