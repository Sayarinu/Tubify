import QtQuick
import QtQuick.Controls

Menu {
    id: root
    objectName: "mediaMenu"
    property var media: ({})
    property var context: ({})
    property bool song: media.kind === "song" || !!media.videoId
    property bool canEdit: (accountState.connected || appState.fixtureMode) && !accountState.busy && !actionsState.busy
    property bool playlistEntry: song && !!media.setVideoId && catalogState.route === "playlist" && catalogState.data.editable && context.playlistId === catalogState.parameters.id
    MenuItem { text: "Play"; onTriggered: browseState.play(root.media) }
    MenuItem { text: "Play next"; visible: root.song; height: visible ? implicitHeight : 0; onTriggered: playerState.enqueue([root.media], true) }
    MenuItem { text: "Add to queue"; visible: root.song; height: visible ? implicitHeight : 0; onTriggered: playerState.enqueue([root.media], false) }
    MenuItem { text: "Start radio"; visible: root.song; height: visible ? implicitHeight : 0; onTriggered: browseState.startRadioForSong(root.media.videoId || root.media.id) }
    MenuSeparator { visible: root.song; height: visible ? implicitHeight : 0 }
    MenuItem { text: root.media.rating === "LIKE" ? "Remove like" : "Like"; visible: root.song; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.rate(root.media, "LIKE") }
    MenuItem { text: root.media.rating === "DISLIKE" ? "Remove dislike" : "Dislike"; visible: root.song; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.rate(root.media, "DISLIKE") }
    MenuItem { text: root.media.inLibrary ? "Remove from library" : "Save to library"; visible: root.song; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.saveSong(root.media) }
    MenuItem { text: "Add to playlist"; visible: root.song; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.choosePlaylist(root.media) }
    MenuItem { text: "Download"; visible: root.media.kind !== "artist"; height: visible ? implicitHeight : 0; onTriggered: downloadsState.download(root.media) }
    MenuItem { text: "Go to album"; visible: root.song && !!(root.media.album && root.media.album.id); height: visible ? implicitHeight : 0; onTriggered: browseState.open({kind: "album", id: root.media.album.id}) }
    MenuItem { text: "Go to artist"; visible: root.song && !!(root.media.artists && root.media.artists.length && root.media.artists[0].id); height: visible ? implicitHeight : 0; onTriggered: browseState.open({kind: "artist", id: root.media.artists[0].id}) }
    MenuSeparator { visible: root.playlistEntry || (root.media.kind === "playlist" && root.media.owned); height: visible ? implicitHeight : 0 }
    MenuItem { text: "Remove from playlist"; visible: root.playlistEntry; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.removeEntry(root.media) }
    MenuItem { text: "Move up"; visible: root.playlistEntry; height: visible ? implicitHeight : 0; enabled: root.canEdit && !catalogState.busy && root.context.index > 0; onTriggered: libraryState.moveEntry(root.media, -1) }
    MenuItem { text: "Move down"; visible: root.playlistEntry; height: visible ? implicitHeight : 0; enabled: root.canEdit && !catalogState.busy && (root.context.index + 1 < (catalogState.data.items || []).length || catalogState.data.cursor !== undefined && catalogState.data.cursor !== null); onTriggered: libraryState.moveEntry(root.media, 1) }
    MenuItem { text: "Rename playlist"; visible: root.media.kind === "playlist" && root.media.owned; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.edit("playlist_rename", root.media) }
    MenuItem { text: "Delete playlist"; visible: root.media.kind === "playlist" && root.media.owned; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.edit("playlist_delete", root.media) }
}
