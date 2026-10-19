import QtQuick
import "Theme.js" as Theme

FocusScope {
    id: root
    required property var media
    property var menuContext: ({})
    property string downloadStatus: {
        if (!media.kind || media.kind === "song") return downloadsState.trackStates[media.videoId || media.id] || media.downloadState || ""
        var values = downloadsState.collections
        for (var i = 0; i < values.length; i++) if (values[i].key === media.kind + ":" + media.id) return values[i].state === "complete" ? "ready" : values[i].state
        return ""
    }
    signal playRequested(var item)
    signal activated(var item)
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: media.title || "Music"
    Accessible.description: downloadStatus === "ready" ? "Downloaded" : downloadStatus === "damaged" ? "Download needs repair" : ""
    Accessible.onPressAction: activated(media)
    Keys.onReturnPressed: activated(media)
    Keys.onPressed: event => { if (event.key === Qt.Key_Menu || event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier) { appState.showMenu(root.media, root.menuContext); event.accepted = true } }
    implicitWidth: Theme.cardWidth
    implicitHeight: Theme.cardHeight
    HoverHandler { id: cardHover }
    Rectangle { anchors.fill: parent; radius: 10; color: cardHover.hovered ? Theme.hover : Theme.surface; border.color: root.activeFocus ? Theme.accent : Theme.border; border.width: root.activeFocus ? 2 : 1 }
    Cover {
        id: cover
        x: 16; y: 16
        width: root.width - 32
        height: width
        radius: root.media.kind === "artist" ? width / 2 : 8
        placeholder: root.media.kind === "artist" ? "profile" : "music"
        source: root.media.thumbnail || ""
        mediaKey: root.media.kind === "album" || root.media.kind === "playlist" ? root.media.kind + ":" + root.media.id : root.media.videoId || root.media.id || ""
        accent: root.media.accent || Theme.selected
        Rectangle {
            anchors.fill: parent
            radius: cover.radius
            color: "#33000000"
            visible: hover.hovered || root.activeFocus
            border.color: root.activeFocus ? Theme.accent : "transparent"
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
        Rectangle {
            x: 8; anchors.bottom: parent.bottom; anchors.bottomMargin: 8
            width: 24; height: 24; radius: 12; color: "#dd212121"; visible: !!root.downloadStatus
            Symbol { anchors.centerIn: parent; width: 16; height: 16; name: root.downloadStatus === "ready" ? "check" : "download"; color: root.downloadStatus === "damaged" ? "#ffb4a6" : "white" }
        }
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
        anchors.topMargin: 12
        x: 16; width: parent.width - 32
        text: root.media.title || ""
        textFormat: Text.PlainText
        color: Theme.foreground
        font.family: Theme.bodyFont
        font.pixelSize: 14
        font.weight: Font.Bold
        wrapMode: Text.Wrap
        maximumLineCount: 1
        elide: Text.ElideRight
    }
    Text {
        anchors.top: title.bottom
        anchors.topMargin: 6
        x: 16; width: parent.width - 32
        text: (root.media.label || (root.media.kind ? root.media.kind.charAt(0).toUpperCase() + root.media.kind.slice(1) : "Song")) + (root.media.artist ? " · " + root.media.artist : "")
        textFormat: Text.PlainText
        color: Theme.secondary
        font.family: Theme.bodyFont
        font.pixelSize: 14
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }
}
