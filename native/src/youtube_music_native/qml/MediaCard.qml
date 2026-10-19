import QtQuick
import "Theme.js" as Theme

FocusScope {
    id: root
    required property var media
    property var menuContext: ({})
    signal playRequested(var item)
    signal activated(var item)
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: media.title || "Music"
    Accessible.onPressAction: activated(media)
    Keys.onReturnPressed: activated(media)
    Keys.onPressed: event => { if (event.key === Qt.Key_Menu || event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier) { appState.showMenu(root.media, root.menuContext); event.accepted = true } }
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
            visible: hover.hovered || root.activeFocus
            border.color: root.activeFocus ? "white" : "transparent"
        }
        Symbol {
            anchors.centerIn: parent
            name: "play"
            width: 48
            height: 48
            visible: (hover.hovered || root.activeFocus) && (!root.media.kind || root.media.kind === "song")
        }
        HoverHandler { id: hover }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onClicked: mouse => { root.forceActiveFocus(); if (mouse.button === Qt.RightButton) appState.showMenu(root.media, root.menuContext); else root.activated(root.media) }
        }
        IconButton { anchors.right: parent.right; anchors.top: parent.top; width: 36; height: 36; iconName: "more"; tip: "More options for " + (root.media.title || "music"); visible: hover.hovered || root.activeFocus; onClicked: appState.showMenu(root.media, root.menuContext) }
        Item {
            anchors.right: parent.right; anchors.bottom: parent.bottom; width: 48; height: 48
            visible: (hover.hovered || root.activeFocus) && (root.media.kind === "album" || root.media.kind === "playlist")
            Rectangle { anchors.centerIn: parent; width: 36; height: 36; radius: 18; color: "#cc000000" }
            Symbol { anchors.centerIn: parent; name: "play"; width: 24; height: 24 }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.playRequested(root.media) }
        }
    }
    Text {
        id: title
        anchors.top: cover.bottom
        anchors.topMargin: 16
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
        text: (root.media.label || (root.media.kind ? root.media.kind.charAt(0).toUpperCase() + root.media.kind.slice(1) : "Song")) + (root.media.artist ? " · " + root.media.artist : "")
        textFormat: Text.PlainText
        color: Theme.secondary
        font.family: Theme.bodyFont
        font.pixelSize: 14
        maximumLineCount: 1
        elide: Text.ElideRight
    }
}
