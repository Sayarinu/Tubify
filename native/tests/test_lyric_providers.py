"""Provider fixtures are original test text, never a claim of live song coverage."""

import json
from types import SimpleNamespace

import pytest

from youtube_music_native import lyric_formats as formats
from youtube_music_native.lyric_data import Lyrics, valid_cached
from youtube_music_native.lyric_options import clean_options
from youtube_music_native.lyric_providers import Providers, ProviderUnavailable, provider_key

VIDEO = "abcdefghijk"
TRACK = {"title": "Fixture Song", "artist": "Fixture Artist", "album": "Fixture Album", "duration": 20}
TTML = '<tt xmlns="http://www.w3.org/ns/ttml"><body><div><p begin="0:01.250" end="00:00:06.000"><span begin="1.25s" end="3s">Hello</span> <span begin="3s" end="6s">world</span></p></div></body></tt>'


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.status_code, self.headers, self.closed = status, headers or {}, False

    def iter_content(self, size):
        yield self.body

    def close(self):
        self.closed = True


def get_for(body, status=200):
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(body, status)
    return get, calls


def document(provider="lrclib", timed=True):
    return {**(formats.lrc("[00:01.25]Original fixture\n[00:05.00]Second fixture", 20) if timed else formats.plain("Original plain fixture")), "videoId": VIDEO, "source": provider, "provider": provider}


def native_client(timed=False):
    value = {"lyrics": [{"text": "Native fixture", "start_time": 1000, "end_time": 2000}]} if timed else {"lyrics": "Native plain fixture"}
    return SimpleNamespace(catalog=lambda: SimpleNamespace(get_watch_playlist=lambda **kwargs: {"lyrics": "MPLYfixture"}, get_lyrics=lambda *args, **kwargs: value))


def test_format_timestamps_and_real_word_spaces():
    result = formats.ttml(TTML)
    assert result["timed"] and result["syncLevel"] == "word"
    assert result["lines"] == [{"text": "Hello world", "start": 1.25, "end": 6., "words": [
        {"text": "Hello", "offset": 0, "start": 1.25, "end": 3., "syllable": False},
        {"text": "world", "offset": 6, "start": 3., "end": 6., "syllable": False},
    ]}]
    assert formats.seconds("01:02:03.456") == 3723.456
    assert formats.seconds("1250ms") == 1.25
    lrc = formats.lrc("[ar:Fixture Artist]\n[ti:Fixture Song]\n[00:01.25][00:06.00]Original\n[00:04.50]Fixture", 20)
    assert [(row["start"], row["end"]) for row in lrc["lines"]] == [(1.25, 4.5), (4.5, 6.), (6., 20)]
    assert lrc["syncLevel"] == "line" and not any(row.get("words") for row in lrc["lines"])
    assert lrc["identity"] == {"artist": "Fixture Artist", "title": "Fixture Song"}


def test_nested_syllables_and_background_wrappers_keep_supplied_timing():
    text = '<tt xmlns:ttm="http://www.w3.org/ns/ttml#metadata"><p begin="0" end="4"><span begin="0" end="2"><span begin="0" end="1">Hel</span><span begin="1" end="2">lo</span></span> <span ttm:role="x-bg"><span begin="2" end="4">world</span></span></p></tt>'
    result = formats.ttml(text)
    assert result["syncLevel"] == "syllable"
    assert result["lines"][0]["text"] == "Hello world"
    assert [word["text"] for word in result["lines"][0]["words"]] == ["Hel", "lo", "world"]
    assert [word["syllable"] for word in result["lines"][0]["words"]] == [True, True, False]


@pytest.mark.parametrize("text", ['<!DOCTYPE tt [<!ENTITY x "bad">]><tt/>', '<tt><p begin="nan" end="2">Fixture</p></tt>', '<tt><p>Fixture</p></tt>'])
def test_invalid_xml_or_missing_timing_never_creates_word_timing(text):
    if "DOCTYPE" in text:
        with pytest.raises(ValueError):
            formats.ttml(text)
    else:
        result = formats.ttml(text)
        assert not result["timed"] and result["syncLevel"] == "plain"


def test_lrc_timestamps_inside_text_and_ttml_line_breaks_remain_text():
    result = formats.lrc("[00:01.00]Original [02:00] label", 10)
    assert len(result["lines"]) == 1 and result["lines"][0]["text"] == "Original [02:00] label"
    result = formats.ttml('<tt><p begin="0" end="3">Original<br/>fixture</p></tt>')
    assert result["lines"][0]["text"] == "Original\nfixture" and result["syncLevel"] == "line"


