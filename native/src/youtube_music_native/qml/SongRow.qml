import QtQuick
import "Theme.js" as Theme

FocusScope {
    id: root
    required property var media
    property int number: 0
    property bool showArtwork: true
    property bool showDuration: !showArtwork
    property bool tableLayout: false
    property bool showAlbum: false
    property var menuContext: ({})
    property string downloadStatus: downloadsState.trackStates[media.videoId || media.id] || media.downloadState || ""
    readonly property bool currentSong: playerState.hasTrack && (media.videoId || media.id) === (playerState.currentTrack.videoId || playerState.currentTrack.id)
    property string subtitle: {
        var label = media.kind && media.kind !== "song" ? media.kind.charAt(0).toUpperCase() + media.kind.slice(1) : ""
        if (media.artist) label += (label ? " · " : "") + media.artist
        if (media.album && media.album.name) label += (label ? " · " : "") + media.album.name
        return label
    }
    signal activated(var item)
    signal menuRequested(var item)
    onMenuRequested: item => appState.showMenu(item, menuContext)
    implicitHeight: 64
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: (media.title || "Song") + ", " + (media.artist || "")
    Accessible.description: downloadStatus === "ready" ? "Downloaded" : downloadStatus === "damaged" || downloadStatus === "missing" ? "Download needs repair" : downloadStatus === "downloading" || downloadStatus === "queued" ? "Downloading" : ""
    Accessible.onPressAction: activateSong()
    Keys.onReturnPressed: activateSong()
    function activateSong() { if (root.currentSong) playerState.togglePlayback(); else root.activated(root.media) }
    Keys.onPressed: event => { if (event.key === Qt.Key_Menu || event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier) { root.menuRequested(root.media); event.accepted = true } }
    Rectangle { anchors.fill: parent; radius: 4; color: hover.hovered ? "#1affffff" : "transparent"; border.color: root.activeFocus ? Theme.accent : "transparent"; border.width: 1 }
    Cover {
        id: art
        visible: root.showArtwork
        x: root.tableLayout ? 44 : 8; anchors.verticalCenter: parent.verticalCenter
        width: root.tableLayout ? 40 : 48; height: width
        radius: root.media.kind === "artist" ? width / 2 : 6
        placeholder: root.media.kind === "artist" ? "profile" : "music"
        source: root.media.thumbnail || ""; mediaKey: root.media.videoId || root.media.id || ""; accent: root.media.accent || Theme.selected
        Rectangle { anchors.centerIn: parent; width: 28; height: 28; radius: 14; color: Theme.accent; visible: root.media.kind !== "artist" && (hover.hovered || root.activeFocus) }
        Symbol { anchors.centerIn: parent; name: root.currentSong && playerState.playing ? "pause" : "play"; width: 14; height: 14; color: Theme.onAccent; visible: root.media.kind !== "artist" && (hover.hovered || root.activeFocus) }
    }
    Text { id: rank; x: root.tableLayout ? 12 : root.showArtwork ? 68 : 16; width: root.number > 0 ? 28 : 0; visible: root.number > 0; anchors.verticalCenter: parent.verticalCenter; text: root.number; color: Theme.secondary; font.pixelSize: 14 }
    Column {
        x: root.tableLayout ? root.showArtwork ? 100 : 48 : root.showArtwork ? root.number > 0 ? 104 : 72 : 56
        anchors.verticalCenter: parent.verticalCenter
        width: (root.showAlbum ? parent.width * 0.54 : parent.width - (root.showDuration ? 112 : 56)) - x; spacing: 3
        opacity: root.media.available === false ? 0.5 : 1
        Text { width: parent.width; text: root.media.title || "Unavailable song"; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.foreground; font.pixelSize: 14 }
        Row {
            width: parent.width; spacing: 6
            Symbol { id: downloaded; width: 16; height: 16; visible: !!root.downloadStatus; name: root.downloadStatus === "ready" ? "check" : "download"; color: root.downloadStatus === "damaged" || root.downloadStatus === "missing" ? "#ffb4a6" : Theme.secondary }
            Text { width: parent.width - (downloaded.visible ? 22 : 0); text: root.tableLayout ? root.media.artist || "" : root.showArtwork ? root.subtitle : root.media.views ? root.media.views + " plays" : (root.media.artist || ""); textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.secondary; font.pixelSize: 14 }
        }
    }
    Text { x: parent.width * 0.56; width: parent.width * 0.44 - 120; anchors.verticalCenter: parent.verticalCenter; visible: root.showAlbum; text: root.media.album ? root.media.album.name || "" : ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.secondary; font.pixelSize: 13 }
    Text { anchors.right: parent.right; anchors.rightMargin: 56; anchors.verticalCenter: parent.verticalCenter; visible: root.showDuration; text: root.media.duration ? Theme.timeLabel(root.media.duration) : "–"; color: Theme.secondary; font.pixelSize: 13 }
    HoverHandler { id: hover }
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton; cursorShape: Qt.PointingHandCursor; onClicked: function(mouse) { if (mouse.button === Qt.RightButton) root.menuRequested(root.media); else root.activateSong() } }
    IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; iconName: "more"; tip: "More options for " + (root.media.title || "song"); visible: hover.hovered || root.activeFocus; onClicked: root.menuRequested(root.media) }
}
