"""Portable window/navigation state; provider work belongs outside the GUI thread."""

from PySide6.QtCore import QObject, Property, QSettings, Signal, Slot


class ShellController(QObject):
    pageChanged = Signal()
    sidebarChanged = Signal()
    queueWidthChanged = Signal()
    volumeChanged = Signal()
    navigationRequested = Signal(str)
    searchRequested = Signal(str)
    accountDialogRequested = Signal()
    actionRequested = Signal(str)
    playlistsChanged = Signal()
    menuRequested = Signal(dict, dict)
    playerViewChanged = Signal()
    queueOpenChanged = Signal()

    def __init__(self, settings_path, fixture=None, parent=None):
        super().__init__(parent)
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self._page = "Home"
        self._query = ""
        self._sidebar = self.settings.value("sidebarExpanded", False, type=bool)
        self._sidebar_width = max(180, min(420, self._integer_setting("sidebarWidth", 240)))
        self._queue_width = max(280, min(520, self._integer_setting("queueWidth", 360)))
        self._volume = max(0, min(100, self._integer_setting("volume", 70)))
        self._unmuted_volume = max(1, min(100, self._integer_setting("lastVolume", self._volume or 70)))
        self._fixture = fixture or {}
        self._shelves = self._fixture.get("shelves", [])
        self._playlists = self._fixture.get("playlists", [])
        self._expanded, self._player_tab = False, "Up next"
        self._queue_open = False

    def _integer_setting(self, key, default):
        try:
            return int(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    @Property(str, notify=pageChanged)
    def page(self):
        return self._page

    @Property(str, notify=pageChanged)
    def query(self):
        return self._query

    @Property(bool, notify=sidebarChanged)
    def sidebarExpanded(self):
        return self._sidebar

    @Property(int, notify=sidebarChanged)
    def sidebarWidth(self):
        return self._sidebar_width

    @Property(int, notify=queueWidthChanged)
    def queueWidth(self):
        return self._queue_width

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

    @Slot()
    def toggleSidebar(self):
        self._sidebar = not self._sidebar
        self.sidebarChanged.emit()

    @Slot(float)
    def setSidebarWidth(self, value):
        width = max(180, min(420, round(value)))
        if width != self._sidebar_width:
            self._sidebar_width = width
            self.sidebarChanged.emit()

    @Slot(float)
    def setQueueWidth(self, value):
        width = max(280, min(520, round(value)))
        if width != self._queue_width:
            self._queue_width = width
            self.queueWidthChanged.emit()

    @Slot()
    def saveSidebarWidths(self):
        self.settings.setValue("sidebarWidth", self._sidebar_width)
        self.settings.setValue("queueWidth", self._queue_width)
        self.settings.sync()

    @Property(bool, notify=queueOpenChanged)
    def queueOpen(self):
        return self._queue_open

    @Slot()
    def toggleQueue(self):
        self._queue_open = not self._queue_open
        self.queueOpenChanged.emit()

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

    @Property(str, notify=playerViewChanged)
    def playerTab(self):
        return self._player_tab

    @Slot(bool)
    def setExpanded(self, value):
        self._expanded = value
        self.playerViewChanged.emit()

    @Slot(str)
    def setPlayerTab(self, value):
        if value in {"Up next", "Lyrics"}:
            self._player_tab = value
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
        self.settings.setValue("sidebarExpanded", self._sidebar)
        self.settings.setValue("sidebarWidth", self._sidebar_width)
        self.settings.setValue("queueWidth", self._queue_width)
        self.settings.setValue("volume", self._volume)
        self.settings.setValue("lastVolume", self._unmuted_volume)
        self.settings.sync()
