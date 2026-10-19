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
    onClosing: appState.saveWindow(width, height)

    Rectangle {
        anchors.left: sidebar.right
        anchors.right: parent.right
        height: 370
        gradient: Gradient {
            GradientStop { position: 0; color: "#071b22" }
            GradientStop { position: 1; color: Theme.background }
        }
    }

    Rectangle {
        id: sidebar
        width: appState.sidebarExpanded ? 240 : 72
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
            visible: appState.sidebarExpanded
            Image { width: 34; height: 40; source: "../assets/music.svg"; fillMode: Image.PreserveAspectFit }
            Text { text: "Music"; color: Theme.foreground; font.family: Theme.headingFont; font.bold: true; font.pixelSize: 24; height: 40; verticalAlignment: Text.AlignVCenter }
        }
        Column {
            id: navigation
            x: 8; y: 72; width: sidebar.width - 16
            Repeater {
                model: [{label:"Home",icon:"home"}, {label:"Explore",icon:"explore"}, {label:"Library",icon:"library"}, {label:"Downloads",icon:"download"}]
                delegate: Button {
                    id: nav
                    required property var modelData
                    width: navigation.width
                    height: 48
                    padding: 0
                    text: modelData.label
                    Accessible.name: text
                    onClicked: appState.navigate(text)
                    background: Rectangle {
                        radius: 8
                        color: appState.page === nav.text ? "#212121" : nav.hovered ? "#141414" : "transparent"
                        border.width: nav.visualFocus ? 2 : 0
                        border.color: "white"
                    }
                    contentItem: Row {
                        leftPadding: 16; spacing: 20
                        Symbol { anchors.verticalCenter: parent.verticalCenter; name: nav.modelData.icon }
                        Text { anchors.verticalCenter: parent.verticalCenter; visible: appState.sidebarExpanded; text: nav.text; color: Theme.foreground; font.family: Theme.bodyFont; font.pixelSize: 16 }
                    }
                    ToolTip.text: text
                    ToolTip.visible: !appState.sidebarExpanded && hovered
                }
            }
        }
        Rectangle { x: 24; y: navigation.y + navigation.height + 24; width: sidebar.width - 48; height: 1; color: Theme.border }
        Button {
            id: newPlaylist
            x: 20; y: navigation.y + navigation.height + 48
            width: sidebar.width - 40; height: 36
            visible: appState.sidebarExpanded
            text: "+  New playlist"
            font.pixelSize: 14
            palette.buttonText: Theme.foreground
            background: Rectangle { radius: 20; color: newPlaylist.hovered ? "#303030" : "#212121"; border.width: newPlaylist.visualFocus ? 2 : 0; border.color: "white" }
            onClicked: appState.requestAction("newPlaylist")
        }
        ListView {
            anchors.top: newPlaylist.bottom
            anchors.topMargin: 24
            anchors.bottom: parent.bottom
            width: parent.width
            clip: true
            visible: appState.sidebarExpanded
            model: appState.playlists
            delegate: ItemDelegate {
                required property var modelData
                width: ListView.view.width
                height: 56
                leftPadding: 24
                contentItem: Column {
                    spacing: 5
                    Text { text: modelData.title; color: Theme.foreground; font.family: Theme.bodyFont; font.pixelSize: 14; width: sidebar.width - 48; elide: Text.ElideRight }
                    Text { text: modelData.owner || ""; color: Theme.secondary; font.family: Theme.bodyFont; font.pixelSize: 12 }
                }
                background: Rectangle { color: parent.hovered ? "#151515" : "transparent" }
                onClicked: appState.requestAction("playlist:" + modelData.id)
            }
        }
    }

    Item {
        id: header
        anchors.left: sidebar.right
        anchors.right: parent.right
        height: 64
        TextField {
            id: search
            objectName: "searchField"
            x: Math.min(100, Math.max(32, (header.width - 720) / 2))
            y: 11
            width: Math.min(480, header.width - 160)
            height: 42
            leftPadding: 52
            rightPadding: 16
            color: Theme.foreground
            placeholderText: "Search songs, albums, artists"
            placeholderTextColor: "#999fa1"
            font.pixelSize: 16
            selectByMouse: true
            Accessible.name: "Search YouTube Music"
            background: Rectangle { radius: 8; color: search.activeFocus ? "#303539" : "#2c3337"; border.color: search.activeFocus ? "#aaaaaa" : "#495155"; border.width: 1 }
            Symbol { x: 16; anchors.verticalCenter: parent.verticalCenter; name: "search"; width: 20; height: 20; color: "#a2abad" }
            onAccepted: appState.search(text)
        }
        IconButton {
            anchors.right: parent.right
            anchors.rightMargin: header.width > 900 ? 96 : 24
            y: 10
            width: 44; height: 44
            iconName: "profile"
            tip: accountState.profile.name || "Account"
            onClicked: appState.openAccount()
            Image {
                anchors.centerIn: parent
                width: 28; height: 28
                source: accountState.profile.avatar || ""
                asynchronous: true
                visible: status === Image.Ready
                fillMode: Image.PreserveAspectCrop
            }
        }
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
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.top: reconnectBanner.bottom
        anchors.bottom: player.top
        property real gutter: width > 900 ? 106 : 40

        ListView {
            id: home
            anchors.fill: parent
            anchors.leftMargin: content.gutter
            anchors.rightMargin: Math.min(content.gutter, 72)
            topMargin: 46
            clip: true
            spacing: 80
            visible: appState.page === "Home" && appState.shelves.length > 0
            model: appState.shelves
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            header: Item {
                width: home.width
                height: 82
                ListView {
                    width: parent.width
                    height: 36
                    orientation: ListView.Horizontal
                    spacing: 12
                    clip: true
                    model: ["Energize", "Feel good", "Workout", "Relax", "Party", "Commute", "Romance", "Focus", "Sad"]
                    delegate: Button {
                        id: mood
                        required property string modelData
                        text: modelData
                        height: 36
                        leftPadding: 13; rightPadding: 13
                        palette.buttonText: Theme.foreground
                        background: Rectangle { radius: 8; color: mood.hovered ? "#394146" : "#252d31"; border.width: mood.visualFocus ? 2 : 0; border.color: "white" }
                        onClicked: appState.requestAction("mood:" + text)
                    }
                }
            }
            delegate: Item {
                id: shelf
                required property var modelData
                width: home.width
                height: heading.height + 16 + 218
                Row {
                    id: heading
                    spacing: 16
                    height: shelf.modelData.subtitle ? 56 : 40
                    Rectangle {
                        width: 56; height: 56; radius: 28
                        visible: !!shelf.modelData.subtitle
                        color: "#29373a"
                        Symbol { anchors.centerIn: parent; name: "profile"; width: 30; height: 30 }
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 4
                        Text { visible: !!shelf.modelData.subtitle; text: shelf.modelData.subtitle || ""; color: Theme.secondary; font.pixelSize: 14; font.family: Theme.bodyFont }
                        Text { text: shelf.modelData.title; color: Theme.foreground; font.family: Theme.headingFont; font.bold: true; font.pixelSize: 28 }
                    }
                }
                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: heading.verticalCenter
                    spacing: 12
                    IconButton { iconName: "left"; tip: "Previous items"; outlined: true; width: 36; height: 36; onClicked: cards.contentX = Math.max(0, cards.contentX - cards.width) }
                    IconButton { iconName: "right"; tip: "More items"; outlined: true; width: 36; height: 36; onClicked: cards.contentX = Math.min(Math.max(0, cards.contentWidth - cards.width), cards.contentX + cards.width) }
                }
                ListView {
                    id: cards
                    anchors.top: heading.bottom
                    anchors.topMargin: 16
                    width: parent.width
                    height: 218
                    clip: true
                    orientation: ListView.Horizontal
                    spacing: 24
                    model: shelf.modelData.items
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: MediaCard {
                        required property var modelData
                        media: modelData
                        width: 146
                        onPlayRequested: item => appState.requestAction("play:" + item.id)
                    }
                }
            }
        }

        Column {
            anchors.centerIn: parent
            width: Math.min(parent.width - 80, 480)
            spacing: 16
            visible: !home.visible
            Symbol { anchors.horizontalCenter: parent.horizontalCenter; width: 52; height: 52; name: appState.page === "Downloads" ? "download" : "music"; color: Theme.secondary }
            Text {
                width: parent.width
                text: appState.page === "Home" ? "Your music, all together" : appState.page
                color: Theme.foreground
                font.family: Theme.headingFont
                font.bold: true
                font.pixelSize: 30
                horizontalAlignment: Text.AlignHCenter
            }
            Text {
                width: parent.width
                text: appState.page === "Downloads" ? "Your downloaded songs, albums and playlists will appear here." : accountState.connected ? "Your account is connected." : "Connect YouTube Music to browse your library and recommendations."
                color: Theme.secondary
                font.pixelSize: 15
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
            }
            Button {
                id: connect
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Connect YouTube Music"
                visible: !accountState.connected
                topPadding: 12; bottomPadding: 12; leftPadding: 24; rightPadding: 24
                palette.buttonText: "black"
                background: Rectangle { radius: 22; color: connect.hovered ? "#dddddd" : "white"; border.width: connect.visualFocus ? 2 : 0; border.color: Theme.accent }
                onClicked: appState.openAccount()
            }
        }
    }

    Rectangle {
        id: player
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 72
        color: Theme.surface
        Rectangle { width: parent.width; height: 1; color: "#444444" }
        Rectangle { width: parent.width * playerState.progress; height: 2; color: Theme.accent }
        ProgressBar { width: parent.width; height: 3; visible: playerState.busy; indeterminate: visible }
        MouseArea { anchors.left: parent.left; anchors.right: parent.right; y: -4; height: 12; enabled: playerState.hasTrack; cursorShape: Qt.PointingHandCursor; onPressed: function(mouse) { playerState.seekFraction(mouse.x / width) } }
        Row {
            x: 4; anchors.verticalCenter: parent.verticalCenter
            IconButton { iconName: "previous"; tip: "Previous"; enabled: playerState.hasTrack; onClicked: appState.requestAction("previous") }
            IconButton { iconName: playerState.playing ? "pause" : "play"; iconSize: 32; width: 56; tip: playerState.playing ? "Pause" : "Play"; enabled: playerState.hasTrack; onClicked: playerState.togglePlayback() }
            IconButton { iconName: "next"; tip: "Next"; enabled: playerState.hasTrack; onClicked: appState.requestAction("next") }
        }
        Text { x: 168; anchors.verticalCenter: parent.verticalCenter; text: playerState.progressText; color: Theme.secondary; font.pixelSize: 11 }
        Cover { id: trackCover; x: 280; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; radius: 2; source: playerState.currentTrack.thumbnail || ""; accent: playerState.currentTrack.accent || "#333333" }
        Column {
            id: trackInfo
            x: 336; anchors.verticalCenter: parent.verticalCenter
            width: Math.max(160, window.width - 800)
            spacing: 1
            Text { width: parent.width; text: playerState.currentTrack.title || "Nothing playing"; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.foreground; font.family: Theme.bodyFont; font.pixelSize: 14 }
            Text { width: parent.width; text: playerState.currentTrack.artist || "Choose a song to get started"; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.secondary; font.family: Theme.bodyFont; font.pixelSize: 14 }
        }
        Row {
            anchors.left: trackInfo.right
            anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            IconButton { iconName: "like"; tip: "Like"; enabled: playerState.hasTrack; onClicked: appState.requestAction("like") }
            IconButton { iconName: "dislike"; tip: "Dislike"; enabled: playerState.hasTrack; onClicked: appState.requestAction("dislike") }
            IconButton { iconName: "more"; tip: "More options"; enabled: playerState.hasTrack; onClicked: appState.requestAction("trackMenu") }
        }
        Row {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            IconButton { iconName: appState.volume > 0 ? "volume" : "muted"; iconColor: Theme.secondary; tip: appState.volume > 0 ? "Mute" : "Unmute"; onClicked: appState.toggleMute() }
            Slider { width: 84; height: 40; visible: window.width >= 1200; from: 0; to: 100; value: appState.volume; Accessible.name: "Volume"; onMoved: appState.setVolume(Math.round(value)) }
            IconButton { iconName: "repeat"; iconColor: playerState.repeat !== "off" ? "white" : Theme.secondary; tip: "Repeat: " + playerState.repeat; enabled: playerState.hasTrack; onClicked: appState.requestAction("repeat"); Text { visible: playerState.repeat === "one"; anchors.centerIn: parent; text: "1"; font.pixelSize: 9; color: "white" } }
            IconButton { iconName: "shuffle"; iconColor: playerState.shuffled ? "white" : Theme.secondary; tip: "Shuffle"; enabled: playerState.hasTrack; onClicked: appState.requestAction("shuffle") }
            IconButton { iconName: "up"; tip: "Expand player"; enabled: playerState.hasTrack; onClicked: appState.requestAction("expandPlayer") }
        }
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: player.top; anchors.bottomMargin: 16
        width: Math.min(600, window.width - 80); height: playbackMessage.implicitHeight + 24
        radius: 6; color: "#383838"; visible: playerState.message.length > 0
        Text { id: playbackMessage; anchors.fill: parent; anchors.margins: 12; text: playerState.message; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: "white"; font.pixelSize: 14 }
    }

    Dialog {
        id: accountDialog
        anchors.centerIn: parent
        width: Math.min(window.width - 80, 480)
        modal: true
        title: "Connect YouTube Music"
        standardButtons: Dialog.Close
        palette.window: "#212121"
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
    Shortcut { sequence: "/"; enabled: !search.activeFocus; onActivated: search.forceActiveFocus() }
    Shortcut { sequence: "Ctrl+F"; onActivated: search.forceActiveFocus() }
    Shortcut { sequence: "Space"; enabled: !search.activeFocus && !accountDialog.opened; onActivated: playerState.togglePlayback() }
}