def test_invalid_individual_cues_do_not_discard_other_genuine_timing():
    result = formats.lrc("[00:01.00]Hello\n[00:03.00]", 3)
    assert result["timed"] and result["lines"] == [{"text": "Hello", "start": 1., "end": 3.}]
    result = formats.lrc("[99999:00]Invalid\n[00:01]Hello\n[00:03]Invalid terminal", 3)
    assert result["timed"] and [row["text"] for row in result["lines"]] == ["Hello"]
    result = formats.ttml('<tt><p begin="0" end="3"><span begin="bad" end="2">Hello</span></p><p begin="3" end="3"/><p begin="bad" end="4">Invalid cue</p></tt>')
    assert result["timed"] and result["syncLevel"] == "line"
    assert result["lines"] == [{"text": "Hello", "start": 0., "end": 3., "words": []}]


def test_document_size_and_cache_word_bounds_are_checked():
    with pytest.raises(ValueError):
        formats.ttml("x" * (formats.MAX_DOCUMENT + 1))
    value = {**formats.ttml(TTML), "videoId": VIDEO, "source": "Fixture"}
    assert valid_cached(value, VIDEO)
    value["lines"][0]["words"][0]["end"] = 999
    assert not valid_cached(value, VIDEO)


def test_provider_defaults_are_private_and_option_order_is_sanitized():
    options = clean_options({})
    assert not any(options[key] for key in ("external", "captions", "approximate", "timestamps", "autoOpen"))
    assert options["style"] == "line"
    assert [row["id"] for row in options["providers"]] == ["lrclib", "unison", "better"]
    configured = clean_options({"providers": [{"id": "better", "enabled": False}, {"id": "better", "enabled": True}, {"id": "untrusted", "enabled": True}], "external": "yes"})
    assert configured["providers"][0] == {"id": "better", "enabled": False} and not configured["external"]


def test_lrclib_endpoint_and_exact_recording_check():
    body = {"trackName": TRACK["title"], "artistName": TRACK["artist"], "albumName": TRACK["album"], "duration": 21, "syncedLyrics": "[00:01.25]Original fixture"}
    get, calls = get_for(body)
    result = Providers(http_get=get).fetch("lrclib", VIDEO, TRACK)
    assert result["timed"] and result["match"] == "exact"
    url, kwargs = calls[0]
    assert url == "https://lrclib.net/api/get" and kwargs["params"] == {"track_name": "Fixture Song", "artist_name": "Fixture Artist", "album_name": "Fixture Album", "duration": 20}
    assert kwargs["allow_redirects"] is False and "Cookie" not in kwargs["headers"]
    body["duration"] = 30
    with pytest.raises(ProviderUnavailable, match="confirm"):
        Providers(http_get=get).fetch("lrclib", VIDEO, TRACK)
    assert Providers(http_get=get).fetch("lrclib", VIDEO, TRACK, True)["match"] == "approximate"


def test_unison_checks_envelope_and_video_identity():
    get, calls = get_for({"success": True, "data": {"videoId": VIDEO, "format": "ttml", "lyrics": TTML}})
    result = Providers(http_get=get).fetch("unison", VIDEO, TRACK)
    assert result["syncLevel"] == "word"
    assert calls[0][1]["params"] == {"v": VIDEO}
    wrong, _ = get_for({"success": True, "data": {"videoId": "other000001", "format": "ttml", "lyrics": TTML}})
    with pytest.raises(ProviderUnavailable, match="confirm"):
        Providers(http_get=wrong).fetch("unison", VIDEO, TRACK)
    missing, _ = get_for({"success": False, "data": None})
    with pytest.raises(ProviderUnavailable):
        Providers(http_get=missing).fetch("unison", VIDEO, TRACK)


def test_better_cache_needs_explicit_approximate_opt_in_without_identity():
    get, calls = get_for({"ttml": TTML})
    provider = Providers(http_get=get, key_reader=lambda: "fixture-key")
    with pytest.raises(ProviderUnavailable, match="Approximate matches are off"):
        provider.fetch("better", VIDEO, TRACK)
    result = provider.fetch("better", VIDEO, TRACK, True)
    assert result["match"] == "approximate" and result["syncLevel"] == "word"
    assert calls[0][1]["params"] == {"s": "Fixture Song", "a": "Fixture Artist", "al": "Fixture Album", "d": 20}
    assert calls[0][1]["headers"]["X-API-Key"] == "fixture-key"
    assert "fixture-key" not in json.dumps(result)
    metadata = '<head><metadata><title>Fixture Song</title><artist>Fixture Artist</artist><album>Fixture Album</album><duration>20s</duration></metadata></head>'
    exact, _ = get_for({"ttml": TTML.replace('<body>', metadata + '<body>')})
    assert Providers(http_get=exact, key_reader=lambda: "").fetch("better", VIDEO, TRACK)["match"] == "exact"


def test_provider_http_failures_are_safe_and_back_off():
    get, _ = get_for({"error": "secret server content"}, 401)
    with pytest.raises(ProviderUnavailable, match="existing Better Lyrics API key") as error:
        Providers(http_get=get, key_reader=lambda: "").fetch("better", VIDEO, TRACK)
    assert "secret" not in str(error.value)
    calls = []
    def limited(*args, **kwargs):
        calls.append(True)
        return Response({}, 429, {"Retry-After": "600"})
    provider = Providers(http_get=limited)
    for _ in range(2):
        with pytest.raises(ProviderUnavailable, match="rate limited"):
            provider.fetch("unison", VIDEO, TRACK)
    assert len(calls) == 1


