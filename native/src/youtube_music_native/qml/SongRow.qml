import QtQuick
import "Theme.js" as Theme

FocusScope {
    id: root
    required property var media
    property int number: 0
    property bool showArtwork: true
    property bool showDuration: !showArtwork
    property bool tableLayout: false
    property bool showAlbum: false
    property bool reorderable: false
    property bool queueRow: false
    property var menuContext: ({})
    property string downloadStatus: downloadsState.trackStates[media.videoId || media.id] || media.downloadState || ""
    readonly property bool currentSong: playerState.hasTrack && (queueRow && media.key ? !!media.current : (media.videoId || media.id) === (playerState.currentTrack.videoId || playerState.currentTrack.id))
    readonly property var artistItems: {
        if (media.artists && media.artists.length) return media.artists
        return (media.artist || "").split(" • ").filter(Boolean).map(name => ({name: name}))
    }
    signal activated(var item)
    signal menuRequested(var item)
    signal reorderDragStarted(real sceneX, real sceneY)
    signal reorderDragMoved(real sceneX, real sceneY)
    signal reorderDragFinished(real sceneX, real sceneY)
    onMenuRequested: item => appState.showMenu(item, menuContext)
    implicitHeight: 64
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: (media.title || "Song") + ", " + (media.artist || "")
    Accessible.description: downloadStatus === "ready" ? "Downloaded" : downloadStatus === "damaged" || downloadStatus === "missing" ? "Download needs repair" : downloadStatus === "downloading" || downloadStatus === "queued" ? "Downloading" : ""
    Accessible.onPressAction: activateSong()
    Keys.onReturnPressed: activateSong()
    function activateSong() { if (root.currentSong) playerState.togglePlayback(); else root.activated(root.media) }
    Keys.onPressed: event => { if (event.key === Qt.Key_Menu || event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier) { root.menuRequested(root.media); event.accepted = true } }
    Rectangle { anchors.fill: parent; radius: 4; color: !root.queueRow && hover.hovered ? "#1affffff" : "transparent"; border.color: root.activeFocus && !root.queueRow ? themeState.accent : "transparent"; border.width: 1 }
    Cover {
        id: art
        objectName: root.queueRow ? "queueRowArtwork-" + (root.media.key || root.media.videoId || root.media.id || "") : ""
        visible: root.showArtwork
        x: root.queueRow ? 0 : root.tableLayout ? 44 : 8; anchors.verticalCenter: parent.verticalCenter
        width: root.tableLayout || root.queueRow ? 40 : 48; height: width
        radius: root.media.kind === "artist" ? width / 2 : 6
        placeholder: root.media.kind === "artist" ? "profile" : "music"
        source: root.media.thumbnail || ""; mediaKey: root.media.videoId || root.media.id || ""; accent: root.media.accent || themeState.selected
        Rectangle { anchors.centerIn: parent; width: 28; height: 28; radius: 14; color: themeState.accent; visible: root.media.kind !== "artist" && (hover.hovered || root.activeFocus) }
        Symbol { anchors.centerIn: parent; name: root.currentSong && playerState.playing ? "pause" : "play"; width: 14; height: 14; color: themeState.onAccent; visible: root.media.kind !== "artist" && (hover.hovered || root.activeFocus) }
    }
    MouseArea {
        objectName: root.queueRow ? "queueArtworkActivate-" + (root.media.key || root.media.videoId || root.media.id || "") : ""
        anchors.fill: art
        z: 3
        visible: root.queueRow && root.showArtwork
        acceptedButtons: Qt.LeftButton
        cursorShape: Qt.PointingHandCursor
        onClicked: root.activateSong()
    }
    Text { id: rank; x: root.tableLayout ? 12 : root.showArtwork ? 68 : 16; width: root.number > 0 ? 28 : 0; visible: root.number > 0; anchors.verticalCenter: parent.verticalCenter; text: root.number; color: themeState.secondary; font.pixelSize: 14 }
    Column {
        objectName: root.queueRow ? "queueRowMetadata-" + (root.media.key || "") : ""
        x: root.queueRow ? 52 : root.tableLayout ? root.showArtwork ? 100 : 48 : root.showArtwork ? root.number > 0 ? 104 : 72 : 56
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, (root.showAlbum ? parent.width * 0.54 : parent.width - (root.queueRow ? 68 : root.showDuration ? 112 : 104)) - x); spacing: 3
        opacity: root.media.available === false ? 0.5 : 1
        Text { width: parent.width; text: root.media.title || "Unavailable song"; textFormat: Text.PlainText; elide: Text.ElideRight; color: themeState.foreground; font.pixelSize: 14 }
        Row {
            id: metadata
            width: parent.width; height: 18; spacing: 4; clip: true
            Text {
                id: metadataLabel
                visible: root.showArtwork && !!(root.media.label || root.media.kind && root.media.kind !== "song")
                text: root.media.label || (root.media.kind && root.media.kind !== "song" ? root.media.kind.charAt(0).toUpperCase() + root.media.kind.slice(1) : "")
                textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 14
            }
            Repeater {
                model: root.tableLayout || root.showArtwork ? root.artistItems : []
                delegate: Row {
                    required property var modelData
                    required property int index
                    height: metadata.height; spacing: 0
                    Text {
                        id: artistName
                        text: modelData.name || ""; textFormat: Text.PlainText; color: artistLink.containsMouse || activeFocus ? themeState.foreground : themeState.secondary; font.pixelSize: 14
                        font.underline: artistLink.containsMouse || activeFocus
                        activeFocusOnTab: !!text
                        Accessible.role: text ? Accessible.Link : Accessible.StaticText
                        Accessible.onPressAction: browseState.openArtist(modelData)
                        Keys.onReturnPressed: browseState.openArtist(modelData)
                        Keys.onSpacePressed: browseState.openArtist(modelData)
                        MouseArea {
                            id: artistLink
                            anchors.fill: parent; z: 2
                            enabled: !!artistName.text; hoverEnabled: enabled
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: browseState.openArtist(modelData)
                        }
                    }
                    Text { text: index < root.artistItems.length - 1 ? " • " : ""; color: themeState.secondary; font.pixelSize: 14 }
                }
            }
            Text {
                visible: !root.showArtwork && !root.tableLayout && !!root.media.views
                text: root.media.views + " plays"; textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 14
            }
        }
        Item {
            id: albumMetadata
            objectName: "songAlbumMetadata-" + (root.media.videoId || root.media.id || "")
            width: parent.width
            height: 18
            visible: root.showArtwork && !root.tableLayout && !!(root.media.album && root.media.album.name)
            clip: true
            Text {
                id: albumName
                width: Math.min(implicitWidth, parent.width)
                height: parent.height
                text: root.media.album ? root.media.album.name || "" : ""
                textFormat: Text.PlainText; elide: Text.ElideRight
                color: albumMetadataLink.containsMouse || activeFocus ? themeState.foreground : themeState.secondary
                font.pixelSize: 14
                font.underline: albumMetadataLink.containsMouse || activeFocus
                activeFocusOnTab: !!(root.media.album && (root.media.album.id || root.media.album.browseId))
                Accessible.role: activeFocusOnTab ? Accessible.Link : Accessible.StaticText
                Accessible.onPressAction: openAlbum()
                Keys.onReturnPressed: openAlbum()
                Keys.onSpacePressed: openAlbum()
                function openAlbum() {
                    var album = root.media.album || ({})
                    var id = album.id || album.browseId
                    if (id) browseState.open({kind: "album", id: id, title: album.name})
                }
                MouseArea {
                    id: albumMetadataLink
                    anchors.fill: parent; z: 2
                    enabled: !!(root.media.album && (root.media.album.id || root.media.album.browseId)); hoverEnabled: enabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: albumName.openAlbum()
                }
            }
        }
    }
    Text {
        id: albumColumn
        x: parent.width * 0.56; width: Math.min(implicitWidth, parent.width * 0.44 - 120); anchors.verticalCenter: parent.verticalCenter; visible: root.showAlbum; text: root.media.album ? root.media.album.name || "" : ""; textFormat: Text.PlainText; elide: Text.ElideRight; color: albumColumnLink.containsMouse || activeFocus ? themeState.foreground : themeState.secondary; font.pixelSize: 13
        font.underline: albumColumnLink.containsMouse || activeFocus
        activeFocusOnTab: !!(root.media.album && (root.media.album.id || root.media.album.browseId))
        Accessible.role: activeFocusOnTab ? Accessible.Link : Accessible.StaticText
        Accessible.onPressAction: openAlbum()
        Keys.onReturnPressed: openAlbum()
        Keys.onSpacePressed: openAlbum()
        function openAlbum() { var album = root.media.album || ({}); var id = album.id || album.browseId; if (id) browseState.open({kind: "album", id: id, title: album.name}) }
        MouseArea { id: albumColumnLink; anchors.fill: parent; z: 2; enabled: !!(root.media.album && (root.media.album.id || root.media.album.browseId)); hoverEnabled: enabled; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: albumColumn.openAlbum() }
    }
    Text { anchors.right: parent.right; anchors.rightMargin: 56; anchors.verticalCenter: parent.verticalCenter; visible: root.showDuration; text: root.media.duration ? Theme.timeLabel(root.media.duration) : "–"; color: themeState.secondary; font.pixelSize: 13 }
    HoverHandler { id: hover }
    MouseArea { z: -1; anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton; cursorShape: Qt.PointingHandCursor; onClicked: function(mouse) { if (mouse.button === Qt.RightButton) root.menuRequested(root.media); else root.activateSong() } }
    Item {
        id: reorderRegion
        width: Math.max(0, root.width - (root.queueRow ? 68 : 104))
        height: root.height
        opacity: 0
        DragHandler {
            parent: reorderRegion
            enabled: root.reorderable
            target: null
            property point lastPosition: Qt.point(0, 0)
            onCentroidChanged: if (active) { lastPosition = centroid.scenePosition; root.reorderDragMoved(lastPosition.x, lastPosition.y) }
            onActiveChanged: {
                if (active) { lastPosition = centroid.scenePosition; root.reorderDragStarted(lastPosition.x, lastPosition.y) }
                else root.reorderDragFinished(lastPosition.x, lastPosition.y)
            }
        }
    }
    DownloadButton {
        id: downloadButton
        objectName: root.queueRow ? "queueRowDownload-" + (root.media.key || "") : ""
        width: root.queueRow ? 32 : implicitWidth
        anchors.right: parent.right; anchors.rightMargin: root.queueRow ? 32 : 56; anchors.verticalCenter: parent.verticalCenter
        visible: hover.hovered || downloadButton.activeFocus || downloadButton.status === "complete" || downloadButton.status === "ready" || downloadButton.status === "downloading" || downloadButton.status === "queued"
        background: Rectangle {
            radius: width / 2
            color: root.queueRow ? "transparent" : parent.down ? themeState.border : parent.hovered ? themeState.hover : "transparent"
            border.width: !root.queueRow && parent.visualFocus ? 2 : 0
            border.color: themeState.accent
        }
        media: ({kind: "song", id: root.media.videoId || root.media.id || "", videoId: root.media.videoId || "", title: root.media.title || "", thumbnail: root.media.thumbnail || ""})
    }
    IconButton {
        width: root.queueRow ? 32 : implicitWidth
        objectName: root.queueRow ? "queueRowMore-" + (root.media.videoId || root.media.id || "") : ""
        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
        iconName: "more"; tip: "More options for " + (root.media.title || "song")
        visible: hover.hovered || root.activeFocus
        background: Rectangle {
            radius: width / 2
            color: root.queueRow ? "transparent" : parent.down ? themeState.border : parent.hovered ? themeState.hover : "transparent"
            border.width: !root.queueRow && parent.visualFocus ? 2 : 0
            border.color: themeState.accent
        }
        onClicked: root.menuRequested(root.media)
    }
}
