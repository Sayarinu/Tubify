"""Adapt our seed/public pair to Sparkle's seed-only stdin format."""
import base64
import binascii
import os
from pathlib import Path
import subprocess
import sys


def sign_update(tool, archive, encoded, run=subprocess.run):
    try:
        pair = base64.b64decode(encoded.strip(), validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Invalid update signing key encoding.') from None
    if len(pair) != 64:
        raise ValueError('Expected an Ed25519 seed/public-key pair.')
    # Sparkle 2.10.1 accepts a 32-byte seed, not the 64-byte seed/public pair.
    seed = base64.b64encode(pair[:32]) + b'\n'
    args = [str(tool), '--ed-key-file', '-']
    result = run([*args, '-p', str(archive)], input=seed, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError('Sparkle could not sign the update archive.')
    signature = result.stdout.strip()
    try:
        if len(base64.b64decode(signature, validate=True)) != 64:
            raise ValueError()
        signature = signature.decode('ascii')
    except (ValueError, binascii.Error, UnicodeError):
        raise RuntimeError('Sparkle returned an invalid update signature.') from None
    verified = run([*args, '--verify', str(archive), signature], input=seed, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if verified.returncode != 0:
        raise RuntimeError('Sparkle update signature verification failed.')
    return signature


if __name__ == '__main__':
    try:
        print(sign_update(Path(sys.argv[1]), Path(sys.argv[2]), os.environ['TUBIFY_SPARKLE_PRIVATE_KEY']))
    except (ValueError, RuntimeError, OSError, KeyError):
        # Vendor diagnostics can contain key material; never relay raw output.
        print('Update signing failed. Check the key, signing tool and archive.', file=sys.stderr)
        raise SystemExit(1)
