import base64
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('sign_update', Path(__file__).resolve().parents[1]/'sign_update.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PAIR = bytes(range(64))
KEY = base64.b64encode(PAIR).decode()
SIGNATURE = base64.b64encode(b's'*64)


def test_only_seed_is_sent_on_stdin_and_signature_is_verified():
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert kwargs['input'] == base64.b64encode(PAIR[:32])+b'\n'
        assert KEY not in args
        return SimpleNamespace(returncode=0, stdout=SIGNATURE+b'\n')
    assert module.sign_update('tool', 'archive.dmg', '\n'+KEY+'\n', run) == SIGNATURE.decode()
    assert calls[1] == ['tool', '--ed-key-file', '-', '--verify', 'archive.dmg', SIGNATURE.decode()]


@pytest.mark.parametrize('key', ['invalid', base64.b64encode(b'short').decode()])
def test_invalid_key_never_launches_signer(key):
    with pytest.raises(ValueError):
        module.sign_update('tool', 'archive', key, lambda *a, **k: pytest.fail('No signing with invalid keys'))


def test_vendor_errors_never_relay_secret_material():
    def run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout=KEY.encode(), stderr=KEY.encode())
    with pytest.raises(RuntimeError) as result:
        module.sign_update('tool', 'archive', KEY, run)
    assert KEY not in str(result.value)


def test_invalid_signature_is_not_published():
    with pytest.raises(RuntimeError):
        module.sign_update('tool', 'archive', KEY, lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'bad signature'))


def test_failed_signature_verification_is_not_published():
    calls = []
    def run(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(returncode=0 if len(calls) == 1 else 1, stdout=SIGNATURE)
    with pytest.raises(RuntimeError):
        module.sign_update('tool', 'archive', KEY, run)
