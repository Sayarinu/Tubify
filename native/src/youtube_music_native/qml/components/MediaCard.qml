import QtQuick
import "../Theme.js" as Theme

// Artwork is the card: no frame, with the title and subtitle set underneath and the
// play, menu and download controls floating on the artwork.
FocusScope {
    id: root
    required property var media
    property var menuContext: ({})
    readonly property bool song: !media.kind || media.kind === "song"
    readonly property bool currentSong: song && playerState.hasTrack && (media.videoId || media.id) === (playerState.currentTrack.videoId || playerState.currentTrack.id)
    readonly property bool album: media.kind === "album"
    readonly property bool artist: media.kind === "artist"
    readonly property bool currentAlbum: !!(album && playerState.hasTrack && ((media.id && playerState.currentTrack.album && media.id === playerState.currentTrack.album.id) || (media.title && playerState.currentTrack.album && media.title === playerState.currentTrack.album.name)))
    readonly property bool playableCollection: album || media.kind === "playlist"
    readonly property bool playable: song || playableCollection
    readonly property bool nowPlaying: (currentSong || currentAlbum) && playerState.playing
    readonly property var primaryArtist: media.artists && media.artists.length ? media.artists[0] : ({})
    // Only albums and artists name their kind; songs and playlists read clearly from the artist or owner alone.
    readonly property string kindLabel: artist ? "Artist" : album ? (media.label || "Album") : ""
    // Clicks never move focus onto a card, so focus here always comes from the keyboard: only it shows the ring and holds the controls up.
    readonly property bool keyboardFocus: activeFocus
    readonly property bool engaged: cardHover.hovered || keyboardFocus
    signal playRequested(var item)
    signal activated(var item)
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: media.title || "Music"
    Accessible.description: kindLabel
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
        if (root.artist || root.playableCollection) root.activated(root.media)
        else if (root.song) root.activateArtwork()
    }
    Keys.onPressed: event => { if (event.key === Qt.Key_Menu || event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier) { appState.showMenu(root.media, root.menuContext); event.accepted = true } }
    implicitWidth: Theme.cardWidth
    implicitHeight: Theme.cardHeight
    HoverHandler { id: cardHover }
    // The whole card, artwork included, opens an album, playlist or artist like its title does; only the play button plays it.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        onClicked: mouse => { if (mouse.button === Qt.RightButton) appState.showMenu(root.media, root.menuContext); else root.activateCard() }
    }
    // Keyboard focus rings the artwork rather than a frame around the whole card.
    Rectangle {
        anchors.fill: cover; anchors.margins: -4
        radius: cover.radius + 4
        color: "transparent"; border.width: 2; border.color: themeState.accent
        visible: root.keyboardFocus
    }
    Cover {
        id: cover
        width: root.width
        height: width
        radius: root.artist ? width / 2 : Theme.radiusMedium
        placeholder: root.artist ? "profile" : "music"
        source: root.media.thumbnail || ""
        mediaKey: root.album || root.media.kind === "playlist" ? root.media.kind + ":" + root.media.id : root.media.videoId || root.media.id || ""
        accent: root.media.accent || themeState.selected
        // Play sits in the corner on hover, and stays there as a pause button while this item plays.
        Rectangle {
            objectName: "cardPlay"
            anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 10
            width: 44; height: 44; radius: 22
            color: playArea.containsMouse ? themeState.accentHover : themeState.accent
            visible: root.playable
            opacity: root.engaged || root.nowPlaying ? 1 : 0
            scale: root.engaged || root.nowPlaying ? 1 : 0.85
            Behavior on opacity { enabled: !appState.reducedMotion; NumberAnimation { duration: Theme.motionFast } }
            Behavior on scale { enabled: !appState.reducedMotion; NumberAnimation { duration: Theme.motionMedium; easing.type: Easing.OutBack } }
            Symbol { anchors.centerIn: parent; name: root.nowPlaying ? "pause" : "play"; width: 20; height: 20; color: themeState.onAccent }
            MouseArea { id: playArea; anchors.fill: parent; enabled: parent.opacity > 0; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { root.activateArtwork() } }
        }
        IconButton {
            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: root.artist ? parent.width * 0.1 : 6
            width: 32; height: 32; iconSize: 20
            iconName: "more"; iconColor: "white"
            tip: "More options for " + (root.media.title || "music")
            visible: root.engaged
            background: Rectangle { radius: width / 2; color: Qt.rgba(0, 0, 0, parent.hovered ? 0.65 : 0.4); border.width: parent.visualFocus ? 2 : 0; border.color: themeState.accent }
            onClicked: appState.showMenu(root.media, root.menuContext)
        }
        // Download status is a badge on the artwork: always shown once saved or saving, otherwise on hover.
        DownloadButton {
            id: downloadButton
            anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 6
            width: 32; height: 32; iconSize: 18
            visible: !root.artist && (root.engaged || downloadButton.activeFocus || ["complete", "ready", "downloading", "queued", "damaged"].indexOf(downloadButton.status) >= 0)
            iconColor: status === "complete" || status === "ready" ? themeState.accent : status === "damaged" ? themeState.error : "white"
            background: Rectangle { radius: width / 2; color: Qt.rgba(0, 0, 0, parent.hovered ? 0.65 : 0.4); border.width: parent.visualFocus ? 2 : 0; border.color: themeState.accent }
            media: ({kind: root.song ? "song" : root.media.kind, id: root.media.videoId || root.media.id || "", videoId: root.media.videoId || "", title: root.media.title || "", thumbnail: root.media.thumbnail || ""})
        }
    }
    Text {
        id: title
        anchors.top: cover.bottom; anchors.topMargin: 10
        width: parent.width
        horizontalAlignment: root.artist ? Text.AlignHCenter : Text.AlignLeft
        text: root.media.title || ""
        textFormat: Text.PlainText
        color: themeState.foreground
        font.pixelSize: Theme.textBody
        font.weight: Font.DemiBold
        font.underline: titleLink.containsMouse
        maximumLineCount: 1
        elide: Text.ElideRight
        Accessible.role: root.playableCollection ? Accessible.Link : Accessible.StaticText
        Accessible.onPressAction: if (root.playableCollection) root.activated(root.media)
        MouseArea {
            id: titleLink
            width: Math.min(parent.implicitWidth, parent.width); height: parent.height
            x: root.artist ? (parent.width - width) / 2 : 0
            enabled: root.playableCollection
            hoverEnabled: enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: root.activated(root.media)
        }
    }
    Row {
        id: subtitle
        anchors.top: title.bottom; anchors.topMargin: 3
        x: root.artist ? Math.max(0, (parent.width - implicitWidth) / 2) : 0
        Text {
            id: kind
            text: root.kindLabel + (root.kindLabel && artistName.visible ? " • " : "")
            visible: text.length > 0
            color: themeState.secondary; font.pixelSize: 13
        }
        Text {
            id: artistName
            objectName: "cardArtist"
            text: root.artist ? "" : root.media.artist || root.primaryArtist.name || ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: artistLink.containsMouse || activeFocus ? themeState.foreground : themeState.secondary; font.pixelSize: 13; visible: text.length > 0
            width: Math.min(implicitWidth, Math.max(0, root.width - (kind.visible ? kind.implicitWidth : 0)))
            font.underline: artistLink.containsMouse || activeFocus
            activeFocusOnTab: !!root.primaryArtist.id
            function openArtist() { if (root.primaryArtist.id) browseState.open({kind: "artist", id: root.primaryArtist.id, title: root.primaryArtist.name}) }
            Accessible.role: root.primaryArtist.id ? Accessible.Link : Accessible.StaticText
            Accessible.onPressAction: openArtist()
            Keys.onReturnPressed: openArtist()
            Keys.onSpacePressed: openArtist()
            MouseArea { id: artistLink; anchors.fill: parent; z: 2; enabled: !!root.primaryArtist.id; hoverEnabled: enabled; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: artistName.openArtist() }
        }
    }
}
