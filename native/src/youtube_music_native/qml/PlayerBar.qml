import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Rectangle {
    id: root
    objectName: "playerBar"
    height: 92
    radius: 12
    color: Theme.surface
    border.color: Theme.border
    property bool compact: width < 1100

    Item {
        id: track
        x: 16; width: Math.min(320, root.width * 0.28); height: parent.height
        Cover { id: cover; anchors.verticalCenter: parent.verticalCenter; width: 52; height: 52; radius: 8; source: playerState.currentTrack.thumbnail || ""; mediaKey: playerState.currentTrack.videoId || playerState.currentTrack.id || ""; accent: Theme.selected }
        Column {
            x: 64; width: parent.width - x - like.width; anchors.verticalCenter: parent.verticalCenter; spacing: 5
            Text { width: parent.width; text: playerState.currentTrack.title || "Nothing playing"; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.foreground; font.bold: true; font.pixelSize: 14 }
            Text { width: parent.width; text: playerState.currentTrack.artist || "Choose a song"; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.secondary; font.pixelSize: 12 }
        }
        IconButton { id: like; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; iconName: "like"; tip: playerState.currentTrack.rating === "LIKE" ? "Remove like" : "Like"; iconColor: playerState.currentTrack.rating === "LIKE" ? Theme.accent : Theme.secondary; enabled: playerState.hasTrack && !actionsState.busy && (accountState.connected || appState.fixtureMode); onClicked: appState.requestAction("like") }
    }
    Item {
        anchors.left: track.right; anchors.leftMargin: 8
        anchors.right: tools.left; anchors.rightMargin: 12
        height: parent.height
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; y: 6; spacing: 4
            IconButton { iconName: "shuffle"; iconColor: playerState.shuffled ? Theme.accent : Theme.secondary; tip: "Shuffle"; enabled: playerState.hasTrack; onClicked: appState.requestAction("shuffle") }
            IconButton { iconName: "previous"; tip: "Previous"; enabled: playerState.hasTrack; onClicked: playerState.previous() }
            IconButton { iconName: playerState.playing ? "pause" : "play"; iconSize: 28; iconColor: Theme.onAccent; tip: playerState.playing ? "Pause" : "Play"; enabled: playerState.hasTrack; onClicked: playerState.togglePlayback(); background: Rectangle { radius: 22; color: parent.hovered ? Theme.accentHover : Theme.accent; border.width: parent.visualFocus ? 2 : 0; border.color: Theme.foreground } }
            IconButton { iconName: "next"; tip: "Next"; enabled: playerState.hasTrack; onClicked: playerState.next() }
            IconButton { iconName: playerState.repeat === "one" ? "repeatOne" : "repeat"; iconColor: playerState.repeat !== "off" ? Theme.accent : Theme.secondary; tip: "Repeat: " + playerState.repeat; enabled: playerState.hasTrack; onClicked: appState.requestAction("repeat") }
        }
        Text { x: 0; y: 63; width: 38; text: Theme.timeLabel(playerState.position); color: Theme.secondary; font.pixelSize: 11; horizontalAlignment: Text.AlignRight }
        AccentSlider {
            id: progress
            objectName: "playbackSeek"
            x: 46; y: 48; width: parent.width - 92; height: 40
            from: 0; to: 1; value: playerState.progress
            enabled: playerState.hasTrack; Accessible.name: "Playback position"
            onMoved: playerState.seekFraction(value)
        }
        Text { anchors.right: parent.right; y: 63; width: 38; text: Theme.timeLabel(playerState.duration); color: Theme.secondary; font.pixelSize: 11 }
        BusyIndicator { anchors.right: parent.right; y: 10; width: 28; height: 28; visible: playerState.busy; running: visible }
    }
    Row {
        id: tools
        anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
        IconButton { iconName: "more"; tip: "Current song options"; enabled: playerState.hasTrack; onClicked: appState.showMenu(playerState.currentTrack, {}) }
        IconButton { iconName: "lyrics"; tip: "Lyrics"; iconColor: appState.expanded && appState.playerTab === "Lyrics" ? Theme.accent : Theme.secondary; onClicked: { appState.setPlayerTab("Lyrics"); appState.setExpanded(true) } }
        IconButton { iconName: "queue"; tip: "Queue"; iconColor: appState.expanded && appState.playerTab === "Up next" ? Theme.accent : Theme.secondary; onClicked: { appState.setPlayerTab("Up next"); appState.setExpanded(true) } }
        IconButton { id: volume; iconName: appState.volume > 0 ? "volume" : "muted"; tip: root.compact ? "Volume" : appState.volume > 0 ? "Mute" : "Unmute"; onClicked: root.compact ? volumePopup.open() : appState.toggleMute() }
        AccentSlider { width: 84; height: 44; visible: !root.compact; from: 0; to: 100; value: appState.volume; Accessible.name: "Volume"; onMoved: appState.setVolume(Math.round(value)) }
        IconButton { iconName: appState.expanded ? "down" : "up"; tip: appState.expanded ? "Close player page" : "Expand player"; onClicked: appState.requestAction("expandPlayer") }
    }
    Popup {
        id: volumePopup
        x: root.width - width - 12; y: -height - 8; width: 220; height: 64; padding: 8
        background: Rectangle { color: Theme.surface; radius: 12; border.color: Theme.border }
        contentItem: Row {
            IconButton { iconName: appState.volume ? "volume" : "muted"; tip: appState.volume ? "Mute" : "Unmute"; onClicked: appState.toggleMute() }
            AccentSlider { width: 156; height: 44; from: 0; to: 100; value: appState.volume; Accessible.name: "Volume"; onMoved: appState.setVolume(Math.round(value)) }
        }
    }
}
