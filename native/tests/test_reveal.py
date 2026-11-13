from tubify.system.reveal import reveal


def calls():
    launched, shown, opened = [], [], []
    return launched, shown, opened, dict(launch=launched.append, show_items=shown.append, open_folder=lambda folder: opened.append(folder) or True)


def test_each_platform_selects_the_file(tmp_path):
    song = tmp_path / "song.flac"
    song.write_bytes(b"x")
    launched, shown, opened, hooks = calls()
    assert reveal(str(song), platform="win32", **hooks)
    assert reveal(str(song), platform="darwin", **hooks)
    assert reveal(str(song), platform="linux", **hooks)
    assert launched[0][:2] == ["explorer", "/select,"] and launched[1] == ["open", "-R", str(song)]
    assert shown == [str(song)] and not opened


def test_falls_back_to_the_folder(tmp_path):
    song = tmp_path / "song.flac"
    song.write_bytes(b"x")
    launched, shown, opened, hooks = calls()

    def unavailable(path):
        raise OSError("no file manager service")

    assert reveal(str(song), platform="linux", **{**hooks, "show_items": unavailable})
    assert reveal(str(tmp_path / "gone.flac"), platform="darwin", **hooks)  # A missing file opens its folder.
    assert opened == [str(tmp_path), str(tmp_path)] and not launched


def test_nothing_opens_without_a_real_location(tmp_path):
    launched, shown, opened, hooks = calls()
    assert not reveal("relative/song.flac", platform="linux", **hooks)
    assert not reveal(str(tmp_path / "missing" / "song.flac"), platform="linux", **hooks)
    assert not reveal(None, platform="linux", **hooks)
    assert not (launched or shown or opened)
