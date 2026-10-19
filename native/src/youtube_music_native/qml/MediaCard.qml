import QtQuick
import "Theme.js" as Theme

Item {
    id: root
    required property var media
    signal playRequested(var item)
    implicitWidth: 146
    implicitHeight: 218
    Cover {
        id: cover
        width: root.width
        height: width
        source: root.media.thumbnail || ""
        accent: root.media.accent || "#283238"
        Rectangle {
            anchors.fill: parent
            color: "#33000000"
            visible: hover.hovered
        }
        Symbol {
            anchors.centerIn: parent
            name: "play"
            width: 48
            height: 48
            visible: hover.hovered
        }
        HoverHandler { id: hover }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.playRequested(root.media)
        }
    }
    Text {
        id: title
        anchors.top: cover.bottom
        anchors.topMargin: 12
        width: parent.width
        text: root.media.title || ""
        textFormat: Text.PlainText
        color: Theme.foreground
        font.family: Theme.bodyFont
        font.pixelSize: 14
        font.weight: Font.Medium
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }
    Text {
        anchors.top: title.bottom
        anchors.topMargin: 4
        width: parent.width
        text: (root.media.kind || "Song") + " · " + (root.media.artist || "")
        textFormat: Text.PlainText
        color: Theme.secondary
        font.family: Theme.bodyFont
        font.pixelSize: 14
        maximumLineCount: 1
        elide: Text.ElideRight
    }
}
