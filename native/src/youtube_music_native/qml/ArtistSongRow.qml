import QtQuick
import "Theme.js" as Theme

FocusScope {
    id: root
    required property var media
    signal activated(var item)
    implicitHeight: 49
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: media.title || "Song"
    Accessible.onPressAction: activated(media)
    Keys.onReturnPressed: activated(media)
    Rectangle { anchors.fill: parent; color: hover.hovered ? "#202020" : "transparent"; border.color: root.activeFocus ? "white" : "transparent" }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#222222" }
    Cover { x: 8; anchors.verticalCenter: parent.verticalCenter; width: 32; height: 32; radius: 3; source: root.media.thumbnail || ""; accent: root.media.accent || "#283238" }
    Text { x: 64; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.30; text: root.media.title || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: "white"; font.pixelSize: 14 }
    Text { x: parent.width * 0.39; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.13; text: root.media.artist || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.secondary; font.pixelSize: 14; visible: root.width > 650 }
    Text { x: parent.width * 0.54; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.13; text: root.media.views ? root.media.views + " plays" : ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.secondary; font.pixelSize: 14; visible: root.width > 650 }
    Text { x: parent.width * 0.69; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.23; text: root.media.album ? root.media.album.name || "" : ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.secondary; font.pixelSize: 14 }
    HoverHandler { id: hover }
    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.activated(root.media) }
}
