"""Portable window/navigation state; provider work belongs outside the GUI thread."""

from PySide6.QtCore import QObject, Property, QRect, QSettings, Signal, Slot


def fit_window_geometry(saved, available):
    """Keep the saved window on the nearest connected display, including negative origins."""
    if not available:
        return saved
    target = max(available, key=lambda screen: screen.intersected(saved).width() * screen.intersected(saved).height())
    if not target.intersects(saved):
        target = min(available, key=lambda screen: (screen.center() - saved.center()).manhattanLength())
    width, height = min(saved.width(), target.width()), min(saved.height(), target.height())
    return QRect(max(target.x(), min(saved.x(), target.x() + target.width() - width)),
                 max(target.y(), min(saved.y(), target.y() + target.height() - height)), width, height)


SIDE_PANELS = {"Queue", "Lyrics", "NowPlaying"}


class ShellController(QObject):
    pageChanged = Signal()
    sidebarChanged = Signal()
    panelWidthChanged = Signal()
    volumeChanged = Signal()
    navigationRequested = Signal(str)
    searchRequested = Signal(str)
    accountDialogRequested = Signal()
    actionRequested = Signal(str)
    playlistsChanged = Signal()
    menuRequested = Signal(dict, dict)
    playerViewChanged = Signal()
    playerViewChanging = Signal(bool)
    panelChanged = Signal()
    appearanceChanged = Signal()

    def __init__(self, settings_path, fixture=None, parent=None):
        super().__init__(parent)
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self._ui_scale = round(max(80, min(150, self._integer_setting("uiScale", 100))) / 5) * 5
        self._reduced_motion = self.settings.value("reducedMotion", False, type=bool)
        self._artwork_background = self.settings.value("artworkBackground", True, type=bool)
        self._artwork_blur = self.settings.value("artworkBlur", True, type=bool)
        self._page = "Home"
        self._query = ""
        self._sidebar_width = max(180, min(420, self._integer_setting("sidebarWidth", 240)))
        self._panel_width = max(280, min(520, self._integer_setting("panelWidth", 360)))
        self._volume = max(0, min(100, self._integer_setting("volume", 70)))
        self._unmuted_volume = max(1, min(100, self._integer_setting("lastVolume", self._volume or 70)))
        self._fixture = fixture or {}
        self._shelves = self._fixture.get("shelves", [])
        self._playlists = self._fixture.get("playlists", [])
        self._expanded = False
        self._panel = str(self.settings.value("sidePanel", ""))
        if self._panel not in SIDE_PANELS:
            self._panel = ""

    def _integer_setting(self, key, default):
        try:
            return int(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    @Property(int, notify=appearanceChanged)
    def uiScale(self):
        return self._ui_scale

    @Property(float, notify=appearanceChanged)
    def uiScaleFactor(self):
        return self._ui_scale / 100

    @Property(bool, notify=appearanceChanged)
    def reducedMotion(self):
        return self._reduced_motion

    @Property(bool, notify=appearanceChanged)
    def artworkBackground(self):
        return self._artwork_background

    @Property(bool, notify=appearanceChanged)
    def artworkBlur(self):
        return self._artwork_blur

    def _save_appearance(self):
        for key, value in (("uiScale", self._ui_scale), ("reducedMotion", self._reduced_motion),
                           ("artworkBackground", self._artwork_background), ("artworkBlur", self._artwork_blur)):
            self.settings.setValue(key, value)
        self.settings.sync()
        self.appearanceChanged.emit()

    @Slot(int)
    def setUiScale(self, value):
        value = max(80, min(150, round(value / 5) * 5))
        if value != self._ui_scale:
            self._ui_scale = value
            self._save_appearance()

    @Slot(bool)
    def setReducedMotion(self, value):
        if value != self._reduced_motion:
            self._reduced_motion = value
            self._save_appearance()

    @Slot(bool)
    def setArtworkBackground(self, value):
        if value != self._artwork_background:
            self._artwork_background = value
            self._save_appearance()

    @Slot(bool)
    def setArtworkBlur(self, value):
        if value != self._artwork_blur:
            self._artwork_blur = value
            self._save_appearance()

    def restoreWindow(self, window, available):
        saved = QRect(max(-1000000, min(1000000, self._integer_setting("windowX", window.x()))),
                      max(-1000000, min(1000000, self._integer_setting("windowY", window.y()))),
                      self.initialWidth, self.initialHeight)
        geometry = fit_window_geometry(saved, available)
        window.setMinimumSize(geometry.size().boundedTo(window.minimumSize()))
        window.setGeometry(geometry)

    @Slot(int, int, int, int)
    def saveWindowGeometry(self, x, y, width, height):
        self.settings.setValue("windowX", x)
        self.settings.setValue("windowY", y)
        self.saveWindow(width, height)

    @Property(str, notify=pageChanged)
    def page(self):
        return self._page

    @Property(str, notify=pageChanged)
    def query(self):
        return self._query

    @Property(int, notify=sidebarChanged)
    def sidebarWidth(self):
        return self._sidebar_width

    @Property(int, notify=panelWidthChanged)
    def panelWidth(self):
        return self._panel_width

    @Property("QVariantList", constant=True)
    def shelves(self):
        return self._shelves

    @Property("QVariantList", notify=playlistsChanged)
    def playlists(self):
        return self._playlists

    def setPlaylists(self, values):
        self._playlists = values
        self.playlistsChanged.emit()

    def restoreNavigation(self, page, query):
        self._page, self._query = page, query
        self.pageChanged.emit()

    @Property(int, notify=volumeChanged)
    def volume(self):
        return self._volume

    @Property(int, constant=True)
    def initialWidth(self):
        return max(920, min(7680, self._integer_setting("width", 1280)))

    @Property(int, constant=True)
    def initialHeight(self):
        return max(620, min(4320, self._integer_setting("height", 820)))

    @Property(bool, constant=True)
    def fixtureMode(self):
        return bool(self._fixture)

    @Slot(str)
    def navigate(self, page):
        if page not in {"Home", "Explore", "Library", "Downloads", "Search"}:
            return
        self._page = page
        self.setExpanded(False)
        self.pageChanged.emit()
        self.navigationRequested.emit(page)

    @Slot(str)
    def search(self, query):
        query = query.strip()
        if not query:
            return
        self._query = query
        self.navigate("Search")
        self.searchRequested.emit(query)

    @Slot(float)
    def setSidebarWidth(self, value):
        width = max(180, min(420, round(value)))
        if width != self._sidebar_width:
            self._sidebar_width = width
            self.sidebarChanged.emit()

    @Slot(float)
    def setPanelWidth(self, value):
        width = max(280, min(520, round(value)))
        if width != self._panel_width:
            self._panel_width = width
            self.panelWidthChanged.emit()

    @Slot()
    def saveSidebarWidths(self):
        self.settings.setValue("sidebarWidth", self._sidebar_width)
        self.settings.setValue("panelWidth", self._panel_width)
        self.settings.sync()

    @Property(str, notify=panelChanged)
    def panel(self):
        """The open side panel, or an empty string. At most one is ever open."""
        return self._panel

    @Slot(str)
    def setPanel(self, value):
        if value and value not in SIDE_PANELS:
            return
        if value != self._panel:
            self._panel = value
            self.settings.setValue("sidePanel", value)
            self.settings.sync()
            self.panelChanged.emit()

    @Slot(str)
    def togglePanel(self, value):
        self.setPanel("" if self._panel == value else value)

    @Property(bool, notify=panelChanged)
    def queueOpen(self):
        return self._panel == "Queue"

    @Property(bool, notify=panelChanged)
    def lyricsOpen(self):
        return self._panel == "Lyrics"

    @Property(bool, notify=panelChanged)
    def nowPlayingOpen(self):
        return self._panel == "NowPlaying"

    @Slot(bool)
    def setQueueOpen(self, value):
        self.setPanel("Queue" if value else "" if self.queueOpen else self._panel)

    @Slot(bool)
    def setLyricsOpen(self, value):
        self.setPanel("Lyrics" if value else "" if self.lyricsOpen else self._panel)

    @Slot()
    def toggleQueue(self):
        self.togglePanel("Queue")

    @Slot()
    def toggleLyrics(self):
        self.togglePanel("Lyrics")

    @Slot()
    def toggleNowPlaying(self):
        self.togglePanel("NowPlaying")

    @Slot(int)
    def setVolume(self, value):
        self._volume = max(0, min(100, value))
        if self._volume:
            self._unmuted_volume = self._volume
        self.volumeChanged.emit()

    @Slot()
    def toggleMute(self):
        self.setVolume(0 if self._volume else self._unmuted_volume)

    @Slot(str)
    def requestAction(self, action):
        if action == "expandPlayer":
            self.setExpanded(not self._expanded)
        self.actionRequested.emit(action)

    @Property(bool, notify=playerViewChanged)
    def expanded(self):
        return self._expanded

    @Slot(bool)
    def setExpanded(self, value):
        if self._expanded != value:
            self.playerViewChanging.emit(value)
            self._expanded = value
            self.playerViewChanged.emit()

    @Slot("QVariantMap", "QVariantMap")
    def showMenu(self, media, context):
        self.menuRequested.emit(dict(media), dict(context))

    @Slot()
    def openAccount(self):
        self.accountDialogRequested.emit()

    @Slot(int, int)
    def saveWindow(self, width, height):
        self.settings.setValue("width", max(920, min(7680, width)))
        self.settings.setValue("height", max(620, min(4320, height)))
        self.settings.setValue("sidebarWidth", self._sidebar_width)
        self.settings.setValue("panelWidth", self._panel_width)
        self.settings.setValue("volume", self._volume)
        self.settings.setValue("lastVolume", self._unmuted_volume)
        self.settings.sync()
