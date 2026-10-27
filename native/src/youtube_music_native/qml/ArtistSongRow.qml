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
    Keys.onPressed: event => { if (event.key === Qt.Key_Menu || event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier) { appState.showMenu(root.media, {}); event.accepted = true } }
    Rectangle { anchors.fill: parent; color: hover.hovered ? themeState.surface : "transparent"; border.color: root.activeFocus ? themeState.accent : "transparent" }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: themeState.surface }
    Cover { x: 8; anchors.verticalCenter: parent.verticalCenter; width: 32; height: 32; radius: 3; source: root.media.thumbnail || ""; mediaKey: root.media.videoId || root.media.id || ""; accent: root.media.accent || themeState.selected }
    Text { x: 64; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.30; text: root.media.title || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: themeState.foreground; font.pixelSize: 14 }
    Text { x: parent.width * 0.39; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.13; text: root.media.artist || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: themeState.secondary; font.pixelSize: 14; visible: root.width > 650 }
    Text { x: parent.width * 0.54; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.13; text: root.media.views ? root.media.views + " plays" : ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: themeState.secondary; font.pixelSize: 14; visible: root.width > 650 }
    Text {
        id: albumName
        x: parent.width * 0.69; anchors.verticalCenter: parent.verticalCenter; width: Math.min(implicitWidth, parent.width * 0.23 - 112)
        text: root.media.album ? root.media.album.name || "" : ""
        textFormat: Text.PlainText; elide: Text.ElideRight; color: albumLink.containsMouse ? themeState.foreground : themeState.secondary; font.pixelSize: 14
        MouseArea {
            id: albumLink
            anchors.fill: parent; z: 2
            enabled: !!(root.media.album && root.media.album.id)
            hoverEnabled: enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: browseState.open({kind: "album", id: root.media.album.id, title: root.media.album.name})
        }
    }
    HoverHandler { id: hover }
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton; cursorShape: Qt.PointingHandCursor; onClicked: mouse => { if (mouse.button === Qt.RightButton) appState.showMenu(root.media, {}); else root.activated(root.media) } }
    DownloadButton {
        id: downloadButton
        anchors.right: parent.right; anchors.rightMargin: 56; anchors.verticalCenter: parent.verticalCenter
        visible: hover.hovered || downloadButton.activeFocus || downloadButton.status === "complete" || downloadButton.status === "ready" || downloadButton.status === "downloading" || downloadButton.status === "queued"
        media: ({kind: "song", id: root.media.videoId || root.media.id || "", videoId: root.media.videoId || "", title: root.media.title || "", thumbnail: root.media.thumbnail || ""})
    }
    IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; iconName: "more"; tip: "More options for " + (root.media.title || "song"); visible: hover.hovered || root.activeFocus; onClicked: appState.showMenu(root.media, {}) }
}
