import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

Item {
    id: root
    objectName: "collectionPane"
    property bool playlist: catalogState.route === "playlist"
    // Do not incubate delegates for another route while the page is being replaced.
    property var album: (catalogState.route === "album" || catalogState.route === "playlist") ? catalogState.data : ({})
    property real margin: Theme.gutter(width)
    property bool compact: width < 1000
    property bool descriptionExpanded: false
    property string durationLabel: {
        var minutes = Math.floor((album.duration || 0) / 60)
        var hours = Math.floor(minutes / 60)
        return (hours ? hours + " hr " : "") + (minutes % 60) + " min"
    }
    ListView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: songs
        objectName: "collectionSongs"
        anchors.fill: parent; clip: true; bottomMargin: 24
        model: root.album.items || []
        ScrollBar.vertical: ScrollBar {}
        header: Column {
            width: songs.width
            Item {
                id: hero
                objectName: "collectionHero"
                width: parent.width
                height: Math.max(root.compact ? 200 : 300, summary.implicitHeight + 40)
                ArtworkBackdrop { anchors.fill: parent; source: root.album.thumbnail || ""; mediaKey: catalogState.route + ":" + (catalogState.parameters.id || "") }
                Cover {
                    id: cover
                    x: root.margin; anchors.verticalCenter: parent.verticalCenter
                    width: root.compact ? 144 : 216; height: width; radius: 12
                    source: root.album.thumbnail || ""; mediaKey: catalogState.route + ":" + (catalogState.parameters.id || ""); accent: themeState.selected
                }
                Column {
                    id: summary
                    x: cover.x + cover.width + 28; width: parent.width - x - root.margin
                    anchors.verticalCenter: parent.verticalCenter; spacing: 10
                    Text { text: root.playlist ? root.album.privacy === "PRIVATE" ? "PRIVATE PLAYLIST" : "PLAYLIST" : "ALBUM"; color: themeState.accent; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1 }
                    Text { width: parent.width; text: root.album.title || (root.playlist ? "Playlist" : "Album"); textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; color: themeState.foreground; font.pixelSize: root.compact ? 32 : 48; font.bold: true }
                    Text { id: description; objectName: "collectionDescription"; width: parent.width; visible: !!root.album.subtitle; text: root.album.subtitle || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: root.descriptionExpanded ? 1000 : 2; elide: Text.ElideRight; color: themeState.secondary; font.pixelSize: 14 }
                    Button { objectName: "descriptionToggle"; visible: description.truncated || root.descriptionExpanded; text: root.descriptionExpanded ? "Less" : "More"; flat: true; height: 28; leftPadding: 0; onClicked: root.descriptionExpanded = !root.descriptionExpanded }
                    Text { width: parent.width; visible: root.playlist; text: root.album.author || "YouTube Music"; textFormat: Text.PlainText; color: themeState.foreground; elide: Text.ElideRight; font.pixelSize: 14; font.bold: true }
                    Button { id: artist; width: parent.width; visible: !root.playlist; text: root.album.artists && root.album.artists.length ? root.album.artists[0].name : "Artist"; flat: true; height: 28; leftPadding: 0; contentItem: Text { text: artist.text; textFormat: Text.PlainText; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; color: themeState.foreground; font.pixelSize: 14; font.bold: true } enabled: !!(root.album.artists && root.album.artists.length && root.album.artists[0].id); onClicked: browseState.open({kind: "artist", id: root.album.artists[0].id, title: text}) }
                    Text { width: parent.width; text: (root.album.year ? root.album.year + " · " : "") + (root.album.trackCount || (root.album.items || []).length) + " songs" + (root.album.duration ? " · " + root.durationLabel : ""); color: themeState.secondary; font.pixelSize: 13; wrapMode: Text.Wrap }
                }
            }
            Row {
                x: root.margin; spacing: 12; height: 80
                Button { id: play; anchors.verticalCenter: parent.verticalCenter; width: 56; height: 56; padding: 14; enabled: (root.album.items || []).length > 0; Accessible.name: root.playlist ? "Play playlist" : "Play album"; background: Rectangle { radius: 16; color: play.hovered ? themeState.accentHover : themeState.accent; border.width: play.visualFocus ? 2 : 0; border.color: themeState.foreground } contentItem: Symbol { name: "play"; color: themeState.onAccent } onClicked: browseState.playView() }
                DownloadButton { anchors.verticalCenter: parent.verticalCenter; media: ({kind: root.playlist ? "playlist" : "album", id: catalogState.parameters.id || "", title: root.album.title || "", thumbnail: root.album.thumbnail || ""}) }
                IconButton { anchors.verticalCenter: parent.verticalCenter; visible: !root.playlist || !root.album.editable; iconName: "library"; tip: root.album.saved ? "Remove from Library" : "Add to Library"; iconColor: root.album.saved ? themeState.accent : themeState.secondary; enabled: !actionsState.busy && (accountState.connected || appState.fixtureMode) && (root.playlist || !!root.album.audioPlaylistId); onClicked: actionsState.set(root.playlist ? "playlist_library" : "album_library", root.playlist ? catalogState.parameters.id : root.album.audioPlaylistId, !root.album.saved, catalogState.parameters.id) }
                IconButton { anchors.verticalCenter: parent.verticalCenter; visible: root.playlist && !!root.album.editable; iconName: "edit"; tip: "Rename Playlist"; enabled: !actionsState.busy && (accountState.connected || appState.fixtureMode); onClicked: libraryState.edit("playlist_rename", {id: catalogState.parameters.id, title: root.album.title}) }
                IconButton { anchors.verticalCenter: parent.verticalCenter; iconName: "shuffle"; tip: root.playlist ? "Shuffle Playlist" : "Shuffle Album"; enabled: (root.album.items || []).length > 0; onClicked: browseState.shuffleView() }
                IconButton { anchors.verticalCenter: parent.verticalCenter; iconName: "more"; tip: root.playlist ? "Playlist Options" : "Album Options"; onClicked: appState.showMenu({kind: root.playlist ? "playlist" : "album", id: catalogState.parameters.id, title: root.album.title, owned: root.playlist && !!root.album.editable}, {}) }
            }
            Text { x: root.margin; width: parent.width - 2 * root.margin; text: actionsState.message || downloadsState.message || ""; visible: !!text; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 14; bottomPadding: 12 }
            Item {
                width: parent.width; height: 40
                Rectangle { anchors.bottom: parent.bottom; x: root.margin; width: parent.width - 2 * root.margin; height: 1; color: themeState.border }
                Text { x: root.margin + 12; anchors.verticalCenter: parent.verticalCenter; text: "#"; color: themeState.secondary; font.pixelSize: 12 }
                Text { x: root.margin + (root.playlist ? 100 : 48); anchors.verticalCenter: parent.verticalCenter; text: "TITLE"; color: themeState.secondary; font.pixelSize: 12; font.letterSpacing: 1 }
                Text { x: root.margin + (parent.width - 2 * root.margin) * 0.56; anchors.verticalCenter: parent.verticalCenter; visible: root.playlist && !root.compact; text: "ALBUM"; color: themeState.secondary; font.pixelSize: 12; font.letterSpacing: 1 }
                Text { anchors.right: parent.right; anchors.rightMargin: root.margin + 56; anchors.verticalCenter: parent.verticalCenter; text: "TIME"; color: themeState.secondary; font.pixelSize: 12 }
            }
        }
        delegate: Item {
            required property int index
            required property var modelData
            width: songs.width; height: 64
            SongRow {
                x: root.margin; width: parent.width - 2 * root.margin; height: parent.height
                showArtwork: root.playlist; showDuration: true; tableLayout: true; showAlbum: root.playlist && !root.compact
                menuContext: ({playlistId: root.playlist ? catalogState.parameters.id : "", index: parent.index})
                media: parent.modelData; number: parent.index + 1; onActivated: browseState.playAt(parent.index)
            }
        }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        onAtYEndChanged: if (atYEnd && root.album.cursor !== undefined && root.album.cursor !== null && !catalogState.busy) catalogState.more()
        footer: Column {
            width: songs.width
            Text { width: parent.width; padding: 24; text: "Add songs from a song’s menu."; visible: root.playlist && !catalogState.busy && !catalogState.error && !(root.album.items || []).length; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; color: themeState.secondary; font.pixelSize: 16 }
            Button { text: "Load More"; visible: root.album.cursor !== undefined && root.album.cursor !== null; enabled: !catalogState.busy; onClicked: catalogState.more() }
        }
    }
    BusyIndicator { anchors.centerIn: parent; running: catalogState.busy; visible: running && !(root.album.items || []).length }
    RetryBanner { message: catalogState.error; busy: catalogState.busy; onRetry: catalogState.refresh() }
    property int revision: -1
    function restoreScroll() {
        if (catalogState.busy || revision === catalogState.revision) return
        revision = catalogState.revision
        Qt.callLater(function() { if (catalogState.hasScrollPosition) songs.contentY = catalogState.scrollPosition; else songs.positionViewAtBeginning() })
    }
    Component.onCompleted: restoreScroll()
    Connections { target: catalogState; function onChanged() { root.restoreScroll() } }
}
