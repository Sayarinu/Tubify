import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window
import "Theme.js" as Theme

ApplicationWindow {
    id: window
    visible: true
    width: appState.initialWidth
    height: appState.initialHeight
    minimumWidth: 920
    minimumHeight: 620
    title: appState.fixtureMode ? "YouTube Music · Visual fixture" : "YouTube Music"
    color: themeState.background
    font.family: Theme.bodyFont
    font.pixelSize: 14
    palette.window: themeState.surface
    palette.base: themeState.background
    palette.alternateBase: themeState.surface
    palette.button: themeState.surface
    palette.text: themeState.foreground
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
    property bool wideNavigation: true
    readonly property bool docksVisible: (appState.queueOpen || appState.lyricsOpen)
    readonly property bool bothDocks: appState.queueOpen && appState.lyricsOpen
    readonly property bool tabbedDocks: bothDocks && width - sidebar.width < 1040
    readonly property real dockBudget: Math.max(280, width - sidebar.width - (bothDocks && !tabbedDocks ? 480 : 320))
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
            if (window.activeFocusItem && !window.activeFocusItem.visible) {
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
    function focusSearch() {
        appState.setExpanded(false)
        Qt.callLater(function() { search.forceActiveFocus() })
    }
    Connections {
        target: appState
        function onPlayerViewChanging(entering) {
            if (entering) {
                window.browseFocus = window.activeFocusItem
                window.browseWidth = pages.width
                window.browseHeight = pages.height
            }
        }
        function onPlayerViewChanged() {
            Qt.callLater(function() {
                if (appState.expanded && immersive.item) immersive.item.focusStage()
                else if (window.browseFocus && window.browseFocus.visible && window.browseFocus.enabled) window.browseFocus.forceActiveFocus()
                else player.focusImmersiveToggle()
            })
        }
    }
    onClosing: appState.saveWindow(width, height)
    property bool editingText: activeFocusItem instanceof TextInput || activeFocusItem instanceof TextEdit
    property bool modalOpen: accountMenu.opened || appearanceMenu.opened || accountDialog.opened || settingsDialog.opened || lyricsSettings.opened || playlistDialogs.opened || shortcutHelp.opened || !!(pages.item && pages.item.objectName === "downloadsPane" && pages.item.blockingShortcuts)
    property bool playbackShortcuts: !editingText && !modalOpen && !mediaMenu.opened

    Rectangle {
        id: homeBackdrop
        objectName: "homeBackdrop"
        anchors.left: sidebar.right
        anchors.right: parent.right
        height: 370
        property bool heroVisible: !appState.expanded && appState.page === "Home" && catalogState.route === "home"
        property color themeTint: themeState.heroTint
        gradient: Gradient {
            GradientStop { position: 0; color: homeBackdrop.heroVisible ? homeBackdrop.themeTint : themeState.background }
            GradientStop { position: 1; color: themeState.background }
        }
    }

    Rectangle {
        id: sidebar
        objectName: "navigationRail"
        width: appState.expanded ? 0 : Math.min(appState.sidebarWidth, Math.max(180, window.width - (appState.queueOpen || appState.lyricsOpen ? 280 : 0) - 320))
        visible: !appState.expanded
        anchors.top: parent.top
        anchors.bottom: player.top
        color: themeState.background
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: themeState.border }
        Item {
            id: sidebarResizeHandle
            objectName: "sidebarResizeHandle"
            z: 10
            visible: true
            x: sidebar.width - width
            width: 12
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            HoverHandler { id: sidebarResizeHover; cursorShape: Qt.SizeHorCursor }
            Rectangle {
                anchors.centerIn: parent
                width: 2
                height: parent.height
                color: themeState.accent
                opacity: sidebarResizeHover.hovered || sidebarResizeMouse.pressed ? 0.9 : 0
            }
            MouseArea {
                id: sidebarResizeMouse
                anchors.fill: parent
                cursorShape: Qt.SizeHorCursor
                preventStealing: true
                property real startWidth: 240
                property real startX: 0
                onPressed: function(mouse) {
                    startWidth = sidebar.width
                    startX = sidebarResizeMouse.mapToItem(null, mouse.x, mouse.y).x
                }
                onPositionChanged: function(mouse) {
                    if (pressed) {
                        var sceneX = sidebarResizeMouse.mapToItem(null, mouse.x, mouse.y).x
                        appState.setSidebarWidth(startWidth + sceneX - startX)
                    }
                }
                onReleased: appState.saveSidebarWidths()
            }
        }
        Column {
            id: navigation
            x: 8; y: 8; width: sidebar.width - 16
            Repeater {
                model: [{label:"Home",icon:"home"}, {label:"Explore",icon:"explore"}, {label:"Library",icon:"library"}, {label:"Downloads",icon:"download"}]
                delegate: Button {
                    id: nav
                    required property var modelData
                    objectName: "navigationButton-" + modelData.label
                    readonly property bool selected: appState.page === text
                    hoverEnabled: true
                    width: navigation.width
                    height: 48
                    padding: 0
                    leftInset: 0; rightInset: 0; topInset: 0; bottomInset: 0
                    text: modelData.label
                    Accessible.name: text
                    onClicked: appState.navigate(text)
                    background: Rectangle {
                        objectName: "navigationBackground-" + nav.text
                        anchors.fill: parent
                        radius: 8
                        color: nav.selected ? themeState.selected : nav.hovered ? themeState.hover : "transparent"
                        border.width: nav.visualFocus ? 2 : 0
                        border.color: themeState.accent
                        Rectangle { objectName: "navigationMarker-" + nav.text; x: 4; anchors.verticalCenter: parent.verticalCenter; width: 3; height: 24; radius: 2; color: themeState.accent; visible: nav.selected }
                    }
                    contentItem: Row {
                        leftPadding: 16; spacing: 20
                        Symbol { anchors.verticalCenter: parent.verticalCenter; name: nav.modelData.icon; color: nav.selected ? themeState.accent : themeState.secondary }
                        Text { anchors.verticalCenter: parent.verticalCenter; visible: window.wideNavigation; text: nav.text; color: themeState.foreground; font.family: Theme.bodyFont; font.pixelSize: 16 }
                    }
                    ToolTip.text: text
                    ToolTip.visible: !window.wideNavigation && hovered
                }
            }
        }
        Rectangle { x: 16; y: navigation.y + navigation.height + 12; width: sidebar.width - 48; height: 1; color: themeState.border }
        Button {
            id: newPlaylist
            x: 12; y: navigation.y + navigation.height + 24
            width: sidebar.width - 24; height: 40
            text: window.wideNavigation ? "+  New playlist" : "+"
            Accessible.name: "New playlist"
            ToolTip.text: "New playlist"
            ToolTip.visible: hovered
            font.pixelSize: 14
            palette.buttonText: themeState.foreground
            background: Rectangle { radius: 20; color: newPlaylist.hovered ? themeState.hover : themeState.surface; border.width: newPlaylist.visualFocus ? 2 : 0; border.color: themeState.foreground }
            onClicked: appState.requestAction("newPlaylist")
        }
        ListView {
            anchors.top: newPlaylist.bottom
            anchors.topMargin: 12
            anchors.bottom: parent.bottom
            width: parent.width
            clip: true
            model: appState.playlists
            delegate: ItemDelegate {
                required property var modelData
                width: ListView.view.width
                height: 56
                padding: 0
                Accessible.name: modelData.title
                ToolTip.text: modelData.title
                ToolTip.visible: hovered && !window.wideNavigation
                contentItem: Item {
                    Cover { x: 16; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; radius: 8; source: modelData.thumbnail || ""; mediaKey: "playlist:" + modelData.id; accent: themeState.selected }
                    Column {
                        x: 68; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 80; spacing: 4
                        visible: window.wideNavigation
                        Text { width: parent.width; text: modelData.title; textFormat: Text.PlainText; color: themeState.foreground; font.pixelSize: 14; elide: Text.ElideRight }
                        Text { width: parent.width; text: modelData.owner || ""; textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 12; elide: Text.ElideRight }
                    }
                }
                background: Rectangle { radius: 8; color: parent.hovered ? themeState.hover : "transparent"; border.color: parent.visualFocus ? themeState.accent : "transparent" }
                onClicked: appState.requestAction("playlist:" + modelData.id)
            }
        }
    }

    Item {
        id: header
        objectName: "mainHeader"
        anchors.left: sidebar.right
        anchors.right: showLyricsDock ? lyricsSidebar.left : showQueueDock ? queueSidebar.left : parent.right
        height: appState.expanded ? 0 : 64
        visible: !appState.expanded
        IconButton { x: header.width < 480 ? 8 : 40; y: 10; width: 44; height: 44; iconName: "back"; tip: "Back"; outlined: true; onClicked: { appState.setExpanded(false); browseState.back() } }
        TextField {
            id: search
            objectName: "searchField"
            x: header.width < 480 ? 56 : 96
            y: 11
            width: Math.max(96, Math.min(480, (historyButton.visible ? historyButton.x : settingsButton.x) - x - 12))
            height: 42
            leftPadding: 52
            rightPadding: text.length > 0 ? 48 : 16
            color: themeState.foreground
            placeholderText: "Search songs, albums, artists"
            placeholderTextColor: themeState.muted
            font.pixelSize: 16
            selectByMouse: true
            Accessible.name: "Search YouTube Music"
            background: Rectangle { radius: 12; color: search.activeFocus ? themeState.hover : themeState.surface; border.color: search.activeFocus ? themeState.accent : themeState.border; border.width: 1 }
            Symbol { x: 16; anchors.verticalCenter: parent.verticalCenter; name: "search"; width: 20; height: 20; color: themeState.secondary }
            IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; visible: search.text.length > 0; iconName: "close"; tip: "Clear search"; onClicked: { search.clear(); searchState.clearSuggestions(); search.forceActiveFocus() } }
            onAccepted: {
                var chosen = suggestions.currentIndex >= 0 ? searchState.suggestions[suggestions.currentIndex] : search.text
                search.text = chosen
                appState.search(chosen)
            }
            onTextEdited: { suggestions.currentIndex = -1; searchState.suggest(text) }
            Keys.onDownPressed: suggestions.currentIndex = Math.min(suggestions.count - 1, suggestions.currentIndex + 1)
            Keys.onUpPressed: suggestions.currentIndex = Math.max(-1, suggestions.currentIndex - 1)
            Keys.onEscapePressed: searchState.clearSuggestions()
            Popup {
                id: suggestionPopup
                y: search.height + 4; width: search.width
                height: Math.min(360, searchState.suggestions.length * 44 + 16)
                padding: 8; focus: false
                visible: search.activeFocus && searchState.suggestions.length > 0
                background: Rectangle { color: themeState.hover; radius: 8 }
                contentItem: ListView {
                    id: suggestions
                    clip: true; currentIndex: -1; model: searchState.suggestions
                    delegate: ItemDelegate {
                        required property string modelData
                        required property int index
                        width: suggestions.width; height: 44
                        highlighted: index === suggestions.currentIndex
                        background: Rectangle { color: parent.highlighted ? themeState.selected : parent.hovered ? themeState.hover : "transparent"; radius: 4 }
                        contentItem: Text { text: modelData; textFormat: Text.PlainText; color: themeState.foreground; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; font.pixelSize: 15 }
                        onClicked: { search.text = modelData; appState.search(modelData) }
                    }
                }
            }
        }
        IconButton {
            id: profileButton
            objectName: "profileButton"
            anchors.right: parent.right
            anchors.rightMargin: header.width < 480 ? 8 : 32
            y: 10
            width: 44; height: 44
            iconName: "profile"
            tip: accountState.profile.name || "Account"
            onClicked: {
                if (accountState.connected) accountMenu.popup(profileButton, profileButton.width - accountMenu.implicitWidth, profileButton.height, null)
                else accountDialog.open()
            }
            contentItem: Item {
                Avatar {
                    anchors.centerIn: parent
                    width: 28; height: 28
                    source: accountState.profile.avatar || ""
                }
            }
        }
        IconButton { id: settingsButton; objectName: "settingsButton"; anchors.right: profileButton.left; anchors.rightMargin: 12; y: 10; width: 44; height: 44; iconName: "settings"; tip: "Settings"; onClicked: appearanceMenu.popup(settingsButton, settingsButton.width - appearanceMenu.implicitWidth, settingsButton.height, null) }
        IconButton { id: historyButton; objectName: "historyButton"; visible: header.width >= 640; anchors.right: settingsButton.left; anchors.rightMargin: 12; y: 10; width: 44; height: 44; iconName: "history"; tip: "Listening history"; onClicked: libraryState.history() }
    }

    Menu {
        id: accountMenu
        objectName: "accountMenu"
        implicitWidth: 252
        padding: 8
        spacing: 2
        background: Rectangle { radius: 12; color: themeState.surface; border.color: themeState.border; border.width: 1 }
        MenuItem {
            enabled: false
            implicitHeight: 42
            contentItem: Item {
                Text {
                    anchors.fill: parent
                    verticalAlignment: Text.AlignVCenter
                    text: accountState.profile.name || "YouTube Music account"
                    color: themeState.foreground
                    font.pixelSize: 14
                    font.bold: true
                    elide: Text.ElideRight
                }
            }
            background: Rectangle { color: "transparent" }
        }
        MenuSeparator {}
        ContextMenuItem { text: "Connection Settings"; onTriggered: accountDialog.open() }
        MenuSeparator { visible: accountState.connected; height: visible ? implicitHeight : 0 }
        ContextMenuItem { text: "Sign Out"; visible: accountState.connected; height: visible ? implicitHeight : 0; onTriggered: accountState.signOut() }
    }

    Menu {
        id: appearanceMenu
        objectName: "appearanceMenu"
        implicitWidth: 220
        padding: 8
        spacing: 2
        background: Rectangle { radius: 12; color: themeState.surface; border.color: themeState.border; border.width: 1 }
        ContextMenuItem { text: "Appearance Settings"; onTriggered: settingsDialog.open() }
        ContextMenuItem { text: "Lyrics Settings"; onTriggered: lyricsSettings.open() }
    }
    LyricsSettings { id: lyricsSettings }

    Rectangle {
        id: reconnectBanner
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.top: header.bottom
        visible: accountState.reconnect
        height: visible ? 44 : 0
        color: "#352724"
        Text {
            anchors.left: parent.left; anchors.leftMargin: 24
            anchors.right: reconnectButton.left; anchors.rightMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            text: "Reconnect your account. Downloaded music remains available."
            textFormat: Text.PlainText
            color: themeState.foreground; font.pixelSize: 14; elide: Text.ElideRight
        }
        Button { id: reconnectButton; anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; text: "Reconnect"; onClicked: appState.openAccount() }
    }

    Item {
        id: content
        objectName: "pageContent"
        anchors.left: sidebar.right
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
            anchors.fill: parent
            active: appState.expanded
            sourceComponent: Component { ExpandedPane {} }
            onLoaded: item.focusStage()
        }

    }

    Rectangle {
        id: lyricsSidebar
        objectName: "lyricsSidebar"
        anchors.top: parent.top
        anchors.right: showQueueDock ? queueSidebar.left : parent.right
        anchors.bottom: player.top
        width: fittedLyricsWidth
        visible: showLyricsDock
        color: themeState.background
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

    Rectangle {
        id: queueSidebar
        objectName: "queueSidebar"
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: player.top
        width: fittedQueueWidth
        visible: showQueueDock
        color: themeState.background
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
        width: Math.min(600, window.width - 80); height: playbackMessage.implicitHeight + 24
        radius: 6; color: themeState.hover; visible: playbackMessage.text.length > 0
        Text { id: playbackMessage; anchors.fill: parent; anchors.margins: 12; text: browseState.queueMessage || actionsState.message || libraryState.message || playerState.message || downloadsState.message; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.foreground; font.pixelSize: 14 }
    }

    Popup {
        id: accountDialog
        objectName: "accountDialog"
        anchors.centerIn: Overlay.overlay
        width: Math.min(window.width - 64, 440)
        modal: true
        padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { radius: 16; color: themeState.surface; border.color: themeState.border; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 14
            RowLayout {
                Layout.fillWidth: true
                Label { Layout.fillWidth: true; text: "Connection Settings"; color: themeState.foreground; font.pixelSize: 15; font.bold: true }
                IconButton { iconName: "close"; tip: "Close"; iconSize: 18; implicitWidth: 34; implicitHeight: 34; onClicked: accountDialog.close() }
            }
            Label { Layout.fillWidth: true; text: "Current User:"; horizontalAlignment: Text.AlignHCenter; color: themeState.secondary; font.pixelSize: 13 }
            Label { Layout.fillWidth: true; text: accountState.profile.name || "Not signed in"; horizontalAlignment: Text.AlignHCenter; color: themeState.foreground; font.pixelSize: 21; font.bold: true; elide: Text.ElideRight }
            Button {
                Layout.fillWidth: true; Layout.preferredHeight: 44
                text: "Use Existing Desktop App Session"
                visible: accountState.tauriAvailable && !accountState.fixtureMode && !accountState.connected; enabled: !accountState.busy
                contentItem: Text { text: parent.text; color: themeState.onAccent; font.pixelSize: 14; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 20; color: parent.down ? themeState.accent : parent.hovered ? themeState.accentHover : themeState.accent; border.width: parent.visualFocus ? 2 : 0; border.color: themeState.foreground }
                onClicked: accountState.importTauri()
            }
            Button {
                Layout.fillWidth: true; Layout.preferredHeight: 44
                text: "Choose Browser Session File"
                enabled: !accountState.busy && !accountState.fixtureMode
                contentItem: Text { text: parent.text; color: themeState.foreground; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 20; color: parent.down ? themeState.border : parent.hovered ? themeState.surface : "transparent"; border.width: parent.visualFocus ? 2 : 1; border.color: parent.visualFocus ? themeState.accent : themeState.border }
                onClicked: sessionPicker.open()
            }
            BusyIndicator { Layout.alignment: Qt.AlignHCenter; running: accountState.busy; visible: running }
            Label { Layout.fillWidth: true; text: accountState.message; textFormat: Text.PlainText; visible: text.length > 0 && !accountState.connected; wrapMode: Text.Wrap; color: themeState.secondary }
            Button {
                Layout.fillWidth: true; Layout.preferredHeight: 38
                text: "Sign Out"; visible: accountState.connected
                contentItem: Text { text: parent.text; color: themeState.foreground; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 19; color: parent.hovered ? themeState.surface : "transparent"; border.color: themeState.border; border.width: 1 }
                onClicked: { accountState.signOut(); accountDialog.close() }
            }
            Button {
                Layout.fillWidth: true; Layout.preferredHeight: 34
                text: "Export Instructions"
                contentItem: Text { text: parent.text; color: themeState.foreground; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 17; color: parent.hovered ? themeState.hover : "transparent" }
                onClicked: Qt.openUrlExternally("https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html")
            }
        }
    }
    Popup {
        id: settingsDialog
        objectName: "appearanceSettingsDialog"
        anchors.centerIn: Overlay.overlay
        width: Math.min(window.width - 48, 720)
        height: Math.min(window.height - 48, 590)
        modal: true
        padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        property string activeColorRole: ""
        property color pickerColor: "white"
        property bool editingColors: false
        background: Rectangle { radius: 16; color: themeState.surface; border.color: themeState.border; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                Label {
                    Layout.fillWidth: true
                    text: settingsDialog.editingColors ? "Customize " + themeState.activeThemeName : "Appearance Settings"
                    color: themeState.foreground; font.pixelSize: 16; font.bold: true
                }
                ThemeActionButton {
                    id: addThemeButton
                    objectName: "addThemeButton"
                    visible: !settingsDialog.editingColors
                    text: "Add Theme"
                    primary: true
                    onClicked: addThemeMenu.popup(addThemeButton, addThemeButton.width - addThemeMenu.implicitWidth, addThemeButton.height, null)
                }
                ThemeActionButton {
                    visible: settingsDialog.editingColors
                    text: "Back to themes"
                    onClicked: settingsDialog.editingColors = false
                }
                IconButton { iconName: "close"; tip: "Close"; iconSize: 18; implicitWidth: 34; implicitHeight: 34; onClicked: settingsDialog.close() }
            }
            StackLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                currentIndex: settingsDialog.editingColors ? 1 : 0
                Item {
                    ColumnLayout {
                        anchors.fill: parent; spacing: 8
                        ScrollView {
                            id: themeScroll
                            objectName: "themeScroll"
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true
                            ScrollBar.vertical.policy: ScrollBar.AsNeeded
                            ColumnLayout {
                                width: themeScroll.availableWidth
                                spacing: 6
                                Label { text: "Dark themes"; color: themeState.secondary; font.pixelSize: 12; font.bold: true }
                                GridView {
                                    id: darkThemeGrid
                                    objectName: "darkThemeGrid"
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Math.ceil(themeState.darkThemes.length / 2) * 50
                                    clip: true; interactive: false; cellWidth: width / 2; cellHeight: 50
                                    model: themeState.darkThemes
                                    delegate: themeCardDelegate
                                }
                                Label { text: "Light themes"; color: themeState.secondary; font.pixelSize: 12; font.bold: true }
                                GridView {
                                    id: lightThemeGrid
                                    objectName: "lightThemeGrid"
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Math.max(50, Math.ceil(themeState.lightThemes.length / 2) * 50)
                                    clip: true; interactive: false; cellWidth: width / 2; cellHeight: 50
                                    model: themeState.lightThemes
                                    delegate: themeCardDelegate
                                }
                            }
                        }
                        Label {
                            Layout.fillWidth: true
                            visible: !settingsDialog.editingColors && themeState.message.length > 0
                            text: themeState.message
                            color: themeState.foreground
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 8
                            ThemeActionButton { objectName: "themeEditColorsButton"; text: "Edit colors"; enabled: themeState.activeThemeIsCustom; disabledReason: "Create a custom theme before editing colors."; onClicked: settingsDialog.editingColors = true }
                            ThemeActionButton { objectName: "themeRenameButton"; text: "Rename"; enabled: themeState.activeThemeIsCustom; disabledReason: "Built-in themes cannot be renamed. Create a custom theme first."; onClicked: { themeNameDialog.renameMode = true; themeNameField.text = themeState.activeThemeName; themeNameDialog.open() } }
                            ThemeActionButton { objectName: "themeDeleteButton"; text: "Delete"; enabled: themeState.activeThemeIsCustom; disabledReason: "Built-in themes cannot be deleted. Create a custom theme first."; onClicked: deleteThemeDialog.open() }
                            Item { Layout.fillWidth: true }
                            ThemeActionButton { objectName: "themeExportButton"; text: "Export current theme"; enabled: themeState.activeThemeIsCustom; disabledReason: "Only custom themes can be exported. Create a custom theme first."; onClicked: themeExportDialog.open() }
                        }
                    }
                }
                Item {
                    ColumnLayout {
                        anchors.fill: parent; spacing: 8
                        Label { Layout.fillWidth: true; text: "Adjust all eleven colors in this custom theme."; color: themeState.secondary; font.pixelSize: 12; wrapMode: Text.Wrap }
                        GridView {
                            id: colorRoles
                            objectName: "colorRoles"
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true; cellWidth: width / 2; cellHeight: 52
                            model: themeState.palette
                            delegate: RowLayout {
                                required property var modelData
                                width: colorRoles.cellWidth - 8; height: colorRoles.cellHeight - 4; spacing: 7
                                Button {
                                    Layout.preferredWidth: 28; Layout.preferredHeight: 28; padding: 0
                                    ToolTip.text: "Choose color"; ToolTip.visible: hovered
                                    background: Rectangle { radius: 8; color: modelData.value; border.color: themeState.border; border.width: 1 }
                                    onClicked: {
                                        settingsDialog.activeColorRole = modelData.key
                                        settingsDialog.pickerColor = modelData.value
                                        palettePicker.setDraft(modelData.value)
                                        palettePicker.open()
                                    }
                                }
                                Label { Layout.fillWidth: true; text: modelData.label; color: themeState.foreground; elide: Text.ElideRight; font.pixelSize: 11 }
                                TextField {
                                    Layout.preferredWidth: 82
                                    text: modelData.value
                                    maximumLength: 7; color: themeState.foreground; selectByMouse: true
                                    font.pixelSize: 11; horizontalAlignment: TextInput.AlignHCenter
                                    background: Rectangle { radius: 7; color: themeState.background; border.color: parent.activeFocus ? themeState.accent : "transparent"; border.width: parent.activeFocus ? 1 : 0 }
                                    onEditingFinished: themeState.setColor(modelData.key, text)
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { Layout.fillWidth: true; text: themeState.message; textFormat: Text.PlainText; visible: text.length > 0; color: themeState.secondary; font.pixelSize: 11; wrapMode: Text.Wrap; maximumLineCount: 2 }
                            ThemeActionButton { text: "View config"; onClicked: themeState.openConfigFile() }
                        }
                    }
                }
            }
        }
    }
    Component {
        id: themeCardDelegate
        Rectangle {
            required property var modelData
            width: darkThemeGrid.cellWidth - 8; height: darkThemeGrid.cellHeight - 6; radius: 9
            color: modelData.active ? themeState.selected : themeState.background
            border.color: modelData.active ? themeState.accent : themeState.border
            border.width: modelData.active ? 2 : 1
            RowLayout {
                anchors.fill: parent; anchors.margins: 9; spacing: 9
                Row {
                    spacing: -5
                    Repeater {
                        model: modelData.swatches
                        delegate: Rectangle {
                            required property string modelData
                            width: 22; height: 22; radius: 11
                            color: modelData; border.color: themeState.foreground; border.width: 1
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 1
                    Text { Layout.fillWidth: true; text: modelData.name; color: themeState.foreground; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight }
                    Text { text: modelData.builtin ? "Built-in" : "Custom"; color: themeState.secondary; font.pixelSize: 10 }
                }
                Symbol { visible: modelData.active; name: "check"; width: 16; height: 16; color: themeState.accent }
            }
            MouseArea { anchors.fill: parent; onClicked: themeState.selectTheme(modelData.id) }
        }
    }
    Menu {
        id: addThemeMenu
        objectName: "addThemeMenu"
        implicitWidth: 230
        padding: 8
        spacing: 2
        background: Rectangle { radius: 12; color: themeState.surface; border.color: themeState.border; border.width: 1 }
        ContextMenuItem { text: "Create from current"; onTriggered: { themeNameDialog.renameMode = false; themeNameField.text = ""; themeNameDialog.open() } }
        ContextMenuItem { text: "Import theme…"; onTriggered: themeImportDialog.open() }
    }
    Dialog {
        id: themeNameDialog
        anchors.centerIn: Overlay.overlay
        width: 390
        modal: true; title: renameMode ? "Rename Theme" : "Create Custom Theme"
        standardButtons: Dialog.NoButton
        property bool renameMode: false
        contentItem: ColumnLayout {
            spacing: 10
            Label { Layout.fillWidth: true; text: themeNameDialog.renameMode ? "Choose a new name for this custom theme." : "Your new theme starts with the current colors."; wrapMode: Text.Wrap }
            TextField { id: themeNameField; objectName: "themeNameField"; Layout.fillWidth: true; placeholderText: "Theme name"; maximumLength: 60; onAccepted: themeNameSave.clicked() }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: themeNameDialog.close() }
                ThemeActionButton {
                    id: themeNameSave; text: themeNameDialog.renameMode ? "Save" : "Create"; highlighted: true
                    onClicked: {
                        var ok = themeNameDialog.renameMode
                            ? themeState.renameCustomTheme(themeState.activeThemeId, themeNameField.text)
                            : themeState.createCustomTheme(themeNameField.text)
                        if (ok) { themeNameDialog.close(); settingsDialog.editingColors = true }
                    }
                }
            }
        }
    }
    Dialog {
        id: deleteThemeDialog
        anchors.centerIn: Overlay.overlay
        width: 390
        modal: true; title: "Delete Custom Theme?"; standardButtons: Dialog.NoButton
        contentItem: ColumnLayout {
            spacing: 10
            Label { Layout.fillWidth: true; text: "Delete “" + themeState.activeThemeName + "”? Classic will become active if this is the selected theme."; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: deleteThemeDialog.close() }
                ThemeActionButton { text: "Delete"; primary: true; onClicked: { themeState.deleteCustomTheme(themeState.activeThemeId); deleteThemeDialog.close() } }
            }
        }
    }
    Dialog {
        id: importThemeDialog
        anchors.centerIn: Overlay.overlay
        width: 420
        modal: true; title: "Import Theme"; standardButtons: Dialog.NoButton
        property bool replaceCustom: false
        contentItem: ColumnLayout {
            spacing: 10
            Label { Layout.fillWidth: true; text: importThemeDialog.replaceCustom ? "A custom theme already uses this name. Save to replace it, or choose another name." : "Name this imported custom theme. Built-in themes are protected and cannot be replaced."; wrapMode: Text.Wrap }
            TextField { id: importThemeName; Layout.fillWidth: true; placeholderText: "Theme name"; maximumLength: 60 }
            Label { Layout.fillWidth: true; text: themeState.message; visible: text.length > 0; color: "#ffb4a6"; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true; Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: importThemeDialog.close() }
                ThemeActionButton {
                    text: importThemeDialog.replaceCustom ? "Replace" : "Import"; primary: true
                    onClicked: {
                        if (themeState.completeImport(importThemeName.text, importThemeDialog.replaceCustom)) {
                            importThemeDialog.close(); settingsDialog.editingColors = false
                        }
                    }
                }
            }
        }
    }
    FileDialog {
        id: themeImportDialog
        title: "Import a Theme"; fileMode: FileDialog.OpenFile
        nameFilters: ["Theme files (*.json)", "All files (*)"]
        onAccepted: {
            var result = themeState.inspectImport(selectedFile.toString())
            if (result.ok) {
                importThemeDialog.replaceCustom = !!result.conflict && !result.builtIn
                importThemeName.text = result.name
                importThemeDialog.open()
            }
        }
    }
    FileDialog {
        id: themeExportDialog
        title: "Export Custom Theme"; fileMode: FileDialog.SaveFile
        nameFilters: ["Theme files (*.json)"]
        defaultSuffix: "json"
        onAccepted: themeState.exportTheme(selectedFile.toString())
    }
    Popup {
        id: palettePicker
        objectName: "colorPickerDialog"
        anchors.centerIn: Overlay.overlay
        width: Math.min(window.width - 48, 430)
        padding: 20
        modal: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        property string draftHex: "#A78BFA"
        property color previewColor: "#A78BFA"
        property real hue: 0.72
        property real saturation: 0.42
        property real value: 0.98
        property string statusMessage: ""
        function setDraft(hex) {
            draftHex = hex.toUpperCase()
            statusMessage = ""
            if (!/^#[0-9A-F]{6}$/.test(draftHex)) return
            var red = parseInt(draftHex.slice(1, 3), 16) / 255
            var green = parseInt(draftHex.slice(3, 5), 16) / 255
            var blue = parseInt(draftHex.slice(5, 7), 16) / 255
            var high = Math.max(red, green, blue)
            var low = Math.min(red, green, blue)
            var delta = high - low
            value = high
            saturation = high === 0 ? 0 : delta / high
            if (delta === 0) hue = 0
            else if (high === red) hue = ((green - blue) / delta + (green < blue ? 6 : 0)) / 6
            else if (high === green) hue = ((blue - red) / delta + 2) / 6
            else hue = ((red - green) / delta + 4) / 6
            previewColor = draftHex
        }
        function updateFromField() {
            previewColor = Qt.hsva(hue, saturation, value, 1)
            draftHex = previewColor.toString().toUpperCase()
        }
        function applyColor() {
            if (/^#[0-9A-Fa-f]{6}$/.test(draftHex)) {
                themeState.setColor(settingsDialog.activeColorRole, draftHex)
                close()
            }
        }
        background: Rectangle { radius: 16; color: themeState.surface; border.color: themeState.border; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 14
            RowLayout {
                Layout.fillWidth: true
                Label { Layout.fillWidth: true; text: "Choose a Color"; color: themeState.foreground; font.pixelSize: 15; font.bold: true }
                IconButton {
                    iconName: "pipette"; tip: "Pick a color from the screen"; iconSize: 19; implicitWidth: 34; implicitHeight: 34
                    onClicked: { palettePicker.close(); settingsDialog.close(); screenPickerOverlay.show() }
                }
                IconButton { iconName: "close"; tip: "Close"; iconSize: 18; implicitWidth: 34; implicitHeight: 34; onClicked: palettePicker.close() }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 12
                Rectangle { Layout.preferredWidth: 38; Layout.preferredHeight: 38; radius: 12; color: palettePicker.previewColor; border.color: themeState.border; border.width: 1 }
                TextField {
                    Layout.fillWidth: true
                    text: palettePicker.draftHex
                    maximumLength: 7
                    selectByMouse: true
                    color: themeState.foreground
                    font.pixelSize: 14
                    horizontalAlignment: TextInput.AlignHCenter
                    background: Rectangle { radius: 18; color: themeState.background; border.color: parent.activeFocus ? themeState.accent : themeState.border; border.width: 1 }
                    onTextEdited: {
                        if (/^#[0-9A-Fa-f]{6}$/.test(text)) palettePicker.setDraft(text)
                    }
                    onAccepted: palettePicker.applyColor()
                }
            }
            Rectangle {
                id: saturationValueField
                Layout.fillWidth: true; Layout.preferredHeight: 156
                radius: 10; clip: true
                color: Qt.hsva(palettePicker.hue, 1, 1, 1)
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "white" }
                        GradientStop { position: 1; color: "transparent" }
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0; color: "transparent" }
                        GradientStop { position: 1; color: "black" }
                    }
                }
                Rectangle {
                    x: palettePicker.saturation * (parent.width - width)
                    y: (1 - palettePicker.value) * (parent.height - height)
                    width: 14; height: 14; radius: 7
                    color: "transparent"; border.color: "white"; border.width: 2
                    Rectangle { anchors.centerIn: parent; width: 4; height: 4; radius: 2; color: "transparent"; border.color: "#55000000"; border.width: 1 }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.CrossCursor
                    function selectPoint(mouse) {
                        palettePicker.saturation = Math.max(0, Math.min(1, mouse.x / width))
                        palettePicker.value = 1 - Math.max(0, Math.min(1, mouse.y / height))
                        palettePicker.updateFromField()
                    }
                    onPressed: function(mouse) { selectPoint(mouse) }
                    onPositionChanged: function(mouse) { if (pressed) selectPoint(mouse) }
                }
            }
            Slider {
                id: hueSlider
                Layout.fillWidth: true; Layout.preferredHeight: 26
                from: 0; to: 1; value: palettePicker.hue
                onMoved: { palettePicker.hue = value; palettePicker.updateFromField() }
                background: Rectangle {
                    x: hueSlider.leftPadding; y: hueSlider.topPadding + (hueSlider.availableHeight - height) / 2
                    width: hueSlider.availableWidth; height: 10; radius: 5
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "#ff0000" }
                        GradientStop { position: 0.17; color: "#ffff00" }
                        GradientStop { position: 0.33; color: "#00ff00" }
                        GradientStop { position: 0.5; color: "#00ffff" }
                        GradientStop { position: 0.67; color: "#0000ff" }
                        GradientStop { position: 0.83; color: "#ff00ff" }
                        GradientStop { position: 1; color: "#ff0000" }
                    }
                }
                handle: Rectangle {
                    x: hueSlider.leftPadding + hueSlider.visualPosition * (hueSlider.availableWidth - width)
                    y: hueSlider.topPadding + (hueSlider.availableHeight - height) / 2
                    width: 18; height: 18; radius: 9; color: "white"
                    border.color: themeState.border; border.width: 2
                }
            }
            Label { text: "Palette"; color: themeState.secondary; font.pixelSize: 13 }
            GridView {
                id: presetColors
                Layout.fillWidth: true; Layout.preferredHeight: 160
                clip: true; cellWidth: width / 8; cellHeight: 40
                model: ["#EF4444", "#F97316", "#F59E0B", "#EAB308", "#84CC16", "#22C55E", "#10B981", "#14B8A6", "#06B6D4", "#0EA5E9", "#3B82F6", "#6366F1", "#8B5CF6", "#A855F7", "#D946EF", "#EC4899", "#F43F5E", "#FB7185", "#FDBA74", "#FDE047", "#BEF264", "#86EFAC", "#5EEAD4", "#67E8F9", "#7DD3FC", "#93C5FD", "#A5B4FC", "#C4B5FD", "#D8B4FE", "#F0ABFC", "#F9A8D4", "#FDA4AF"]
                delegate: Button {
                    required property string modelData
                    width: 32; height: 32; padding: 2
                    Accessible.name: modelData
                    background: Rectangle { anchors.centerIn: parent; width: 27; height: 27; radius: 14; color: modelData; border.color: palettePicker.draftHex.toUpperCase() === modelData ? themeState.foreground : themeState.border; border.width: palettePicker.draftHex.toUpperCase() === modelData ? 2 : 1 }
                    onClicked: palettePicker.setDraft(modelData)
                }
            }
            Label { Layout.fillWidth: true; text: palettePicker.statusMessage; visible: text.length > 0; color: themeState.secondary; font.pixelSize: 12; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    text: "Cancel"; height: 36; leftPadding: 18; rightPadding: 18
                    contentItem: Text { text: parent.text; color: themeState.foreground; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { radius: 18; color: parent.hovered ? themeState.surface : "transparent"; border.color: themeState.border; border.width: 1 }
                    onClicked: palettePicker.close()
                }
                Button {
                    text: "Apply"; height: 36; leftPadding: 18; rightPadding: 18
                    enabled: /^#[0-9A-Fa-f]{6}$/.test(palettePicker.draftHex)
                    contentItem: Text { text: parent.text; color: themeState.onAccent; font.pixelSize: 13; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { radius: 18; color: parent.enabled ? parent.hovered ? themeState.accentHover : themeState.accent : themeState.muted }
                    onClicked: palettePicker.applyColor()
                }
            }
        }
    }
    Window {
        id: screenPickerOverlay
        objectName: "screenPickerOverlay"
        visible: false
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        color: "#01000000"
        modality: Qt.ApplicationModal
        x: colorSampler.virtualGeometry.x
        y: colorSampler.virtualGeometry.y
        width: colorSampler.virtualGeometry.width
        height: colorSampler.virtualGeometry.height
        Item {
            anchors.fill: parent
            focus: true
            Keys.onEscapePressed: { screenPickerOverlay.hide(); settingsDialog.open(); palettePicker.open() }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.CrossCursor
                onClicked: function(mouse) {
                    colorSampler.sampleAt(Math.round(screenPickerOverlay.x + mouse.x), Math.round(screenPickerOverlay.y + mouse.y))
                    screenPickerOverlay.hide()
                }
            }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top; anchors.topMargin: 28
                width: samplingHint.implicitWidth + 36; height: 44; radius: 22
                color: themeState.surface; border.color: themeState.border; border.width: 1
                Text { id: samplingHint; anchors.centerIn: parent; text: "Click anywhere to sample a color · Esc to cancel"; color: themeState.foreground; font.pixelSize: 14 }
            }
        }
    }
    Connections {
        target: colorSampler
        function onColorPicked(color) {
            palettePicker.setDraft(color)
            settingsDialog.open()
            palettePicker.open()
        }
        function onPickFailed(message) {
            palettePicker.statusMessage = message
            settingsDialog.open()
            palettePicker.open()
        }
    }
    FileDialog {
        id: sessionPicker
        title: "Choose a YouTube Music Session Export"
        nameFilters: ["JSON session files (*.json)", "All files (*)"]
        onAccepted: accountState.importFile(selectedFile)
    }
    Connections { target: appState; function onAccountDialogRequested() { accountDialog.open() } }
    Connections { target: appState; function onPageChanged() { if (appState.page === "Search") search.text = appState.query } }
    MediaMenu { id: mediaMenu }
    PlaylistDialogs { id: playlistDialogs; anchors.fill: parent }
    Connections { target: appState; function onMenuRequested(media, context) { mediaMenu.media = media; mediaMenu.context = context; mediaMenu.popup() } }
    Dialog {
        id: shortcutHelp
        width: Math.min(580, window.width - 80)
        anchors.centerIn: parent; modal: true; title: "Keyboard Shortcuts"; standardButtons: Dialog.Close
        palette.window: themeState.surface; palette.windowText: themeState.foreground
        contentItem: Label {
            color: themeState.foreground; lineHeight: 1.7
            text: "Space — Play / pause\nShift+N / Shift+P — Next / previous\nLeft / Right — Seek 5 seconds\nShift+Left / Shift+Right — Seek 10 seconds\n+ / − — Volume\nM — Mute\nS / R — Shuffle / repeat\nF / Escape — Open / close immersive player\n/ or Ctrl+F — Search\nAlt+Left — Back\nAlt+Up / Alt+Down — Move focused queue entry\nDelete — Remove focused queue entry"
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
