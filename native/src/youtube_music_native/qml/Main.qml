import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window
import "Theme.js" as Theme

ApplicationWindow {
    id: window
    visible: false
    width: appState.initialWidth
    height: appState.initialHeight
    minimumWidth: 920
    minimumHeight: 620
    title: appState.fixtureMode ? "Tubify · Visual Fixture" : "Tubify"
    color: themeState.background
    font.pixelSize: 14
    palette.window: themeState.surface
    palette.base: themeState.background
    palette.alternateBase: themeState.surface
    palette.button: themeState.surface
    palette.text: themeState.foreground
    palette.placeholderText: themeState.secondary
    palette.windowText: themeState.foreground
    palette.buttonText: themeState.foreground
    palette.accent: themeState.accent
    palette.highlight: themeState.accent
    palette.highlightedText: themeState.onAccent
    palette.midlight: themeState.hover
    palette.mid: themeState.border
    palette.light: themeState.border
    palette.dark: themeState.background
    palette.link: themeState.accent
    // Warm the artwork caches for the next songs so track changes never show a blank cover.
    Repeater {
        model: (playerState.upcomingTracks || []).filter(track => !!track.videoId).reduce((items, track) => items.concat([
            { url: track.thumbnail || "", size: 136 },
            { url: downloadsState.artworkSource(track, Math.ceil(720 * Screen.devicePixelRatio * appState.uiScaleFactor)), size: Math.ceil(720 * Screen.devicePixelRatio * appState.uiScaleFactor) }
        ]), [])
        delegate: Image {
            required property var modelData
            visible: false
            asynchronous: true
            source: modelData.url
            sourceSize.width: modelData.size
            sourceSize.height: modelData.size
        }
    }
    property bool wideNavigation: true
    readonly property bool compactNavigation: !appState.expanded && (appState.queueOpen || appState.lyricsOpen) && uiRoot.width < 780
    onCompactNavigationChanged: navigationDrawer.close()
    readonly property bool docksVisible: (appState.queueOpen || appState.lyricsOpen)
    readonly property bool bothDocks: appState.queueOpen && appState.lyricsOpen
    readonly property bool tabbedDocks: bothDocks && uiRoot.width - navigationEdge.width < 1040
    // Docks never take the last 480 px from the page; below that they stop at their 280 px minimum.
    readonly property real dockBudget: Math.max(280, uiRoot.width - navigationEdge.width - 480)
    readonly property real dockExtra: appState.queueWidth + appState.lyricsWidth - 560
    readonly property real fittedExtra: Math.min(dockExtra, Math.max(0, dockBudget - 560))
    readonly property real fittedQueueWidth: bothDocks && !tabbedDocks
        ? 280 + (dockExtra > 0 ? fittedExtra * (appState.queueWidth - 280) / dockExtra : 0)
        : Math.min(appState.queueWidth, dockBudget)
    readonly property real fittedLyricsWidth: bothDocks && !tabbedDocks
        ? 280 + (dockExtra > 0 ? fittedExtra * (appState.lyricsWidth - 280) / dockExtra : 0)
        : Math.min(appState.lyricsWidth, dockBudget)
    readonly property bool showQueueDock: docksVisible && appState.queueOpen && (!tabbedDocks || appState.activeDock === "Queue")
    readonly property bool showLyricsDock: docksVisible && appState.lyricsOpen && (!tabbedDocks || appState.activeDock === "Lyrics")
    readonly property bool lyricsActive: showLyricsDock
    function restoreDockFocus() {
        Qt.callLater(function() {
            // A dock sliding out is disabled at once, which drops its focus to the window root.
            var focused = window.activeFocusItem
            if (focused && (!focused.visible || !focused.enabled || !focused.parent)) {
                if (showLyricsDock) lyricsHeader.focusControl()
                else if (showQueueDock) queueHeader.focusControl()
                else player.focusDockToggle(appState.activeDock)
            }
        })
    }
    onShowLyricsDockChanged: restoreDockFocus()
    onShowQueueDockChanged: restoreDockFocus()
    onLyricsActiveChanged: lyricState.setActive(lyricsActive)
    Component.onCompleted: lyricState.setActive(lyricsActive)
    property var browseFocus: null
    property real browseWidth: 0
    property real browseHeight: 0
    // Keeps the expanded player loaded while it slides back down.
    property bool immersiveClosing: false
    function focusSearch() {
        appState.setExpanded(false)
        Qt.callLater(header.focusSearch)
    }
    Connections {
        target: appState
        function onAppearanceChanged() { Qt.callLater(window.revealActiveScrollFocus) }
        function onPlayerViewChanging(entering) {
            if (entering) {
                window.browseFocus = window.activeFocusItem
                window.browseWidth = pages.width
                window.browseHeight = pages.height
            }
            immersive.slide(entering)
        }
        function onPlayerViewChanged() {
            if (appState.expanded) window.immersiveClosing = false
            Qt.callLater(function() {
                if (appState.expanded && immersive.item) immersive.item.focusStage()
                else if (window.browseFocus && window.browseFocus.visible && window.browseFocus.enabled) window.browseFocus.forceActiveFocus()
                else player.focusImmersiveToggle()
            })
        }
    }
    onClosing: function(event) {
        appState.saveWindowGeometry(x, y, width, height)
        if (lifecycleState.hideOnClose()) event.accepted = false
    }
    function revealScrolledFocus(scroll) {
        var item = window.activeFocusItem
        if (!item || !scroll || !scroll.visible) return
        var ancestor = item
        while (ancestor && ancestor !== scroll) ancestor = ancestor.parent
        if (!ancestor) return
        var flick = scroll.contentItem
        var point = item.mapToItem(flick.contentItem, 0, 0)
        if (point.y < flick.contentY) flick.contentY = Math.max(0, point.y)
        else if (point.y + item.height > flick.contentY + flick.height)
            flick.contentY = Math.min(flick.contentHeight - flick.height, point.y + item.height - flick.height)
    }
    readonly property var focusedScrollView: {
        var ancestor = window.activeFocusItem
        while (ancestor && !(ancestor instanceof ScrollView)) ancestor = ancestor.parent
        return ancestor
    }
    function revealActiveScrollFocus() { revealScrolledFocus(focusedScrollView) }
    onActiveFocusItemChanged: Qt.callLater(revealActiveScrollFocus)
    // Font metrics and wrapped content can settle after focus has already moved.
    Connections {
        target: window.focusedScrollView ? window.focusedScrollView.contentItem : null
        function onContentHeightChanged() { Qt.callLater(window.revealActiveScrollFocus) }
        function onHeightChanged() { Qt.callLater(window.revealActiveScrollFocus) }
    }
    property bool editingText: activeFocusItem instanceof TextInput || activeFocusItem instanceof TextEdit
    // Open dialogs, menus and the navigation drawer take keyboard focus and sit in the overlay while shown,
    // so any of them blocks the shortcuts without being listed here. Tooltips and search suggestions don't take focus,
    // and the player bar's sleep timer popover is meant to leave the shortcuts working.
    readonly property int focusedPopups: Overlay.overlay ? Overlay.overlay.children.filter(item => item.visible && item.focus).length : 0
    readonly property bool modalOpen: focusedPopups > (player.sleepMenuOpen ? 1 : 0)
    property bool playbackShortcuts: !editingText && !modalOpen && !mediaMenu.opened

    // Content zoom is independent of the platform device-pixel ratio.
    Overlay.overlay.transform: Scale { xScale: appState.uiScaleFactor; yScale: appState.uiScaleFactor }
    Binding { target: window.Overlay.overlay; property: "width"; value: uiRoot.width }
    Binding { target: window.Overlay.overlay; property: "height"; value: uiRoot.height }
    Item {
        id: uiRoot
        objectName: "scaledContent"
        width: window.width / appState.uiScaleFactor
        height: window.height / appState.uiScaleFactor
        scale: appState.uiScaleFactor
        transformOrigin: Item.TopLeft

    Item { id: navigationEdge; width: window.compactNavigation ? 0 : sidebar.width }
    Drawer {
        id: navigationDrawer
        objectName: "navigationDrawer"
        width: Math.min(appState.sidebarWidth, uiRoot.width - 48)
        height: uiRoot.height - player.height - 24
        padding: 0
        modal: true; focus: true
        onOpened: sidebar.forceActiveFocus()
        onClosed: if (window.compactNavigation) header.focusNavigationToggle()
        enter: Transition { enabled: !appState.reducedMotion }
        exit: Transition { enabled: !appState.reducedMotion }
        contentItem: Item { id: drawerContent }
    }

    NavigationSidebar {
        id: sidebar
        parent: window.compactNavigation ? drawerContent : uiRoot
        wide: window.wideNavigation
        width: appState.expanded ? 0 : window.compactNavigation ? navigationDrawer.width : Math.min(appState.sidebarWidth, Math.max(180, uiRoot.width - (window.docksVisible ? 280 + 480 : 320)))
        anchors.top: parent.top
        anchors.bottom: window.compactNavigation ? parent.bottom : player.top
        onNavigated: navigationDrawer.close()
    }

    MainHeader {
        id: header
        anchors.left: navigationEdge.right
        anchors.right: showLyricsDock ? lyricsSidebar.left : showQueueDock ? queueSidebar.left : parent.right
        compactNavigation: window.compactNavigation
        onNavigationRequested: navigationDrawer.open()
        onSettingsRequested: settingsDialog.open()
        onAccountRequested: accountDialog.open()
        onUpdateRequested: updateDialog.open()
    }

    PlaybackSettings { id: playbackSettings; host: settingsDialog }
    UpdateSettings { id: updateSettings; host: settingsDialog }
    TroubleshootingSettings { id: troubleshootingSettings; host: settingsDialog }
    UpdateDialog { id: updateDialog }
    DesktopSettings { id: desktopSettings; host: settingsDialog }
    DiscordSettings { id: discordSettings; host: settingsDialog }
    CastSettings { id: castSettings; host: settingsDialog }
    Loader { active: trayState.enabled; sourceComponent: TrayPlayer { palette: window.palette } }

    SettingsDialog {
        id: settingsDialog
        currentPage: appearanceSettings
        sections: [
            { title: "General", pages: [appearanceSettings, playbackSettings, lyricsSettings] },
            { title: "Application", pages: [desktopSettings] },
            { title: "Connections", pages: [discordSettings, lastFmSettings, castSettings] },
            { title: "Support", pages: [updateSettings, troubleshootingSettings] }
        ]
        onClosed: header.focusSettingsButton()
    }
    LyricsSettings { id: lyricsSettings; host: settingsDialog }
    LastFmSettings { id: lastFmSettings; host: settingsDialog }
    LinkPreview { id: linkPreview }
    HandoffDialog { id: handoffDialog }
    Connections {
        target: typeof handoffState !== "undefined" ? handoffState : null
        function onRequested() { handoffDialog.open() }
    }
    Connections {
        target: typeof linkState !== "undefined" ? linkState : null
        function onPreviewRequested() { linkPreview.open() }
    }

    Rectangle {
        id: reconnectBanner
        anchors.left: navigationEdge.right
        anchors.right: parent.right
        anchors.top: header.bottom
        visible: accountState.reconnect
        height: visible ? 44 : 0
        // A light wash of the error colour keeps the primary text readable on light and dark themes.
        color: Qt.tint(themeState.surface, Qt.alpha(themeState.error, 0.16))
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Qt.alpha(themeState.error, 0.4) }
        Text {
            anchors.left: parent.left; anchors.leftMargin: 24
            anchors.right: reconnectButton.left; anchors.rightMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            text: "Reconnect your account. Downloaded music remains available."
            textFormat: Text.PlainText
            color: themeState.foreground; font.pixelSize: Theme.textBody; elide: Text.ElideRight
        }
        ThemeActionButton { id: reconnectButton; primary: true; implicitHeight: 32; anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; text: accountState.signInAvailable ? "Sign In Again" : "Reconnect"; enabled: !accountState.busy && !accountState.signingIn; onClicked: accountState.signInAvailable ? accountState.signIn() : appState.openAccount() }
    }

    Item {
        id: content
        objectName: "pageContent"
        anchors.left: navigationEdge.right
        anchors.right: showLyricsDock ? lyricsSidebar.left : showQueueDock ? queueSidebar.left : parent.right
        anchors.top: reconnectBanner.bottom
        anchors.bottom: player.top
        anchors.bottomMargin: 12
        property real gutter: Theme.gutter(width)

        Loader {
            id: pages
            objectName: "browseLoader"
            // Keep the page and its viewport alive while the stage uses the available space.
            width: appState.expanded ? window.browseWidth : parent.width
            height: appState.expanded ? window.browseHeight : parent.height
            visible: !appState.expanded
            enabled: visible
            // Pages ease in on every navigation instead of swapping abruptly.
            transform: Translate { id: pageShift }
            function enter() {
                if (appState.reducedMotion) { pageEnter.stop(); opacity = 1; pageShift.y = 0; return }
                pageEnter.restart()
            }
            ParallelAnimation {
                id: pageEnter
                NumberAnimation { target: pages; property: "opacity"; from: 0; to: 1; duration: Theme.motionMedium; easing.type: Easing.OutCubic }
                NumberAnimation { target: pageShift; property: "y"; from: 12; to: 0; duration: Theme.motionSlow; easing.type: Easing.OutCubic }
            }
            onLoaded: enter()
            Connections { target: catalogState; function onNavigationStarted() { pages.enter() } }
            function syncPage() {
                var route = catalogState.route
                var target = route === "downloads" ? downloadsPage
                    : route === "album" || route === "playlist" ? collectionPage
                    : route === "artist" ? artistPage
                    : route === "search" ? searchPage
                    : route.indexOf("library_") === 0 || route === "history" || appState.page === "Library" && route === "home" ? libraryPage
                    : browsePage
                if (sourceComponent !== target) sourceComponent = target
            }
            // Coalesce route and shell updates before replacing an incubating page.
            Component.onCompleted: Qt.callLater(syncPage)
            Connections { target: catalogState; function onChanged() { Qt.callLater(pages.syncPage) } }
            Connections { target: appState; function onPageChanged() { Qt.callLater(pages.syncPage) } }
            Component { id: downloadsPage; DownloadsPane {} }
            Component { id: collectionPage; CollectionPane {} }
            Component { id: artistPage; ArtistPane {} }
            Component { id: searchPage; SearchPane {} }
            Component { id: libraryPage; LibraryPane {} }
            Component { id: browsePage; BrowsePane {} }
        }

        Loader {
            id: immersive
            objectName: "immersiveLoader"
            // While closing, hold the expanded geometry so the returning sidebar and header don't re-lay out the pane;
            // content sits above them, and the docks and player bar above it.
            property rect closingArea: Qt.rect(0, 0, 0, 0)
            x: window.immersiveClosing ? closingArea.x - content.x : 0
            y: window.immersiveClosing ? closingArea.y - content.y : 0
            width: window.immersiveClosing ? closingArea.width : parent.width
            height: window.immersiveClosing ? closingArea.height : parent.height
            z: 1
            active: appState.expanded || window.immersiveClosing
            // The closing pane only animates; input and focus belong to the pages beneath it.
            enabled: appState.expanded
            sourceComponent: Component { ExpandedPane {} }
            onLoaded: item.focusStage()
            transform: Translate { id: immersiveShift }
            property bool opening: true
            // Runs before the expanded flag flips, so the pane starts off-screen and stays loaded while closing.
            function slide(entering) {
                immersiveSlide.stop()
                // Only a close raises the flag; an open clears it after the flip so a reversal never unloads the pane.
                if (!entering && !window.immersiveClosing) closingArea = Qt.rect(content.x, content.y, content.width, content.height)
                if (!entering) window.immersiveClosing = !appState.reducedMotion
                if (appState.reducedMotion) {
                    immersiveShift.y = 0
                    return
                }
                // A fresh open starts below the content; reopening mid-close reverses from where it is.
                if (entering && !active) immersiveShift.y = content.height
                opening = entering
                immersiveTarget.to = entering ? 0 : closingArea.height
                immersiveSlide.start()
            }
            // The pane stays opaque: it still spans the sidebar while closing, so any fade would show its artwork over the page.
            SequentialAnimation {
                id: immersiveSlide
                NumberAnimation { id: immersiveTarget; target: immersiveShift; property: "y"; duration: Theme.motionSlow; easing.type: immersive.opening ? Easing.OutCubic : Easing.InCubic }
                // Stopping to reverse skips this, so only a finished close unloads the pane.
                ScriptAction { script: if (!appState.expanded) window.immersiveClosing = false }
            }
        }

    }

    DockPanel {
        id: lyricsSidebar
        objectName: "lyricsSidebar"
        dock: "Lyrics"
        shown: showLyricsDock
        anchors.top: parent.top
        anchors.right: showQueueDock ? queueSidebar.left : parent.right
        anchors.bottom: player.top
        width: fittedLyricsWidth
        Rectangle { width: 1; height: parent.height; color: themeState.border }
        DockHeader { id: lyricsHeader; title: "Lyrics"; tabbed: window.tabbedDocks; onCloseRequested: appState.setLyricsOpen(false) }
        LyricsPane { anchors.fill: parent; anchors.topMargin: 48; anchors.leftMargin: 16; anchors.rightMargin: 16 }
        PanelResizeHandle {
            objectName: "lyricsResizeHandle"
            panelWidth: lyricsSidebar.width
            onResized: function(value) { appState.setLyricsWidth(value) }
            onFinished: appState.saveSidebarWidths()
        }
    }

    DockPanel {
        id: queueSidebar
        objectName: "queueSidebar"
        dock: "Queue"
        shown: showQueueDock
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: player.top
        width: fittedQueueWidth
        Rectangle { width: 1; height: parent.height; color: themeState.border }
        DockHeader { id: queueHeader; title: "Queue"; tabbed: window.tabbedDocks; onCloseRequested: appState.setQueueOpen(false) }
        QueuePane { anchors.fill: parent; anchors.topMargin: 48; showCloseButton: false }
        PanelResizeHandle {
            objectName: "queueResizeHandle"
            panelWidth: queueSidebar.width
            onResized: function(value) { appState.setQueueWidth(value) }
            onFinished: appState.saveSidebarWidths()
        }
    }

    PlayerBar {
        id: player
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 12
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: player.top; anchors.bottomMargin: 16
        width: Math.min(600, uiRoot.width - 80); height: playbackMessage.implicitHeight + 24
        radius: 6; color: themeState.hover; visible: playbackMessage.text.length > 0
        Text { id: playbackMessage; anchors.fill: parent; anchors.margins: 12; text: browseState.queueMessage || actionsState.message || libraryState.message || playerState.message || downloadsState.message; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.foreground; font.pixelSize: 14 }
    }

    AccountDialog { id: accountDialog }
    AppearanceSettings { id: appearanceSettings; host: settingsDialog; dialogParent: uiRoot }
    Connections { target: appState; function onAccountDialogRequested() { accountDialog.open() } }
    Connections { target: appState; function onPageChanged() { if (appState.page === "Search") header.showQuery(appState.query) } }
    MediaMenu { id: mediaMenu }
    PlaylistDialogs { id: playlistDialogs; anchors.fill: parent }
    Connections { target: appState; function onMenuRequested(media, context) { if (trayState.popupActive) return; mediaMenu.media = media; mediaMenu.context = context; mediaMenu.popup() } }
    ThemedDialog {
        id: shortcutHelp
        objectName: "shortcutHelpDialog"
        height: Math.min(implicitHeight, uiRoot.height - 48)
        width: Math.min(580, uiRoot.width - 80)
        anchors.centerIn: parent
        title: "Keyboard Shortcuts"
        contentItem: ScrollView {
            id: shortcutScroll
            clip: true
            implicitHeight: shortcutText.implicitHeight
            Label {
            id: shortcutText
            width: shortcutScroll.availableWidth
            wrapMode: Text.Wrap
            color: themeState.foreground; lineHeight: 1.7
            text: "Space — Play / pause\nShift+N / Shift+P — Next / previous\nLeft / Right — Seek 5 seconds\nShift+Left / Shift+Right — Seek 10 seconds\n+ / − — Volume\nM — Mute\nS / R — Shuffle / repeat\nF / Escape — Open / close immersive player\n/ or Ctrl+F — Search\nAlt+Left — Back\nAlt+Up / Alt+Down — Move focused queue entry\nDelete — Remove focused queue entry"
        }
        }
    }
    Shortcut { sequence: "Alt+Left"; enabled: window.playbackShortcuts; onActivated: { appState.setExpanded(false); browseState.back() } }
    Shortcut { sequence: "/"; enabled: window.playbackShortcuts; onActivated: window.focusSearch() }
    Shortcut { sequence: "Ctrl+F"; enabled: !window.modalOpen; onActivated: window.focusSearch() }
    Shortcut { sequence: "Space"; enabled: window.playbackShortcuts; onActivated: playerState.togglePlayback() }
    Shortcut { sequence: "Shift+N"; enabled: window.playbackShortcuts; onActivated: playerState.next() }
    Shortcut { sequence: "Shift+P"; enabled: window.playbackShortcuts; onActivated: playerState.previous() }
    Shortcut { sequence: "Left"; enabled: window.playbackShortcuts; onActivated: playerState.seek(playerState.position - 5) }
    Shortcut { sequence: "Right"; enabled: window.playbackShortcuts; onActivated: playerState.seek(playerState.position + 5) }
    Shortcut { sequence: "Shift+Left"; enabled: window.playbackShortcuts; onActivated: playerState.seek(playerState.position - 10) }
    Shortcut { sequence: "Shift+Right"; enabled: window.playbackShortcuts; onActivated: playerState.seek(playerState.position + 10) }
    Shortcut { sequences: ["+", "="]; enabled: window.playbackShortcuts; onActivated: appState.setVolume(appState.volume + 5) }
    Shortcut { sequence: "-"; enabled: window.playbackShortcuts; onActivated: appState.setVolume(appState.volume - 5) }
    Shortcut { sequence: "M"; enabled: window.playbackShortcuts; onActivated: appState.toggleMute() }
    Shortcut { sequence: "S"; enabled: window.playbackShortcuts; onActivated: appState.requestAction("shuffle") }
    Shortcut { sequence: "R"; enabled: window.playbackShortcuts; onActivated: appState.requestAction("repeat") }
    Shortcut { sequence: "F"; enabled: window.playbackShortcuts && playerState.hasTrack; onActivated: appState.requestAction("expandPlayer") }
    Shortcut { sequence: "Escape"; enabled: window.playbackShortcuts && appState.expanded; onActivated: appState.setExpanded(false) }
    Shortcut { sequence: "?"; enabled: window.playbackShortcuts; onActivated: shortcutHelp.open() }
    }
}
