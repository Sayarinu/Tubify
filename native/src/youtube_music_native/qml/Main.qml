import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Effects
import QtQuick.Window
import "Theme.js" as Theme
import "components"
import "dialogs"
import "pages"
import "player"
import "settings"
import "shell"

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
    readonly property bool compactNavigation: !window.chromeHidden && window.panelOpen && uiRoot.width < 780
    onCompactNavigationChanged: navigationDrawer.close()
    readonly property bool panelOpen: appState.panel !== ""
    // The panel card keeps the player bar's margin from the window edge, from the bar and from the page.
    readonly property real panelGap: 12
    // The panel never takes the last 480 px from the page; below that it stops at its 280 px minimum.
    readonly property real panelBudget: Math.max(280, uiRoot.width - navigationEdge.width - 480 - 2 * panelGap)
    readonly property real panelWidth: Math.min(appState.panelWidth, panelBudget)
    // What the panel and its gaps take from the right of the window. The full player's background runs underneath.
    readonly property real panelSpace: panelOpen ? panelWidth + 2 * panelGap : 0
    // The same space, following the panel while it slides.
    readonly property real panelSlideSpace: (panelWidth + 2 * panelGap) * sidePanel.revealed
    function restorePanelFocus() {
        Qt.callLater(function() {
            // A panel sliding out is disabled at once, which drops its focus to the window root.
            var focused = window.activeFocusItem
            if (focused && (!focused.visible || !focused.enabled || !focused.parent)) {
                if (window.panelOpen) panelHeader.focusControl()
                else player.focusPanelToggle(sidePanel.page)
            }
        })
    }
    Component.onCompleted: lyricState.setActive(appState.lyricsOpen)
    Connections { target: appState; function onPanelChanged() { lyricState.setActive(appState.lyricsOpen); window.restorePanelFocus() } }
    property var browseFocus: null
    property real browseWidth: 0
    property real browseHeight: 0
    // While the expanded player slides, it holds its full-size geometry and the page and navigation stay beneath it.
    property bool immersiveClosing: false
    property bool immersiveOpening: false
    readonly property bool chromeHidden: appState.expanded && !immersiveOpening
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
        collapsed: window.chromeHidden
        width: window.chromeHidden ? 0 : window.compactNavigation ? navigationDrawer.width : Math.min(appState.sidebarWidth, Math.max(180, uiRoot.width - (window.panelOpen ? 280 + 480 + 2 * window.panelGap : 320)))
        anchors.top: parent.top
        anchors.bottom: window.compactNavigation ? parent.bottom : player.top
        onNavigated: navigationDrawer.close()
    }

    MainHeader {
        id: header
        anchors.left: navigationEdge.right
        // Follows the panel's slide, so its buttons never end up underneath the panel.
        anchors.right: parent.right
        anchors.rightMargin: window.panelSlideSpace
        dividerExtension: Math.min(window.panelGap, anchors.rightMargin)
        panelRevealed: sidePanel.revealed
        compactNavigation: window.compactNavigation
        collapsed: window.chromeHidden
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
            { title: "Connections", pages: [discordSettings, lastFmSettings] },
            { title: "Experimental Features", pages: [castSettings] },
            { title: "Support", pages: [updateSettings, troubleshootingSettings] }
        ]
        onClosed: header.focusSettingsButton()
    }
    LyricsSettings { id: lyricsSettings; host: settingsDialog }
    LastFmSettings { id: lastFmSettings; host: settingsDialog }
    LinkPreview { id: linkPreview }
    HandoffDialog { id: handoffDialog }
    CastPairingDialog { id: castPairingDialog }
    Connections {
        target: typeof castState !== "undefined" ? castState : null
        function onPairingRequested() { castPairingDialog.open() }
    }
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
        anchors.right: window.panelOpen ? sidePanel.left : parent.right
        anchors.rightMargin: window.panelOpen ? window.panelGap : 0
        anchors.top: reconnectBanner.bottom
        anchors.bottom: player.top
        anchors.bottomMargin: 12
        property real gutter: Theme.gutter(width)

        Loader {
            id: pages
            objectName: "browseLoader"
            // Keep the page and its viewport alive while the stage uses the available space.
            width: window.chromeHidden ? window.browseWidth : parent.width
            height: window.chromeHidden ? window.browseHeight : parent.height
            visible: !window.chromeHidden
            enabled: !appState.expanded
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
            // While sliding, hold the expanded geometry so the sidebar and header beneath it don't re-lay out the pane;
            // content sits above them, and the docks and player bar above it.
            readonly property bool covering: window.immersiveOpening || window.immersiveClosing
            property rect coverArea: Qt.rect(0, 0, 0, 0)
            x: covering ? coverArea.x - content.x : 0
            y: covering ? coverArea.y - content.y : 0
            width: covering ? coverArea.width : parent.width + window.panelSpace
            // The player reaches the bar; pages keep their gap above it.
            height: covering ? coverArea.height : parent.height + content.anchors.bottomMargin
            z: 1
            // Stays loaded between opens, so its artwork is already on screen when it slides in.
            active: playerState.hasTrack || appState.expanded || window.immersiveClosing
            visible: appState.expanded || covering
            // The closing pane only animates; input and focus belong to the pages beneath it.
            enabled: appState.expanded
            sourceComponent: Component { ExpandedPane { rightInset: window.panelSpace; slidingInset: window.panelSlideSpace } }
            onLoaded: if (appState.expanded) item.focusStage()
            transform: Translate { id: immersiveShift }
            property bool opening: true
            // Runs before the expanded flag flips, so the pane starts off-screen and the chrome is still laid out.
            function slide(entering) {
                immersiveSlide.stop()
                var shown = visible
                if (!covering) {
                    // Opening computes the area the pane will fill once the sidebar and header have gone.
                    var bannerHeight = reconnectBanner.visible ? reconnectBanner.height : 0
                    var gap = content.anchors.bottomMargin
                    coverArea = entering ? Qt.rect(0, bannerHeight, content.x + content.width + window.panelSpace, content.y + content.height + gap - bannerHeight)
                                         : Qt.rect(content.x, content.y, content.width + window.panelSpace, content.height + gap)
                }
                window.immersiveOpening = entering && !appState.reducedMotion
                window.immersiveClosing = !entering && !appState.reducedMotion
                if (appState.reducedMotion) {
                    immersiveShift.y = 0
                    return
                }
                // A fresh open starts below the content; reopening mid-close reverses from where it is.
                if (entering && !shown) immersiveShift.y = coverArea.height
                opening = entering
                immersiveTarget.to = entering ? 0 : coverArea.height
                immersiveSlide.start()
            }
            // The pane stays opaque: it still spans the sidebar while closing, so any fade would show its artwork over the page.
            SequentialAnimation {
                id: immersiveSlide
                NumberAnimation { id: immersiveTarget; target: immersiveShift; property: "y"; duration: Theme.motionSlow; easing.type: immersive.opening ? Easing.OutCubic : Easing.InCubic }
                // Stopping to reverse skips this, so the geometry is only released once a slide has finished.
                ScriptAction { script: { window.immersiveOpening = false; window.immersiveClosing = false } }
            }
        }

    }

    DockPanel {
        id: sidePanel
        objectName: "sidePanel"
        // Holds on to the panel being closed while it slides out.
        property string page: appState.panel
        Connections { target: appState; function onPanelChanged() { if (appState.panel) sidePanel.page = appState.panel } }
        property string queueTab: "Queue"
        shown: window.panelOpen
        anchors.top: parent.top; anchors.topMargin: window.panelGap
        anchors.right: parent.right; anchors.rightMargin: window.panelGap
        anchors.bottom: player.top; anchors.bottomMargin: window.panelGap
        width: window.panelWidth
        // Tinted from the artwork, and held back so the lyrics stay readable over bright covers.
        ArtworkBackdrop {
            objectName: "lyricsBackdrop"
            anchors.fill: parent
            visible: sidePanel.page === "Lyrics"
            opacity: 0.65
            source: playerState.currentTrack.thumbnail || ""
            mediaKey: playerState.currentTrack.videoId || playerState.currentTrack.id || ""
            // Rounded to the card; the software renderer has no masks and keeps square corners.
            layer.enabled: visible && GraphicsInfo.api !== GraphicsInfo.Software
            layer.effect: MultiEffect { maskEnabled: true; maskSource: panelMask; maskThresholdMin: 0.5; maskSpreadAtMin: 1; autoPaddingEnabled: false }
        }
        Rectangle { id: panelMask; anchors.fill: parent; radius: sidePanel.radius; visible: false; layer.enabled: true; layer.smooth: true }
        DockHeader {
            id: panelHeader
            // Its divider continues the line under the page header, whose height collapses in the full player.
            height: header.fullHeight - window.panelGap
            title: sidePanel.page === "NowPlaying" ? "Now Playing" : sidePanel.page
            tabs: sidePanel.page === "Queue" ? ["Queue", "Recently played"] : []
            currentTab: sidePanel.queueTab
            onTabSelected: tab => sidePanel.queueTab = tab
            onCloseRequested: appState.setPanel("")
        }
        LyricsPane { visible: sidePanel.page === "Lyrics"; anchors.fill: parent; anchors.topMargin: panelHeader.height; anchors.leftMargin: 16; anchors.rightMargin: 16 }
        QueuePane { visible: sidePanel.page === "Queue" && sidePanel.queueTab === "Queue"; anchors.fill: parent; anchors.topMargin: panelHeader.height; showCloseButton: false }
        RecentlyPlayedPane { visible: sidePanel.page === "Queue" && sidePanel.queueTab === "Recently played"; anchors.fill: parent; anchors.topMargin: panelHeader.height }
        NowPlayingPane { visible: sidePanel.page === "NowPlaying"; anchors.fill: parent; anchors.topMargin: panelHeader.height }
        Rectangle { objectName: "panelBorder"; anchors.fill: parent; radius: sidePanel.radius; color: "transparent"; border.color: themeState.border }
        PanelResizeHandle {
            objectName: "panelResizeHandle"
            panelWidth: sidePanel.width
            onResized: function(value) { appState.setPanelWidth(value) }
            onFinished: appState.saveSidebarWidths()
        }
    }

    // The bar floats with margins around it; the sliding player must not show through them.
    Rectangle {
        objectName: "playerBarBackdrop"
        visible: immersive.covering
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.top: player.top
        color: themeState.background
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
