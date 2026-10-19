import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    objectName: "collectionPane"
    property bool playlist: catalogState.route === "playlist"
    property var album: catalogState.data
    property real margin: width > 900 ? 40 : 24
    property real leftWidth: Math.min(390, width * 0.42)
    property string durationLabel: {
        var minutes = Math.floor((album.duration || 0) / 60)
        var hours = Math.floor(minutes / 60)
        return minutes >= 60 ? hours + (hours === 1 ? " hour, " : " hours, ") + (minutes % 60) + " minutes" : minutes + " minutes"
    }
    Rectangle { width: parent.width; height: 342; z: -1; gradient: Gradient { GradientStop { position: 0; color: "#343434" } GradientStop { position: 1; color: Theme.background } } }
    IconButton { x: 8; y: 12; iconName: "left"; tip: "Back"; onClicked: browseState.back() }
    ScrollView {
        id: summary
        x: root.margin; y: 64; width: root.leftWidth; height: parent.height - 80
        clip: true
        Column {
            width: summary.width; spacing: 0
            Text { anchors.horizontalCenter: parent.horizontalCenter; height: 16; visible: root.playlist; text: root.album.author || "YouTube Music"; textFormat: Text.PlainText; color: "white"; font.pixelSize: 14 }
            Button { id: artist; anchors.horizontalCenter: parent.horizontalCenter; height: 16; topPadding: 0; bottomPadding: 0; visible: !root.playlist; text: root.album.artists && root.album.artists.length ? root.album.artists[0].name : "Artist"; flat: true; palette.windowText: Theme.foreground; contentItem: Text { text: artist.text; textFormat: Text.PlainText; color: "white"; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter } enabled: !!(root.album.artists && root.album.artists.length && root.album.artists[0].id); onClicked: browseState.open({kind: "artist", id: root.album.artists[0].id, title: text}) }
            Item { width: 1; height: 16 }
            Cover { anchors.horizontalCenter: parent.horizontalCenter; width: Math.min(240, parent.width - 32, Math.max(128, root.height - 350)); height: width; source: root.album.thumbnail || ""; mediaKey: catalogState.route + ":" + (catalogState.parameters.id || "") }
            Item { width: 1; height: 16 }
            Text { width: parent.width; text: root.album.title || (root.playlist ? "Playlist" : "Album"); textFormat: Text.PlainText; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; color: "white"; font.family: Theme.headingFont; font.pixelSize: 28; font.bold: true }
            Item { width: 1; height: 8 }
            Text { width: parent.width; text: (root.playlist ? "Playlist" + (root.album.privacy === "PRIVATE" ? " · Private" : "") : "Album") + (root.album.year ? " · " + root.album.year : "") + "\n" + (root.album.trackCount || (root.album.items || []).length) + " songs" + (root.album.duration ? " · " + root.durationLabel : ""); color: Theme.secondary; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 14 }
            Item { width: 1; height: 16 }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter; spacing: root.playlist ? 8 : 12
                DownloadButton { anchors.verticalCenter: parent.verticalCenter; media: ({kind: root.playlist ? "playlist" : "album", id: catalogState.parameters.id || "", title: root.album.title || "", thumbnail: root.album.thumbnail || ""}) }
                IconButton { anchors.verticalCenter: parent.verticalCenter; visible: !root.playlist || !root.album.editable; iconName: "library"; tip: root.album.saved ? "Remove from library" : "Add to library"; iconColor: root.album.saved ? "white" : Theme.secondary; enabled: !actionsState.busy && (accountState.connected || appState.fixtureMode) && (root.playlist || !!root.album.audioPlaylistId); onClicked: actionsState.set(root.playlist ? "playlist_library" : "album_library", root.playlist ? catalogState.parameters.id : root.album.audioPlaylistId, !root.album.saved, catalogState.parameters.id) }
                IconButton { anchors.verticalCenter: parent.verticalCenter; visible: root.playlist && !!root.album.editable; iconName: "edit"; tip: "Rename playlist"; enabled: !actionsState.busy && (accountState.connected || appState.fixtureMode); onClicked: libraryState.edit("playlist_rename", {id: catalogState.parameters.id, title: root.album.title}) }
                Button { id: play; width: 64; height: 64; padding: 16; enabled: (root.album.items || []).length > 0; Accessible.name: root.playlist ? "Play playlist" : "Play album"; background: Rectangle { radius: 32; color: play.hovered ? "#dddddd" : "white" } contentItem: Symbol { name: "play"; color: "black" } onClicked: browseState.playView() }
                IconButton { anchors.verticalCenter: parent.verticalCenter; iconName: "shuffle"; tip: root.playlist ? "Shuffle playlist" : "Shuffle album"; enabled: (root.album.items || []).length > 0; onClicked: browseState.shuffleView() }
                IconButton { anchors.verticalCenter: parent.verticalCenter; visible: root.playlist; iconName: "more"; tip: "Playlist options"; onClicked: appState.showMenu({kind: "playlist", id: catalogState.parameters.id, title: root.album.title, owned: !!root.album.editable}, {}) }
            }
            Item { width: 1; height: 16 }
            Text { width: parent.width; text: actionsState.message || downloadsState.message || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.secondary; font.pixelSize: 14 }
        }
    }
    ListView {
        id: songs
        anchors.left: summary.right; anchors.leftMargin: 8
        anchors.right: parent.right; anchors.rightMargin: root.width > 900 ? 80 : 24
        anchors.top: parent.top; anchors.topMargin: 56; anchors.bottom: parent.bottom
        clip: true; bottomMargin: 32; model: root.album.items || []
        ScrollBar.vertical: ScrollBar {}
        delegate: SongRow { required property int index; required property var modelData; width: songs.width; height: root.playlist ? 64 : 76; showArtwork: root.playlist; showDuration: true; menuContext: ({playlistId: root.playlist ? catalogState.parameters.id : "", index: index}); media: modelData; number: index + 1; onActivated: browseState.playAt(index) }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        onAtYEndChanged: if (atYEnd && root.album.cursor !== undefined && root.album.cursor !== null && !catalogState.busy) catalogState.more()
        footer: Button { text: "Load more"; visible: root.album.cursor !== undefined && root.album.cursor !== null; enabled: !catalogState.busy; onClicked: catalogState.more() }
    }
    BusyIndicator { anchors.centerIn: parent; running: catalogState.busy; visible: running && !(root.album.items || []).length }
    Text { anchors.centerIn: songs; width: songs.width - 32; text: "Add songs from a song’s menu."; visible: root.playlist && !catalogState.busy && !catalogState.error && !(root.album.items || []).length; textFormat: Text.PlainText; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; color: Theme.secondary; font.pixelSize: 16 }
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
