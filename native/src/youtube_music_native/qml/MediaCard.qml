import QtQuick
import "Theme.js" as Theme

FocusScope {
    id: root
    required property var media
    property var menuContext: ({})
    readonly property bool song: !media.kind || media.kind === "song"
    readonly property bool currentSong: song && playerState.hasTrack && (media.videoId || media.id) === (playerState.currentTrack.videoId || playerState.currentTrack.id)
    readonly property bool album: media.kind === "album"
    readonly property bool currentAlbum: !!(album && playerState.hasTrack && ((media.id && playerState.currentTrack.album && media.id === playerState.currentTrack.album.id) || (media.title && playerState.currentTrack.album && media.title === playerState.currentTrack.album.name)))
    readonly property bool playableCollection: album || media.kind === "playlist"
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
    Accessible.onPressAction: activateCard()
    Keys.onReturnPressed: activateCard()
    function activateArtwork() {
        if (root.playableCollection) {
            if (root.currentAlbum) playerState.togglePlayback()
            else root.playRequested(root.media)
        } else if (root.currentSong) playerState.togglePlayback()
        else root.activated(root.media)
    }
    function activateCard() {
        if (root.currentSong) playerState.togglePlayback()
        else root.activated(root.media)
    }
    Keys.onPressed: event => { if (event.key === Qt.Key_Menu || event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier) { appState.showMenu(root.media, root.menuContext); event.accepted = true } }
    implicitWidth: Theme.cardWidth
    implicitHeight: Theme.cardHeight
    HoverHandler { id: cardHover }
    Rectangle { anchors.fill: parent; radius: 10; color: cardHover.hovered ? Theme.hover : Theme.surface; border.color: root.activeFocus ? Theme.accent : Theme.border; border.width: root.activeFocus ? 2 : 1 }
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        onClicked: mouse => { root.forceActiveFocus(); if (mouse.button === Qt.RightButton) appState.showMenu(root.media, root.menuContext); else root.activateCard() }
    }
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
            color: "#22000000"
            visible: hover.hovered || root.activeFocus
            border.color: root.activeFocus ? Theme.accent : "transparent"
        }
        Rectangle { anchors.centerIn: parent; width: 44; height: 44; radius: 22; color: Theme.accent; visible: (hover.hovered || root.activeFocus) && (root.song || root.playableCollection) }
        Symbol {
            anchors.centerIn: parent
            name: (root.currentSong || root.currentAlbum) && playerState.playing ? "pause" : "play"
            width: 20; height: 20; color: Theme.onAccent
            visible: (hover.hovered || root.activeFocus) && (root.song || root.playableCollection)
        }
        HoverHandler { id: hover }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onClicked: mouse => { root.forceActiveFocus(); if (mouse.button === Qt.RightButton) appState.showMenu(root.media, root.menuContext); else root.activateArtwork() }
        }
        IconButton { anchors.right: parent.right; anchors.top: parent.top; width: 36; height: 36; iconName: "more"; tip: "More options for " + (root.media.title || "music"); visible: hover.hovered || root.activeFocus; onClicked: appState.showMenu(root.media, root.menuContext) }
        Rectangle {
            x: 8; anchors.bottom: parent.bottom; anchors.bottomMargin: 8
            width: 20; height: 20; color: "transparent"; visible: !!root.downloadStatus && root.downloadStatus !== "downloading" && root.downloadStatus !== "queued"
            Symbol { anchors.centerIn: parent; width: 16; height: 16; name: root.downloadStatus === "ready" ? "check" : "download"; color: root.downloadStatus === "damaged" ? "#ffb4a6" : Theme.accent }
        }
        IconButton {
            x: 4; anchors.bottom: parent.bottom; anchors.bottomMargin: 4
            width: 28; height: 28; iconName: root.downloadStatus === "ready" ? "check" : "download"
            iconColor: root.downloadStatus === "ready" ? Theme.accent : Theme.foreground
            tip: root.downloadStatus === "ready" ? "Downloaded" : root.downloadStatus === "downloading" || root.downloadStatus === "queued" ? "Download in progress" : "Download " + (root.media.title || "music")
            visible: hover.hovered || root.activeFocus
            enabled: !!(root.media.id || root.media.videoId) && root.downloadStatus !== "ready" && root.downloadStatus !== "downloading" && root.downloadStatus !== "queued"
            onClicked: downloadsState.download(root.media)
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
        Accessible.role: root.media.kind === "album" ? Accessible.Link : Accessible.StaticText
        Accessible.onPressAction: if (root.media.kind === "album") root.activated(root.media)
        MouseArea {
            anchors.fill: parent
            enabled: root.media.kind === "album"
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: root.activated(root.media)
        }
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
