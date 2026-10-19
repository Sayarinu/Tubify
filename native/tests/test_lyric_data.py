from types import SimpleNamespace

from youtube_music_native.lyric_data import Lyrics, normalize


def test_lyrics_normalize_plain_timed_missing_and_invalid_timing():
    assert normalize(None, "abcdefghijk")["available"] is False
    plain = normalize({"lyrics": "First fixture line\n\nSecond fixture line", "source": "Fixture"}, "abcdefghijk")
    assert plain["available"] and not plain["timed"] and len(plain["lines"]) == 3
    timed = normalize({"lyrics": [SimpleNamespace(text="Later", start_time=2000, end_time=3000), SimpleNamespace(text="Earlier", start_time=0, end_time=1000)]}, "abcdefghijk")
    assert timed["timed"] and [row["start"] for row in timed["lines"]] == [0, 2]
    invalid = normalize({"lyrics": [{"text": "Fixture", "start_time": 3000, "end_time": 2000}]}, "abcdefghijk")
    assert invalid["available"] and not invalid["timed"] and invalid["lines"][0]["start"] == -1


def test_fetched_lyrics_reopen_offline_without_accessing_authentication(tmp_path):
    calls = []
    client = SimpleNamespace(
        get_watch_playlist=lambda **kwargs: {"lyrics": "MPLYfixture"},
        get_lyrics=lambda identifier, timestamps: (calls.append(timestamps) or {"lyrics": "Original fixture line", "source": "Fixture"}),
    )
    provider = Lyrics(SimpleNamespace(catalog=lambda: client), tmp_path)
    assert provider.fetch("abcdefghijk")["available"] and calls == [True]
    provider.close()
    def forbidden():
        raise AssertionError("Offline lyrics must not access credentials or HTTP")
    restarted = Lyrics(SimpleNamespace(catalog=forbidden), tmp_path)
    result = restarted.fetch("abcdefghijk")
    assert result["cached"] and result["lines"][0]["text"] == "Original fixture line"
    restarted.close()


def test_missing_lyrics_are_cached_and_damaged_json_can_be_refetched(tmp_path):
    client = SimpleNamespace(get_watch_playlist=lambda **kwargs: {})
    provider = Lyrics(SimpleNamespace(catalog=lambda: client), tmp_path)
    assert not provider.fetch("abcdefghijk")["available"]
    client.get_watch_playlist = lambda **kwargs: (_ for _ in ()).throw(AssertionError("Must reuse cached absence"))
    assert provider.fetch("abcdefghijk")["cached"]
    provider.db.execute("UPDATE lyrics SET body='bad json'")
    provider.db.commit()
    client.get_watch_playlist = lambda **kwargs: {}
    assert not provider.fetch("abcdefghijk")["cached"]
    provider.close()


def test_unavailable_mobile_lyrics_fall_back_to_plain_desktop_lyrics(tmp_path):
    calls = []
    def fetch(identifier, timestamps):
        calls.append(timestamps)
        if timestamps:
            raise RuntimeError("Unsupported mobile client")
        return {"lyrics": "Original fixture line", "source": "Fixture"}
    client = SimpleNamespace(get_watch_playlist=lambda **kwargs: {"lyrics": "MPLYfixture"}, get_lyrics=fetch)
    provider = Lyrics(SimpleNamespace(catalog=lambda: client), tmp_path)
    assert provider.fetch("abcdefghijk")["available"] and calls == [True, False]
    provider.close()
