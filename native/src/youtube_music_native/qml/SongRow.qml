import QtQuick
import "Theme.js" as Theme

FocusScope {
    id: root
    required property var media
    property int number: 0
    property bool showArtwork: true
    property string subtitle: {
        var label = media.kind && media.kind !== "song" ? media.kind.charAt(0).toUpperCase() + media.kind.slice(1) : ""
        if (media.artist) label += (label ? " · " : "") + media.artist
        if (media.album && media.album.name) label += (label ? " · " : "") + media.album.name
        return label
    }
    signal activated(var item)
    signal menuRequested(var item)
    implicitHeight: 64
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: (media.title || "Song") + ", " + (media.artist || "")
    Accessible.onPressAction: activated(media)
    Keys.onReturnPressed: activated(media)
    Rectangle { anchors.fill: parent; radius: 4; color: hover.hovered ? "#1affffff" : "transparent"; border.color: root.activeFocus ? "white" : "transparent"; border.width: 1 }
    Cover { id: art; visible: root.showArtwork; x: 8; anchors.verticalCenter: parent.verticalCenter; width: 48; height: 48; radius: 3; source: root.media.thumbnail || ""; accent: root.media.accent || "#29363b"; Symbol { anchors.centerIn: parent; name: "play"; width: 28; height: 28; visible: hover.hovered || root.activeFocus } }
    Text { id: rank; x: root.showArtwork ? 68 : 16; width: root.number > 0 ? 28 : 0; visible: root.number > 0; anchors.verticalCenter: parent.verticalCenter; text: root.number; color: Theme.secondary; font.pixelSize: 14 }
    Column {
        x: root.showArtwork ? root.number > 0 ? 104 : 72 : 56
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - x - (root.showArtwork ? 36 : 76); spacing: 3
        opacity: root.media.available === false ? 0.5 : 1
        Text { width: parent.width; text: root.media.title || "Unavailable song"; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.foreground; font.pixelSize: 14 }
        Text { width: parent.width; text: root.showArtwork ? root.subtitle : root.media.views ? root.media.views + " plays" : (root.media.artist || ""); textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.secondary; font.pixelSize: 14 }
    }
    Text { anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; visible: !root.showArtwork; text: Math.floor((root.media.duration || 0) / 60) + ":" + String((root.media.duration || 0) % 60).padStart(2, "0"); color: Theme.secondary; font.pixelSize: 14 }
    HoverHandler { id: hover }
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton; cursorShape: Qt.PointingHandCursor; onClicked: function(mouse) { if (mouse.button === Qt.RightButton) root.menuRequested(root.media); else root.activated(root.media) } }
}
