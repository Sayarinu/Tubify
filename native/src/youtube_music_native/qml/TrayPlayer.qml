import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "Theme.js" as Theme

ApplicationWindow {
    id: root
    objectName: "trayPlayer"
    title: "YouTube Music · Tray player"
    width: 360
    height: Math.min(screen.desktopAvailableHeight, trayState.queueOpen ? 700 : 292)
    visible: false
    color: themeState.background
    flags: Qt.Tool | Qt.FramelessWindowHint | (trayState.pinned ? Qt.WindowStaysOnTopHint : 0)
    onClosing: function(event) { event.accepted = false; hide() }
    onActiveChanged: if (!active && !trayState.pinned && !moving.active && !mediaMenu.opened && visible) hide()
    onHeightChanged: if (visible) trayState.positionPopup()
    onXChanged: positionSave.restart()
    onYChanged: positionSave.restart()
    Component.onCompleted: trayState.attachPopup(root)
    Component.onDestruction: trayState.detachPopup()
    MediaMenu { id: mediaMenu }
    Connections { target: appState; function onMenuRequested(media, context) { if (root.active) { mediaMenu.media = media; mediaMenu.context = context; mediaMenu.popup() } } }
    Timer { id: positionSave; interval: 300; onTriggered: trayState.savePosition() }
    Rectangle { anchors.fill: parent; color: "transparent"; border.color: themeState.border; border.width: 1; radius: 12 }
    Item {
        id: titleBar
        width: parent.width; height: 44
        Text { x: 16; anchors.verticalCenter: parent.verticalCenter; text: "YouTube Music"; color: themeState.foreground; font.bold: true; font.pixelSize: 14 }
        DragHandler { id: moving; target: null; onActiveChanged: if (active) root.startSystemMove() }
        IconButton { x: parent.width - 88; width: 40; height: 40; iconName: "pin"; tip: trayState.pinned ? "Unpin player" : "Keep player on top"; iconColor: trayState.pinned ? themeState.accent : themeState.secondary; onClicked: trayState.setPinned(!trayState.pinned) }
        IconButton { x: parent.width - 44; width: 40; height: 40; iconName: "close"; tip: "Close tray player"; onClicked: root.hide() }
    }
    Cover { id: artwork; x: 16; y: 52; width: 76; height: 76; media: playerState.currentTrack; mediaKey: playerState.currentTrack.videoId || playerState.currentTrack.id || ""; source: playerState.currentTrack.thumbnail || "" }
    Column {
        x: 108; y: 56; width: parent.width - x - 16; spacing: 6
        Text { width: parent.width; text: playerState.currentTrack.title || "Nothing playing"; textFormat: Text.PlainText; color: themeState.foreground; font.bold: true; font.pixelSize: 16; elide: Text.ElideRight }
        Text { width: parent.width; text: playerState.currentTrack.artist || (playerState.currentTrack.artists || []).map(item => item.name).join(" · "); textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 13; elide: Text.ElideRight }
        Row {
            IconButton { objectName: "trayLike"; width: 32; height: 32; iconName: "like"; tip: "Like"; enabled: playerState.hasTrack && !actionsState.busy && (accountState.connected || appState.fixtureMode); iconColor: playerState.currentTrack.rating === "LIKE" ? themeState.accent : themeState.secondary; onClicked: libraryState.rate(playerState.currentTrack, "LIKE") }
            IconButton { width: 32; height: 32; iconName: "dislike"; tip: "Dislike"; enabled: playerState.hasTrack && !actionsState.busy && (accountState.connected || appState.fixtureMode); iconColor: playerState.currentTrack.rating === "DISLIKE" ? themeState.accent : themeState.secondary; onClicked: libraryState.rate(playerState.currentTrack, "DISLIKE") }
            IconButton { width: 32; height: 32; iconName: "more"; tip: "Open full app"; onClicked: trayState.showMain() }
        }
    }
    Row {
        anchors.horizontalCenter: parent.horizontalCenter; y: 136; spacing: 8
        IconButton { iconName: "shuffle"; tip: "Shuffle"; iconColor: playerState.shuffled ? themeState.accent : themeState.secondary; onClicked: playerState.setShuffle(!playerState.shuffled) }
        IconButton { objectName: "trayPrevious"; iconName: "previous"; tip: "Previous"; enabled: playerState.hasTrack; onClicked: playerState.previous() }
        IconButton { objectName: "trayPlayPause"; iconName: playerState.playing ? "pause" : "play"; tip: playerState.playing ? "Pause" : "Play"; enabled: playerState.hasTrack; onClicked: playerState.togglePlayback() }
        IconButton { objectName: "trayNext"; iconName: "next"; tip: "Next"; enabled: playerState.hasTrack; onClicked: playerState.next() }
        IconButton { iconName: playerState.repeat === "one" ? "repeatOne" : "repeat"; tip: "Repeat: " + playerState.repeat; iconColor: playerState.repeat !== "off" ? themeState.accent : themeState.secondary; onClicked: playerState.handleAction("repeat") }
    }
    AccentSlider { id: seek; objectName: "traySeek"; x: 16; y: 184; width: parent.width - 32; height: 24; from: 0; to: 1; value: playerState.progress; enabled: playerState.hasTrack; Accessible.name: "Playback position"; onMoved: playerState.seekFraction(value) }
    Text { x: 20; y: 212; text: playerState.progressText; color: themeState.secondary; font.pixelSize: 11 }
    Row {
        x: 16; y: 236; spacing: 8
        IconButton { width: 36; height: 36; iconName: appState.volume ? "volume" : "muted"; tip: appState.volume ? "Mute" : "Unmute"; onClicked: appState.toggleMute() }
        AccentSlider { objectName: "trayVolume"; width: 204; height: 36; from: 0; to: 100; value: appState.volume; Accessible.name: "Volume"; onMoved: appState.setVolume(Math.round(value)) }
        IconButton { objectName: "trayQueueToggle"; width: 44; height: 36; iconName: "queue"; tip: trayState.queueOpen ? "Close queue" : "Open queue"; iconColor: trayState.queueOpen ? themeState.accent : themeState.secondary; onClicked: trayState.setQueueOpen(!trayState.queueOpen) }
    }
    Loader {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.topMargin: 284; anchors.bottom: parent.bottom
        active: trayState.queueOpen
        sourceComponent: QueuePane { showCloseButton: false }
    }
}
