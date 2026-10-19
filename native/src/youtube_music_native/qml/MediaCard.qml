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
    readonly property var primaryArtist: media.artists && media.artists.length ? media.artists[0] : ({})
    signal playRequested(var item)
    signal activated(var item)
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: media.title || "Music"
    Accessible.description: ""
    Accessible.onPressAction: activateCard()
    Keys.onReturnPressed: activateCard()
    function activateArtwork() {
        if (root.playableCollection) {
            if (root.currentAlbum) playerState.togglePlayback()
            else root.playRequested(root.media)
        } else if (root.song) {
            if (root.currentSong) playerState.togglePlayback()
            else root.playRequested(root.media)
        } else root.activated(root.media)
    }
    function activateCard() {
        if (root.media.kind === "artist" || root.playableCollection) root.activated(root.media)
    }
    Keys.onPressed: event => { if (event.key === Qt.Key_Menu || event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier) { appState.showMenu(root.media, root.menuContext); event.accepted = true } }
    implicitWidth: Theme.cardWidth
    implicitHeight: Theme.cardHeight
    HoverHandler { id: cardHover }
    Rectangle { anchors.fill: parent; radius: 10; color: cardHover.hovered ? themeState.hover : themeState.surface; border.color: root.activeFocus ? themeState.accent : themeState.border; border.width: root.activeFocus ? 2 : 1 }
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
        accent: root.media.accent || themeState.selected
        Rectangle {
            anchors.fill: parent
            radius: cover.radius
            color: "#22000000"
            visible: hover.hovered || root.activeFocus
            border.color: root.activeFocus ? themeState.accent : "transparent"
        }
        Rectangle { anchors.centerIn: parent; width: 44; height: 44; radius: 22; color: themeState.accent; visible: (hover.hovered || root.activeFocus) && (root.song || root.playableCollection) }
        Symbol {
            anchors.centerIn: parent
            name: (root.currentSong || root.currentAlbum) && playerState.playing ? "pause" : "play"
            width: 20; height: 20; color: themeState.onAccent
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
    }
    Text {
        id: title
        anchors.top: cover.bottom
        anchors.topMargin: 12
        x: 16; width: parent.width - 32
        text: root.media.title || ""
        textFormat: Text.PlainText
        color: themeState.foreground
        font.family: Theme.bodyFont
        font.pixelSize: 14
        font.weight: Font.Bold
        wrapMode: Text.Wrap
        maximumLineCount: 1
        elide: Text.ElideRight
        Accessible.role: root.playableCollection ? Accessible.Link : Accessible.StaticText
        Accessible.onPressAction: if (root.playableCollection) root.activated(root.media)
        MouseArea {
            anchors.fill: parent
            enabled: root.playableCollection
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: root.activated(root.media)
        }
    }
    Row {
        id: subtitle
        anchors.top: title.bottom
        anchors.topMargin: 6
        x: 16; width: parent.width - 32
        spacing: 5
        Text {
            text: root.media.label || (root.media.kind ? root.media.kind.charAt(0).toUpperCase() + root.media.kind.slice(1) : "Song")
            color: themeState.secondary; font.family: Theme.bodyFont; font.pixelSize: 14
        }
        Text {
            id: artist
            objectName: "cardArtist"
            text: root.media.artist || root.primaryArtist.name || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: artistLink.containsMouse || activeFocus ? themeState.foreground : themeState.secondary; font.family: Theme.bodyFont; font.pixelSize: 14; visible: text.length > 0; width: Math.max(0, subtitle.width - x - 4)
            font.underline: artistLink.containsMouse || activeFocus
            activeFocusOnTab: !!root.primaryArtist.id
            function openArtist() { if (root.primaryArtist.id) browseState.open({kind: "artist", id: root.primaryArtist.id, title: root.primaryArtist.name}) }
            Accessible.role: root.primaryArtist.id ? Accessible.Link : Accessible.StaticText
            Accessible.onPressAction: openArtist()
            Keys.onReturnPressed: openArtist()
            Keys.onSpacePressed: openArtist()
            MouseArea { id: artistLink; anchors.fill: parent; z: 2; enabled: !!root.primaryArtist.id; hoverEnabled: enabled; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: artist.openArtist() }
        }
    }
    DownloadButton {
        id: downloadButton
        x: 8; anchors.top: subtitle.bottom; anchors.topMargin: 4; width: 36; height: 32
        visible: root.media.kind !== "artist" && (cardHover.hovered || downloadButton.activeFocus || downloadButton.status === "complete" || downloadButton.status === "ready" || downloadButton.status === "downloading" || downloadButton.status === "queued")
        media: ({kind: root.song ? "song" : root.media.kind, id: root.media.videoId || root.media.id || "", videoId: root.media.videoId || "", title: root.media.title || "", thumbnail: root.media.thumbnail || ""})
    }
}
