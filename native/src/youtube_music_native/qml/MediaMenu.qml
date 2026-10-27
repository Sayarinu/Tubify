import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

ThemedMenu {
    id: root
    objectName: "mediaMenu"
    property var media: ({})
    property var context: ({})
    property bool song: media.kind === "song" || !!media.videoId
    property bool queueable: song || media.kind === "album" || media.kind === "playlist"
    property bool canEdit: (accountState.connected || appState.fixtureMode) && !accountState.busy && !actionsState.busy
    property bool playlistEntry: song && !!media.setVideoId && catalogState.route === "playlist" && catalogState.data.editable && context.playlistId === catalogState.parameters.id
    ContextMenuItem { text: "Play"; onTriggered: { if (root.context.queueKey) playerState.selectKey(root.context.queueKey); else browseState.play(root.media) } }
    ContextMenuItem { text: "Play Next"; visible: root.queueable; height: visible ? implicitHeight : 0; onTriggered: browseState.enqueue(root.media, true) }
    ContextMenuItem { text: "Add to Queue"; visible: root.queueable; height: visible ? implicitHeight : 0; onTriggered: browseState.enqueue(root.media, false) }
    ContextMenuItem { text: "Start Radio"; visible: root.song; height: visible ? implicitHeight : 0; onTriggered: browseState.startRadioForSong(root.media.videoId || root.media.id) }
    ThemedMenuSeparator { visible: root.song; height: visible ? implicitHeight : 0 }
    ContextMenuItem { text: root.media.rating === "LIKE" ? "Remove Like" : "Like"; visible: root.song; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.rate(root.media, "LIKE") }
    ContextMenuItem { text: root.media.rating === "DISLIKE" ? "Remove Dislike" : "Dislike"; visible: root.song; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.rate(root.media, "DISLIKE") }
    ContextMenuItem { text: root.media.inLibrary ? "Remove from Library" : "Save to Library"; visible: root.song; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.saveSong(root.media) }
    ContextMenuItem { text: "Add to Playlist"; visible: root.song; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.choosePlaylist(root.media) }
    ContextMenuItem { text: "Download"; visible: root.media.kind !== "artist"; height: visible ? implicitHeight : 0; onTriggered: downloadsState.download(root.media) }
    ContextMenuItem { text: "Go to Album"; visible: root.song && !!(root.media.album && root.media.album.id); height: visible ? implicitHeight : 0; onTriggered: browseState.open({kind: "album", id: root.media.album.id}) }
    ContextMenuItem { text: "Go to Artist"; visible: root.song && !!(root.media.artists && root.media.artists.length && root.media.artists[0].id); height: visible ? implicitHeight : 0; onTriggered: browseState.open({kind: "artist", id: root.media.artists[0].id}) }
    ThemedMenuSeparator { visible: root.playlistEntry || (root.media.kind === "playlist" && root.media.owned); height: visible ? implicitHeight : 0 }
    ContextMenuItem { text: "Remove from Playlist"; visible: root.playlistEntry; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.removeEntry(root.media) }
    ContextMenuItem { text: "Move Up"; visible: root.playlistEntry; height: visible ? implicitHeight : 0; enabled: root.canEdit && !catalogState.busy && root.context.index > 0; onTriggered: libraryState.moveEntry(root.media, -1) }
    ContextMenuItem { text: "Move Down"; visible: root.playlistEntry; height: visible ? implicitHeight : 0; enabled: root.canEdit && !catalogState.busy && (root.context.index + 1 < (catalogState.data.items || []).length || catalogState.data.cursor !== undefined && catalogState.data.cursor !== null); onTriggered: libraryState.moveEntry(root.media, 1) }
    ContextMenuItem { text: "Rename Playlist"; visible: root.media.kind === "playlist" && root.media.owned; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.edit("playlist_rename", root.media) }
    ContextMenuItem { text: "Delete Playlist"; visible: root.media.kind === "playlist" && root.media.owned; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.edit("playlist_delete", root.media) }
    ThemedMenuSeparator { visible: !!root.context.queueKey; height: visible ? implicitHeight : 0 }
    ContextMenuItem { text: "Remove from Queue"; visible: !!root.context.queueKey; height: visible ? implicitHeight : 0; onTriggered: playerState.removeKey(root.context.queueKey) }
    ContextMenuItem { text: "Move Up in Queue"; visible: !!root.context.queueKey && !!root.media.movable; height: visible ? implicitHeight : 0; onTriggered: playerState.moveKey(root.context.queueKey, -1) }
    ContextMenuItem { text: "Move Down in Queue"; visible: !!root.context.queueKey && !!root.media.movable; height: visible ? implicitHeight : 0; onTriggered: playerState.moveKey(root.context.queueKey, 1) }
}
