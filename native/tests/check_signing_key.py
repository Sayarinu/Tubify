"""Exercise the actual macOS signing-key guard using RFC 8032 test vector 1."""
import base64
import importlib.util
import sys
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
        if len(sys.argv) > 1:
            spec = importlib.util.spec_from_file_location('sign_update', Path(__file__).resolve().parents[1]/'sign_update.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            archive = Path(folder)/'empty.bin'
            archive.write_bytes(b'')
            signature = module.sign_update(sys.argv[1], archive, secret)
            expected = bytes.fromhex('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
            assert base64.b64decode(signature) == expected, 'Vendor signature differs from RFC 8032 test vector 1'
            print('Actual Sparkle signing and verification passed RFC 8032 test vector 1.')
    print('Signing-key guard passed valid, whitespace, malformed and mismatched test vectors.')


if __name__ == '__main__':
    main()
