import QtQuick
import "../Theme.js" as Theme

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
    // Duration and hover actions share the trailing edge: More, then the time column, then Download.
    readonly property real durationRight: 56
    readonly property real durationWidth: 48
    // A hovered parent can hold the actions open while the pointer is on its own controls beside the row.
    property bool actionsHeld: false
    readonly property bool actionsShown: hover.hovered || actionsHeld
    // Queue text only gives up the actions' space while they show, or while a download indicator stays in it.
    readonly property real trailingWidth: queueRow ? (actionsShown || root.activeFocus || downloadButton.visible || localSong ? 68 : 0) : showDuration ? durationRight + durationWidth + 8 + 44 + 4 : 104
    property string downloadStatus: { downloadsState.revision; return downloadsState.songState(media.videoId || media.id || "") || media.downloadState || "" }
    readonly property bool currentSong: playerState.hasTrack && (queueRow && media.key ? !!media.current : (media.videoId || media.id) === (playerState.currentTrack.videoId || playerState.currentTrack.id))
    // A Local Music song plays from its file and has no YouTube Music download, radio or links.
    readonly property bool localSong: String(media.videoId || "").indexOf("local:") === 0
    readonly property bool albumLinked: !!(media.album && (media.album.id || media.album.browseId))
    function openAlbum() { browseState.open({kind: "album", id: media.album.id || media.album.browseId, title: media.album.name}) }
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
    Accessible.description: localSong ? (media.available === false ? "Local file, unavailable" : "Local file") : downloadStatus === "ready" ? "Downloaded" : downloadStatus === "damaged" || downloadStatus === "missing" ? "Download needs repair" : downloadStatus === "downloading" || downloadStatus === "queued" ? "Downloading" : ""
    Accessible.onPressAction: activateSong()
    Keys.onReturnPressed: activateSong()
    function activateSong() { if (root.currentSong) playerState.togglePlayback(); else root.activated(root.media) }
    Keys.onPressed: event => { if (event.key === Qt.Key_Menu || event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier) { root.menuRequested(root.media); event.accepted = true } }
    // A translucent foreground wash reads on artwork backdrops and on light and dark themes alike.
    Rectangle { anchors.fill: parent; radius: Theme.radiusSmall; color: Qt.alpha(themeState.foreground, !root.queueRow && hover.hovered ? 0.1 : 0); border.color: root.activeFocus && !root.queueRow ? themeState.accent : "transparent"; border.width: 1; Behavior on color { enabled: !appState.reducedMotion; ColorAnimation { duration: Theme.motionFast } } }
    Cover {
        id: art
        objectName: root.queueRow ? "queueRowArtwork-" + (root.media.key || root.media.videoId || root.media.id || "") : ""
        visible: root.showArtwork
        x: root.queueRow ? 0 : root.tableLayout ? 44 : 8; anchors.verticalCenter: parent.verticalCenter
        width: root.tableLayout ? 40 : 48; height: width
        radius: root.media.kind === "artist" ? width / 2 : root.queueRow ? 4 : 6
        placeholder: root.media.kind === "artist" ? "profile" : "music"
        source: root.media.thumbnail || ""; mediaKey: root.media.videoId || root.media.id || ""; accent: root.media.accent || themeState.selected
        Rectangle { anchors.centerIn: parent; width: root.queueRow ? parent.width : 28; height: root.queueRow ? parent.height : 28; radius: root.queueRow ? parent.radius : 14; color: root.queueRow ? Qt.rgba(0, 0, 0, 0.55) : themeState.accent; visible: root.media.kind !== "artist" && (hover.hovered || root.activeFocus) }
        Symbol { anchors.centerIn: parent; name: root.currentSong && playerState.playing ? "pause" : "play"; width: root.queueRow ? 18 : 14; height: width; color: root.queueRow ? "white" : themeState.onAccent; visible: root.media.kind !== "artist" && (hover.hovered || root.activeFocus) }
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
    Text { id: rank; x: root.tableLayout ? 12 : root.showArtwork ? 68 : 16; width: root.number > 0 ? 28 : 0; visible: root.number > 0; anchors.verticalCenter: parent.verticalCenter; text: root.number; color: themeState.secondary; font.pixelSize: Theme.textBody }
    Column {
        objectName: root.queueRow ? "queueRowMetadata-" + (root.media.key || "") : ""
        x: root.queueRow ? 60 : root.tableLayout ? root.showArtwork ? 100 : 48 : root.showArtwork ? root.number > 0 ? 104 : 72 : 56
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, (root.showAlbum ? parent.width * 0.54 : parent.width - root.trailingWidth) - x); spacing: 3
        opacity: root.media.available === false ? 0.5 : 1
        Text { width: parent.width; text: root.media.title || "Unavailable song"; textFormat: Text.PlainText; elide: Text.ElideRight; color: root.queueRow && root.currentSong ? themeState.accent : themeState.foreground; font.pixelSize: Theme.textBody }
        Row {
            id: metadata
            width: parent.width; height: 18; spacing: 4; clip: true
            Text {
                id: metadataLabel
                visible: root.showArtwork && !!(root.media.label || root.media.kind && root.media.kind !== "song")
                text: root.media.label || (root.media.kind && root.media.kind !== "song" ? root.media.kind.charAt(0).toUpperCase() + root.media.kind.slice(1) : "")
                textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: Theme.textBody
            }
            Repeater {
                model: root.tableLayout || root.showArtwork ? root.artistItems : []
                delegate: Row {
                    required property var modelData
                    required property int index
                    height: metadata.height; spacing: 0
                    InlineLink {
                        text: modelData.name || ""; font.pixelSize: Theme.textBody
                        linked: !!text && !root.localSong
                        onActivated: browseState.openArtist(modelData)
                    }
                    Text { text: index < root.artistItems.length - 1 ? " • " : ""; color: themeState.secondary; font.pixelSize: Theme.textBody }
                }
            }
            Text {
                visible: !root.showArtwork && !root.tableLayout && !!root.media.views
                text: root.media.views + " plays"; textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: Theme.textBody
            }
        }
        Item {
            id: albumMetadata
            objectName: "songAlbumMetadata-" + (root.media.videoId || root.media.id || "")
            width: parent.width
            height: 18
            visible: root.showArtwork && !root.tableLayout && !root.queueRow && !!(root.media.album && root.media.album.name)
            clip: true
            InlineLink {
                width: Math.min(implicitWidth, parent.width)
                height: parent.height
                text: root.media.album ? root.media.album.name || "" : ""
                elide: Text.ElideRight; font.pixelSize: Theme.textBody
                linked: root.albumLinked
                onActivated: root.openAlbum()
            }
        }
    }
    InlineLink {
        x: parent.width * 0.56; width: Math.max(0, Math.min(implicitWidth, parent.width * 0.44 - root.trailingWidth)); anchors.verticalCenter: parent.verticalCenter; visible: root.showAlbum; text: root.media.album ? root.media.album.name || "" : ""; elide: Text.ElideRight; font.pixelSize: 13
        linked: root.albumLinked
        onActivated: root.openAlbum()
    }
    // Fixed and right-aligned so times line up with each other and the TIME column header.
    Text { id: durationLabel; objectName: "songDuration"; anchors.right: parent.right; anchors.rightMargin: root.durationRight; anchors.verticalCenter: parent.verticalCenter; width: root.durationWidth; horizontalAlignment: Text.AlignRight; visible: root.showDuration; text: root.media.duration ? Theme.timeLabel(root.media.duration) : "–"; color: themeState.secondary; font.pixelSize: 13 }
    HoverHandler { id: hover }
    // Resolve a hovered or focused song shortly before a likely click.
    readonly property bool warmWanted: (hover.hovered || root.activeFocus) && !!(root.media.videoId)
    onWarmWantedChanged: warmWanted ? warmTimer.restart() : warmTimer.stop()
    Timer {
        id: warmTimer
        interval: 200
        onTriggered: if (root.warmWanted && !root.currentSong && root.downloadStatus !== "ready" && typeof playerState.warm === "function") playerState.warm(root.media)
    }
    MouseArea { z: -1; anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton; cursorShape: Qt.PointingHandCursor; onClicked: function(mouse) { if (mouse.button === Qt.RightButton) root.menuRequested(root.media); else root.activateSong() } }
    Item {
        id: reorderRegion
        width: Math.max(0, root.width - root.trailingWidth)
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
        objectName: root.queueRow ? "queueRowDownload-" + (root.media.key || "") : "songDownload"
        width: root.queueRow ? 32 : implicitWidth
        // Beside the duration, never on top of it; queue and plain rows keep their slot left of More.
        anchors.right: root.showDuration && !root.queueRow ? durationLabel.left : parent.right
        anchors.rightMargin: root.queueRow ? 32 : root.showDuration ? 8 : 56
        anchors.verticalCenter: parent.verticalCenter
        visible: !root.localSong && (root.actionsShown || downloadButton.activeFocus || downloadButton.status === "complete" || downloadButton.status === "ready" || downloadButton.status === "downloading" || downloadButton.status === "queued")
        quiet: root.queueRow
        media: ({kind: "song", id: root.media.videoId || root.media.id || "", videoId: root.media.videoId || "", title: root.media.title || "", thumbnail: root.media.thumbnail || ""})
    }
    // Where a download indicator would be, a local song shows that it plays from a file.
    Symbol {
        objectName: "localFileMark"
        anchors.horizontalCenter: downloadButton.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        width: 18; height: 18
        visible: root.localSong
        name: "folder"
        color: root.media.available === false ? themeState.muted : themeState.secondary
    }
    IconButton {
        width: root.queueRow ? 32 : implicitWidth
        objectName: root.queueRow ? "queueRowMore-" + (root.media.videoId || root.media.id || "") : ""
        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
        iconName: "more"; tip: "More options for " + (root.media.title || "song")
        visible: root.actionsShown || root.activeFocus
        quiet: root.queueRow
        onClicked: root.menuRequested(root.media)
    }
}