def test_provider_keys_stay_in_vault_and_are_never_returned():
    saved = {}
    backend = SimpleNamespace(get_password=lambda service, name: saved.get((service, name)), set_password=lambda service, name, value: saved.update({(service, name): value}), delete_password=lambda service, name: saved.pop((service, name)))
    assert provider_key("save", "fixture-key", backend) == {"hasKey": True}
    assert provider_key("status", backend=backend) == {"hasKey": True}
    assert provider_key("clear", backend=backend) == {"hasKey": False}
    with pytest.raises(ProviderUnavailable):
        provider_key("save", "invalid\nkey", backend)


def test_default_native_path_performs_no_external_io(tmp_path):
    provider = SimpleNamespace(fetch=lambda *args: pytest.fail("External lookup before consent"), captions=lambda *args: pytest.fail("Caption lookup before consent"))
    lyrics = Lyrics(native_client(), tmp_path, providers=provider)
    assert lyrics.fetch(VIDEO, track=TRACK)["available"]
    lyrics.close()


def test_native_timed_beats_cached_external_after_native_refresh(tmp_path):
    provider = SimpleNamespace(fetch=lambda *args: document())
    lyrics = Lyrics(native_client(), tmp_path, providers=provider)
    options = {"external": True}
    assert lyrics.fetch(VIDEO, track=TRACK, options=options)["provider"] == "lrclib"
    lyrics.auth = native_client(timed=True)
    assert lyrics.fetch(VIDEO, refresh=True)["timed"]
    result = lyrics.fetch(VIDEO, track=TRACK, options=options)
    assert result["lines"][0]["text"] == "Native fixture" and result["cached"]
    lyrics.close()


def test_fallback_order_native_plain_and_configured_offline_cache(tmp_path):
    calls = []
    def fetch(provider, *args):
        calls.append(provider)
        if provider == "unison":
            return document("unison")
        raise ProviderUnavailable("No matching lyrics available.")
    provider = SimpleNamespace(fetch=fetch)
    lyrics = Lyrics(native_client(), tmp_path, providers=provider)
    result = lyrics.fetch(VIDEO, track=TRACK, options={"external": True})
    assert calls == ["lrclib", "unison"] and result["provider"] == "unison"
    lyrics.close()
    def forbidden(*args):
        pytest.fail("Offline cached variant must not access network or authentication")
    restarted = Lyrics(SimpleNamespace(catalog=forbidden), tmp_path, providers=SimpleNamespace(fetch=forbidden))
    assert restarted.fetch(VIDEO, track=TRACK, options={"external": True})["cached"]
    # Disabling consent selects the native cache, not the external variant.
    assert restarted.fetch(VIDEO, track=TRACK)["lines"][0]["text"] == "Native plain fixture"
    restarted.close()


def test_all_provider_failures_keep_native_plain_and_separate_match_modes(tmp_path):
    calls = []
    def unavailable(provider, *args):
        calls.append(provider)
        raise ProviderUnavailable("Unavailable fixture source.")
    lyrics = Lyrics(native_client(), tmp_path, providers=SimpleNamespace(fetch=unavailable))
    result = lyrics.fetch(VIDEO, track=TRACK, options={"external": True})
    assert result["available"] and not result["timed"] and "Unavailable fixture source" in result["status"]
    assert calls == ["lrclib", "unison", "better"]
    lyrics.fetch(VIDEO, track=TRACK, options={"external": True, "approximate": True})
    assert len(calls) == 6, "Matching mode must be part of the variant cache identity"
    lyrics.close()


def test_captions_use_only_human_subtitles_and_keep_signed_urls_out_of_result(monkeypatch, tmp_path):
    import yt_dlp
    from youtube_music_native import compat
    monkeypatch.setattr(compat, "extractor_options", lambda directory: {})
    seen, data = [], {"subtitles": {"en": [{"ext": "ttml", "url": "https://fixture.invalid/signed-caption"}]}, "automatic_captions": {"en": [{"ext": "ttml", "url": "https://fixture.invalid/automatic"}]}}
    class Extractor:
        def __init__(self, options):
            assert options["writeautomaticsub"] is False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download): return data
        def urlopen(self, url):
            from io import BytesIO
            seen.append(url)
            return BytesIO(TTML.encode())
    monkeypatch.setattr(yt_dlp, "YoutubeDL", Extractor)
    provider = Providers()
    result = provider.captions(SimpleNamespace(session=None), VIDEO, TRACK, tmp_path)
    assert result["available"] and result["provider"] == "captions"
    assert "signed-caption" not in json.dumps(result) and "automatic" not in seen[0]
    data["subtitles"] = {}
    with pytest.raises(ProviderUnavailable, match="Human captions"):
        provider.captions(SimpleNamespace(session=None), VIDEO, TRACK, tmp_path)
    assert len(seen) == 1
