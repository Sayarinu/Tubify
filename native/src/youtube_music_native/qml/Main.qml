import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "Theme.js" as Theme

ApplicationWindow {
    id: window
    visible: true
    width: appState.initialWidth
    height: appState.initialHeight
    minimumWidth: 920
    minimumHeight: 620
    title: appState.fixtureMode ? "YouTube Music · Visual fixture" : "YouTube Music"
    color: Theme.background
    font.family: Theme.bodyFont
    font.pixelSize: 14
    palette.window: Theme.surface
    palette.base: Theme.background
    palette.alternateBase: Theme.surface
    palette.button: Theme.surface
    palette.text: Theme.foreground
    palette.windowText: Theme.foreground
    palette.buttonText: Theme.foreground
    palette.accent: Theme.accent
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.onAccent
    palette.midlight: Theme.hover
    palette.mid: Theme.border
    palette.light: Theme.border
    palette.dark: Theme.background
    palette.link: Theme.accent
    property bool wideNavigation: appState.sidebarExpanded && width >= 1100
    onClosing: appState.saveWindow(width, height)
    property bool editingText: activeFocusItem instanceof TextInput || activeFocusItem instanceof TextEdit
    property bool modalOpen: accountDialog.opened || playlistDialogs.opened || shortcutHelp.opened || !!(pages.item && pages.item.objectName === "downloadsPane" && pages.item.blockingShortcuts)
    property bool playbackShortcuts: !editingText && !modalOpen && !mediaMenu.opened

    Rectangle {
        anchors.left: sidebar.right
        anchors.right: parent.right
        height: 370
        gradient: Gradient {
            GradientStop { position: 0; color: !appState.expanded && appState.page === "Home" && catalogState.route === "home" ? "#251e36" : Theme.background }
            GradientStop { position: 1; color: Theme.background }
        }
    }

    Rectangle {
        id: sidebar
        objectName: "navigationRail"
        width: window.wideNavigation ? 240 : 72
        anchors.top: parent.top
        anchors.bottom: player.top
        color: Theme.background
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.border }
        IconButton {
            x: 12; y: 10
            iconName: "menu"
            tip: "Toggle navigation"
            onClicked: appState.toggleSidebar()
        }
        Row {
            x: 60; y: 12; spacing: 0
            visible: window.wideNavigation
            Image { width: 34; height: 40; source: "../assets/music.svg"; fillMode: Image.PreserveAspectFit }
            Text { text: "Music"; color: Theme.foreground; font.family: Theme.headingFont; font.bold: true; font.pixelSize: 24; height: 40; verticalAlignment: Text.AlignVCenter }
        }
        Column {
            id: navigation
            x: 8; y: 72; width: sidebar.width - 16
            Repeater {
                model: [{label:"Home",icon:"home"}, {label:"Search",icon:"search"}, {label:"Explore",icon:"explore"}, {label:"Library",icon:"library"}, {label:"Downloads",icon:"download"}]
                delegate: Button {
                    id: nav
                    required property var modelData
                    width: navigation.width
                    height: 48
                    padding: 0
                    text: modelData.label
                    Accessible.name: text
                    onClicked: { if (text === "Search") search.forceActiveFocus(); else appState.navigate(text) }
                    background: Rectangle {
                        radius: 8
                        color: appState.page === nav.text ? Theme.selected : nav.hovered ? Theme.hover : "transparent"
                        border.width: nav.visualFocus ? 2 : 0
                        border.color: Theme.accent
                        Rectangle { x: 0; y: 12; width: 3; height: 24; radius: 2; color: Theme.accent; visible: appState.page === nav.text }
                    }
                    contentItem: Row {
                        leftPadding: 16; spacing: 20
                        Symbol { anchors.verticalCenter: parent.verticalCenter; name: nav.modelData.icon; color: appState.page === nav.text ? Theme.accent : Theme.secondary }
                        Text { anchors.verticalCenter: parent.verticalCenter; visible: window.wideNavigation; text: nav.text; color: Theme.foreground; font.family: Theme.bodyFont; font.pixelSize: 16 }
                    }
                    ToolTip.text: text
                    ToolTip.visible: !window.wideNavigation && hovered
                }
            }
        }
        Rectangle { x: 16; y: navigation.y + navigation.height + 12; width: sidebar.width - 48; height: 1; color: Theme.border }
        Button {
            id: newPlaylist
            x: 12; y: navigation.y + navigation.height + 24
            width: sidebar.width - 24; height: 40
            text: window.wideNavigation ? "+  New playlist" : "+"
            Accessible.name: "New playlist"
            ToolTip.text: "New playlist"
            ToolTip.visible: hovered
            font.pixelSize: 14
            palette.buttonText: Theme.foreground
            background: Rectangle { radius: 20; color: newPlaylist.hovered ? Theme.hover : Theme.surface; border.width: newPlaylist.visualFocus ? 2 : 0; border.color: "white" }
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
                    Cover { x: 16; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; radius: 8; source: modelData.thumbnail || ""; mediaKey: "playlist:" + modelData.id; accent: Theme.selected }
                    Column {
                        x: 68; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 80; spacing: 4
                        visible: window.wideNavigation
                        Text { width: parent.width; text: modelData.title; textFormat: Text.PlainText; color: Theme.foreground; font.pixelSize: 14; elide: Text.ElideRight }
                        Text { width: parent.width; text: modelData.owner || ""; textFormat: Text.PlainText; color: Theme.secondary; font.pixelSize: 12; elide: Text.ElideRight }
                    }
                }
                background: Rectangle { radius: 8; color: parent.hovered ? Theme.hover : "transparent"; border.color: parent.visualFocus ? Theme.accent : "transparent" }
                onClicked: appState.requestAction("playlist:" + modelData.id)
            }
        }
    }

    Item {
        id: header
        anchors.left: sidebar.right
        anchors.right: parent.right
        height: 64
        IconButton { x: 12; y: 10; iconName: "left"; tip: "Back"; onClicked: { appState.setExpanded(false); browseState.back() } }
        TextField {
            id: search
            objectName: "searchField"
            x: 68
            y: 11
            width: Math.min(480, header.width - 200)
            height: 42
            leftPadding: 52
            rightPadding: text.length > 0 ? 48 : 16
            color: Theme.foreground
            placeholderText: "Search songs, albums, artists"
            placeholderTextColor: "#999fa1"
            font.pixelSize: 16
            selectByMouse: true
            Accessible.name: "Search YouTube Music"
            background: Rectangle { radius: 12; color: search.activeFocus ? Theme.hover : Theme.surface; border.color: search.activeFocus ? Theme.accent : Theme.border; border.width: 1 }
            Symbol { x: 16; anchors.verticalCenter: parent.verticalCenter; name: "search"; width: 20; height: 20; color: "#a2abad" }
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
                background: Rectangle { color: Theme.hover; radius: 8 }
                contentItem: ListView {
                    id: suggestions
                    clip: true; currentIndex: -1; model: searchState.suggestions
                    delegate: ItemDelegate {
                        required property string modelData
                        required property int index
                        width: suggestions.width; height: 44
                        highlighted: index === suggestions.currentIndex
                        background: Rectangle { color: parent.highlighted ? Theme.selected : parent.hovered ? Theme.hover : "transparent"; radius: 4 }
                        contentItem: Text { text: modelData; textFormat: Text.PlainText; color: "white"; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; font.pixelSize: 15 }
                        onClicked: { search.text = modelData; appState.search(modelData) }
                    }
                }
            }
        }
        IconButton {
            id: profileButton
            anchors.right: parent.right
            anchors.rightMargin: 16
            y: 10
            width: 44; height: 44
            iconName: "profile"
            tip: accountState.profile.name || "Account"
            onClicked: appState.openAccount()
            contentItem: Item {
                Avatar {
                    anchors.centerIn: parent
                    width: 28; height: 28
                    source: accountState.profile.avatar || ""
                }
            }
        }
        IconButton { anchors.right: profileButton.left; anchors.rightMargin: 12; y: 10; width: 44; height: 44; iconName: "history"; tip: "Listening history"; onClicked: libraryState.history() }
    }

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
            color: "white"; font.pixelSize: 14; elide: Text.ElideRight
        }
        Button { id: reconnectButton; anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; text: "Reconnect"; onClicked: appState.openAccount() }
    }

    Item {
        id: content
        objectName: "pageContent"
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.top: reconnectBanner.bottom
        anchors.bottom: player.top
        anchors.bottomMargin: 12
        property real gutter: Theme.gutter(width)

        Loader {
            id: pages
            anchors.fill: parent
            active: !appState.expanded
            sourceComponent: catalogState.route === "downloads" ? downloadsPage : catalogState.route === "album" || catalogState.route === "playlist" ? collectionPage : catalogState.route === "artist" ? artistPage : catalogState.route === "search" ? searchPage : catalogState.route.indexOf("library_") === 0 || catalogState.route === "history" || appState.page === "Library" && catalogState.route === "home" ? libraryPage : browsePage
            Component { id: downloadsPage; DownloadsPane {} }
            Component { id: collectionPage; CollectionPane {} }
            Component { id: artistPage; ArtistPane {} }
            Component { id: searchPage; SearchPane {} }
            Component { id: libraryPage; LibraryPane {} }
            Component { id: browsePage; BrowsePane {} }
        }

        Loader { anchors.fill: parent; active: appState.expanded; sourceComponent: Component { ExpandedPane {} } }

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
        radius: 6; color: Theme.hover; visible: playbackMessage.text.length > 0
        Text { id: playbackMessage; anchors.fill: parent; anchors.margins: 12; text: browseState.queueMessage || actionsState.message || libraryState.message || playerState.message || downloadsState.message; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: "white"; font.pixelSize: 14 }
    }

    Dialog {
        id: accountDialog
        anchors.centerIn: parent
        width: Math.min(window.width - 80, 480)
        modal: true
        title: "Connect YouTube Music"
        standardButtons: Dialog.Close
        palette.window: Theme.surface
        palette.windowText: "white"
        palette.text: "white"
        contentItem: ColumnLayout {
            spacing: 16
            Label { Layout.fillWidth: true; text: accountState.profile.name || "Connect your account"; textFormat: Text.PlainText; font.pixelSize: 20; font.bold: true; color: "white"; wrapMode: Text.Wrap }
            Label { Layout.fillWidth: true; text: "Use the signed-in desktop app or choose a browser session export. Your session stays in this device’s secure storage."; wrapMode: Text.Wrap; color: Theme.secondary }
            Button { Layout.fillWidth: true; text: "Use existing desktop app session"; visible: accountState.tauriAvailable && !accountState.fixtureMode; enabled: !accountState.busy; onClicked: accountState.importTauri() }
            Button { Layout.fillWidth: true; text: "Choose browser session file"; enabled: !accountState.busy && !accountState.fixtureMode; onClicked: sessionPicker.open() }
            Button { Layout.fillWidth: true; text: "Export instructions"; flat: true; onClicked: Qt.openUrlExternally("https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html") }
            BusyIndicator { Layout.alignment: Qt.AlignHCenter; running: accountState.busy; visible: running }
            Label { Layout.fillWidth: true; text: accountState.message; textFormat: Text.PlainText; visible: text.length > 0; wrapMode: Text.Wrap; color: Theme.secondary }
            Button { Layout.fillWidth: true; text: "Sign out"; visible: accountState.connected; enabled: !accountState.busy; onClicked: accountState.signOut() }
        }
    }
    FileDialog {
        id: sessionPicker
        title: "Choose a YouTube Music session export"
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
        anchors.centerIn: parent; modal: true; title: "Keyboard shortcuts"; standardButtons: Dialog.Close
        palette.window: Theme.surface; palette.windowText: "white"
        contentItem: Label {
            color: "white"; lineHeight: 1.7
            text: "Space — Play / pause\nShift+N / Shift+P — Next / previous\nLeft / Right — Seek 5 seconds\nShift+Left / Shift+Right — Seek 10 seconds\n+ / − — Volume\nM — Mute\nS / R — Shuffle / repeat\nF / Escape — Open / close player\n/ or Ctrl+F — Search\nAlt+Left — Back\nAlt+Up / Alt+Down — Move focused queue entry\nDelete — Remove focused queue entry"
        }
    }
    Shortcut { sequence: "Alt+Left"; enabled: window.playbackShortcuts; onActivated: { appState.setExpanded(false); browseState.back() } }
    Shortcut { sequence: "/"; enabled: window.playbackShortcuts; onActivated: search.forceActiveFocus() }
    Shortcut { sequence: "Ctrl+F"; enabled: !window.modalOpen; onActivated: search.forceActiveFocus() }
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
