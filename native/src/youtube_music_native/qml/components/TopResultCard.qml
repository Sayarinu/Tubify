import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

// The single best match for a search, shown large like a music app's "Top result".
FocusScope {
    id: root
    objectName: "searchTopResult"
    property var media: ({})
    readonly property bool artist: media.kind === "artist"
    readonly property bool playable: !artist
    readonly property string kindLabel: artist ? "Artist" : media.kind === "album" ? (media.label || "Album") : media.kind === "playlist" ? "Playlist" : "Song"
    activeFocusOnTab: true
    implicitHeight: 248
    Accessible.role: Accessible.Button
    Accessible.name: "Top result: " + (media.title || "") + ", " + kindLabel
    Keys.onReturnPressed: browseState.open(root.media)
    HoverHandler { id: hover }
    Rectangle {
        anchors.fill: parent; radius: 12
        color: hover.hovered ? themeState.hover : themeState.surface
        border.width: root.activeFocus ? 2 : 0; border.color: themeState.accent
        Behavior on color { enabled: !appState.reducedMotion; ColorAnimation { duration: Theme.motionFast } }
    }
    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { root.forceActiveFocus(); browseState.open(root.media) } }
    Column {
        x: 24; y: 24; width: parent.width - 48; spacing: 16
        Cover {
            width: 104; height: 104
            radius: root.artist ? width / 2 : 8
            placeholder: root.artist ? "profile" : "music"
            source: root.media.thumbnail || ""
            accent: themeState.selected
        }
        Text {
            width: parent.width; text: root.media.title || ""; textFormat: Text.PlainText; elide: Text.ElideRight
            color: themeState.foreground; font.pixelSize: 32; font.bold: true
        }
        Row {
            spacing: 8
            Rectangle {
                width: kind.implicitWidth + 20; height: 26; radius: 13; color: themeState.background
                Text { id: kind; anchors.centerIn: parent; text: root.kindLabel; color: themeState.foreground; font.pixelSize: 12; font.bold: true }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, root.width - kind.implicitWidth - 96)
                text: root.artist ? (root.media.subscribers ? root.media.subscribers + " subscribers" : "") : (root.media.artist || "")
                textFormat: Text.PlainText; elide: Text.ElideRight; color: themeState.secondary; font.pixelSize: 14
            }
        }
    }
    RoundButton {
        objectName: "searchTopResultPlay"
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 20
        width: 52; height: 52
        visible: root.playable
        opacity: hover.hovered || activeFocus || root.activeFocus ? 1 : 0
        Behavior on opacity { enabled: !appState.reducedMotion; NumberAnimation { duration: Theme.motionFast } }
        Accessible.name: "Play " + (root.media.title || "")
        background: Rectangle { radius: width / 2; color: parent.hovered ? themeState.accentHover : themeState.accent }
        contentItem: Item { Symbol { anchors.centerIn: parent; width: 22; height: 22; name: "play"; color: themeState.onAccent } }
        onClicked: browseState.play(root.media)
    }
}
