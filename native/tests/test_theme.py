import json

from PySide6.QtCore import QCoreApplication

from youtube_music_native.theme import DEFAULT_COLORS, DEFAULT_THEME_ID, ThemeState


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


def test_builtin_themes_and_role_palette(tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    assert len([entry for entry in theme.themes if entry["builtin"]]) == 12
    assert sum(entry["light"] for entry in theme.themes) == 3
    assert theme.activeThemeId == DEFAULT_THEME_ID
    assert theme.activeThemeName == "Classic"
    assert {entry["name"] for entry in theme.themes if entry["id"] in ("classic-dark", "classic-light")} == {"Classic", "Classic Light"}
    assert {entry["key"] for entry in theme.palette} == set(DEFAULT_COLORS)


def test_select_custom_palette_is_reactive_and_persists(tmp_path):
    _app()
    path = tmp_path / "theme.ini"
    theme = ThemeState(path)
    changed = []
    theme.paletteChanged.connect(lambda: changed.append(theme.accent))
    assert theme.createCustomTheme("Night Mix")
    theme.setColor("accent", "#12abef")
    assert theme.accent == "#12ABEF"
    assert changed[-1] == "#12ABEF"

    restored = ThemeState(path)
    assert restored.activeThemeName == "Night Mix"
    assert restored.accent == "#12ABEF"
    assert restored.activeThemeIsCustom


def test_hero_tint_blends_the_active_background_with_its_accent(tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    assert theme.heroTint == ThemeState._blend(theme.background, theme.accent)
    classic_tint = theme.heroTint
    theme.selectTheme("classic-light")
    assert theme.heroTint == ThemeState._blend(theme.background, theme.accent)
    assert theme.heroTint != classic_tint
    theme.createCustomTheme("Tint test")
    theme.setColor("accent", "#0000FF")
    assert theme.heroTint == ThemeState._blend(theme.background, "#0000FF")


def test_custom_theme_crud_and_active_delete_falls_back(tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    assert theme.createCustomTheme("My colors")
    theme_id = theme.activeThemeId
    assert theme.renameCustomTheme(theme_id, "Evening")
    assert theme.activeThemeName == "Evening"
    assert not theme.renameCustomTheme(theme_id, "Dracula")
    assert theme.deleteCustomTheme(theme_id)
    assert theme.activeThemeId == DEFAULT_THEME_ID
    assert not theme.deleteCustomTheme(DEFAULT_THEME_ID)


def test_legacy_non_default_colors_migrate_to_custom_theme(tmp_path):
    _app()
    path = tmp_path / "theme.ini"
    path.write_text("[colors]\naccent=#ff0000\n", encoding="utf-8")
    theme = ThemeState(path)
    assert theme.activeThemeIsCustom
    assert theme.activeThemeName == "My Custom Theme"
    assert theme.accent == "#FF0000"
    restored = ThemeState(path)
    assert restored.activeThemeName == "My Custom Theme"


def test_import_export_and_conflict_rules(tmp_path):
    _app()
    path = tmp_path / "theme.ini"
    theme = ThemeState(path)
    assert theme.createCustomTheme("Export me")
    theme.setColor("accent", "#abcdef")
    exported = tmp_path / "shared-theme.json"
    assert theme.exportTheme(str(exported))
    document = json.loads(exported.read_text(encoding="utf-8"))
    assert document["version"] == 1
    assert document["appearance"] == "dark"
    assert set(document["colors"]) == set(DEFAULT_COLORS)

    imported = ThemeState(tmp_path / "other.ini")
    result = imported.inspectImport(str(exported))
    assert result["ok"] and not result["conflict"]
    assert imported.completeImport(result["name"], False)
    assert imported.accent == "#ABCDEF"

    conflict = imported.inspectImport(str(exported))
    assert conflict["conflict"] and not conflict["builtIn"]
    assert not imported.completeImport(result["name"], False)
    assert imported.completeImport(result["name"], True)

    built_in = dict(document, name="Dracula")
    built_in_path = tmp_path / "built-in.json"
    built_in_path.write_text(json.dumps(built_in), encoding="utf-8")
    result = imported.inspectImport(str(built_in_path))
    assert result["builtIn"]
    assert not imported.completeImport("Dracula", True)
    assert imported.completeImport("Dracula Personal", False)

    light_document = dict(document, name="Imported Light", colors=dict(document["colors"], background="#FFFFFF"))
    light_path = tmp_path / "light-theme.json"
    light_path.write_text(json.dumps(light_document), encoding="utf-8")
    result = imported.inspectImport(str(light_path))
    assert result["ok"] and imported.completeImport(result["name"], False)
    assert next(theme for theme in imported.themes if theme["id"] == imported.activeThemeId)["light"]


def test_invalid_import_does_not_change_active_theme(tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    before = theme.activeThemeId, theme.accent
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"version": 99, "name": "Broken", "colors": {}}', encoding="utf-8")
    assert not theme.inspectImport(str(invalid))["ok"]
    assert theme.message == "Invalid theme format."
    assert (theme.activeThemeId, theme.accent) == before
