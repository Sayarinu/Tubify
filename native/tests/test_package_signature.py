import base64

from Cryptodome.PublicKey import ECC

from tubify.updates import package_signature


def keys():
    key = ECC.generate(curve="ed25519")
    public = key.public_key().export_key(format="raw")
    return base64.b64encode(key.seed + public).decode(), base64.b64encode(public).decode()


def test_signed_package_verifies_and_any_change_is_rejected():
    pair, public = keys()
    other_pair, other_public = keys()
    signature = package_signature.sign(b"package bytes", pair)
    assert package_signature.verify(b"package bytes", signature, public)
    assert not package_signature.verify(b"package bytez", signature, public)
    assert not package_signature.verify(b"package bytes", signature, other_public)
    assert not package_signature.verify(b"package bytes", package_signature.sign(b"package bytes", other_pair), public)
    assert not package_signature.verify(b"package bytes", "not base64!", public)


def test_signing_rejects_a_pair_whose_halves_do_not_match():
    pair, _ = keys()
    other, _ = keys()
    mixed = base64.b64encode(base64.b64decode(pair)[:32] + base64.b64decode(other)[32:]).decode()
    for value in (mixed, "short", ""):
        try:
            package_signature.sign(b"data", value)
        except ValueError:
            continue
        raise AssertionError("an invalid key signed")


def test_ci_signing_writes_a_verified_signature_file_without_echoing_the_key(tmp_path, monkeypatch, capsys):
    pair, public = keys()
    package = tmp_path / "Tubify-1.0.0-linux-x86_64.pkg.tar.zst"
    package.write_bytes(b"package")
    key_file = tmp_path / "public.txt"
    key_file.write_text(public + "\n")
    monkeypatch.setenv("TUBIFY_SPARKLE_PRIVATE_KEY", pair)
    assert package_signature.main(["sign", str(package), str(key_file)]) == 0
    assert package_signature.verify(b"package", (tmp_path / (package.name + ".sig")).read_text(), public)
    _, other_public = keys()
    key_file.write_text(other_public)
    assert package_signature.main(["sign", str(package), str(key_file)]) == 1
    assert pair not in capsys.readouterr().err
