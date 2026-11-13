import QtQuick
import QtQuick.Controls
import "../components"

ThemedMenu {
    id: root
    objectName: "mediaMenu"
    property var media: ({})
    property var context: ({})
    property bool song: media.kind === "song" || !!media.videoId
    // A Local Music song plays from its file; YouTube Music actions don't apply to it.
    readonly property bool localSong: String(media.videoId || "").indexOf("local:") === 0
    readonly property bool onlineSong: song && !localSong
    readonly property bool hasLocal: typeof localState !== "undefined"
    // Local Music albums, artists and folders are built from tags and folders, not YouTube Music.
    readonly property bool localCollection: !!media.local && !song
    readonly property bool localFolder: localCollection && media.kind === "folder"
    property bool queueable: !localCollection && (song || media.kind === "album" || media.kind === "playlist")
    property bool canEdit: (accountState.connected || appState.fixtureMode) && !accountState.busy && !actionsState.busy
    // Set on a Downloads card; a song's own download is found by its key.
    readonly property string downloadKey: context.downloadKey || ""
    readonly property var download: { downloadsState.revision; return downloadKey ? downloadsState.collectionEntry(downloadKey) : song ? downloadsState.collectionEntry("song:" + (media.videoId || media.id || "")) : ({}) }
    readonly property bool downloadActive: download.state === "queued" || download.state === "downloading"
    property bool playlistEntry: song && !!media.setVideoId && catalogState.route === "playlist" && catalogState.data.editable && context.playlistId === catalogState.parameters.id
    ContextMenuItem { text: "Play"; visible: !root.localCollection; height: visible ? implicitHeight : 0; onTriggered: { if (root.context.queueKey) playerState.selectKey(root.context.queueKey); else browseState.play(root.media) } }
    ContextMenuItem { text: "Play Next"; visible: root.queueable; height: visible ? implicitHeight : 0; onTriggered: browseState.enqueue(root.media, true) }
    ContextMenuItem { text: "Add to Queue"; visible: root.queueable; height: visible ? implicitHeight : 0; onTriggered: browseState.enqueue(root.media, false) }
    ContextMenuItem { objectName: "localPlay"; text: "Play"; visible: root.localCollection && !root.localFolder && root.hasLocal; height: visible ? implicitHeight : 0; onTriggered: localState.play(root.media.key, false) }
    ContextMenuItem { text: "Shuffle Play"; visible: root.localCollection && !root.localFolder && root.hasLocal; height: visible ? implicitHeight : 0; onTriggered: localState.play(root.media.key, true) }
    ContextMenuItem { text: "Play Next"; visible: root.localCollection && !root.localFolder && root.hasLocal; height: visible ? implicitHeight : 0; onTriggered: localState.enqueue(root.media.key, true) }
    ContextMenuItem { text: "Add to Queue"; visible: root.localCollection && !root.localFolder && root.hasLocal; height: visible ? implicitHeight : 0; onTriggered: localState.enqueue(root.media.key, false) }
    ContextMenuItem { objectName: "localFolderOpen"; text: "Open Folder"; visible: root.localFolder && root.hasLocal; height: visible ? implicitHeight : 0; onTriggered: localState.open(root.media.key) }
    ContextMenuItem { objectName: "localFolderRescan"; text: "Rescan"; visible: root.localFolder && root.hasLocal; height: visible ? implicitHeight : 0; enabled: root.hasLocal && !localState.scanning; onTriggered: localState.rescan(root.media.id) }
    ContextMenuItem { text: "Show in File Manager"; visible: root.localFolder && root.hasLocal; height: visible ? implicitHeight : 0; enabled: root.media.state !== "offline"; onTriggered: localState.showFolder(root.media.id) }
    ContextMenuItem { objectName: "localForgetMissing"; text: "Remove Missing Songs"; visible: root.localFolder && root.media.missing > 0 && root.hasLocal; height: visible ? implicitHeight : 0; onTriggered: localState.forgetMissing(root.media.id) }
    ThemedMenuSeparator { visible: root.localFolder; height: visible ? implicitHeight : 0 }
    ContextMenuItem { objectName: "localRemoveFolder"; text: "Remove Folder…"; visible: root.localFolder && root.hasLocal; height: visible ? implicitHeight : 0; onTriggered: localState.requestFolderRemoval(root.media.id) }
    ContextMenuItem { objectName: "continueOnPhone"; text: "Continue on Phone"; visible: !!root.context.nowPlaying && !root.localSong && typeof handoffState !== "undefined"; height: visible ? implicitHeight : 0; onTriggered: handoffState.open() }
    ContextMenuItem { text: "Start Radio"; visible: root.onlineSong; height: visible ? implicitHeight : 0; onTriggered: browseState.startRadioForSong(root.media.videoId || root.media.id) }
    ThemedMenuSeparator { visible: root.onlineSong; height: visible ? implicitHeight : 0 }
    ContextMenuItem { text: root.media.rating === "LIKE" ? "Remove Like" : "Like"; visible: root.onlineSong; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.rate(root.media, "LIKE") }
    ContextMenuItem { text: root.media.rating === "DISLIKE" ? "Remove Dislike" : "Dislike"; visible: root.onlineSong; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.rate(root.media, "DISLIKE") }
    ContextMenuItem { text: root.media.inLibrary ? "Remove from Library" : "Save to Library"; visible: root.onlineSong; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.saveSong(root.media) }
    ContextMenuItem { text: "Add to Playlist"; visible: root.onlineSong; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.choosePlaylist(root.media) }
    ContextMenuItem { text: "Download"; visible: root.media.kind !== "artist" && !root.localSong && !root.localCollection && !root.download.key; height: visible ? implicitHeight : 0; onTriggered: downloadsState.download(root.media) }
    // Saves this one item as audio files in the chosen folder, whichever download style is set.
    ContextMenuItem { objectName: "saveAudioFiles"; text: root.media.kind === "album" || root.media.kind === "playlist" ? "Save as Audio Files" : "Save as Audio File"; visible: (root.media.kind === "song" || root.media.kind === "album" || root.media.kind === "playlist" || !!root.media.videoId) && !root.localSong && !root.localCollection && !(root.download.files && (root.download.files.state === "saved" || root.download.files.state === "saving")); height: visible ? implicitHeight : 0; onTriggered: downloadsState.saveFiles(root.download.key ? Object.assign({}, root.media, {downloadKey: root.download.key}) : root.media) }
    ContextMenuItem { objectName: "deleteAudioFiles"; text: "Delete Audio Files…"; visible: !!(root.download.key && root.download.files && (root.download.files.state === "saved" || root.download.files.state === "failed")); height: visible ? implicitHeight : 0; onTriggered: downloadsState.requestFilesDeletion(root.download.key) }
    ContextMenuItem { objectName: "showSavedFiles"; text: "Show Saved Files"; visible: !!(root.download.files && root.download.files.state === "saved"); height: visible ? implicitHeight : 0; onTriggered: downloadsState.openFilesFolder() }
    ContextMenuItem { text: "Shuffle Play"; visible: !!root.downloadKey; height: visible ? implicitHeight : 0; enabled: root.download.ready > 0; onTriggered: downloadsState.play(root.downloadKey, true) }
    ContextMenuItem { text: "Cancel Download"; visible: !!root.download.key && root.downloadActive; height: visible ? implicitHeight : 0; onTriggered: downloadsState.cancel(root.download.key) }
    ContextMenuItem { text: root.download.state === "damaged" ? "Repair Download" : "Retry Download"; visible: ["failed", "cancelled", "damaged"].indexOf(root.download.state) >= 0; height: visible ? implicitHeight : 0; onTriggered: downloadsState.retry(root.download.key) }
    ContextMenuItem { text: "Refresh Download"; visible: !!root.downloadKey; height: visible ? implicitHeight : 0; enabled: (accountState.connected || appState.fixtureMode) && !root.downloadActive; onTriggered: downloadsState.download(root.download) }
    ContextMenuItem { text: "Remove Download"; visible: !!root.download.key; height: visible ? implicitHeight : 0; onTriggered: root.downloadKey ? downloadsState.requestRemoval(root.download.key) : downloadsState.remove(root.download.key) }
    ContextMenuItem { objectName: "localGoToAlbum"; text: "Go to Album"; visible: root.localSong && !!root.media.albumName && root.hasLocal; height: visible ? implicitHeight : 0; onTriggered: localState.openAlbum(root.media.localId) }
    ContextMenuItem { objectName: "localGoToArtist"; text: "Go to Artist"; visible: root.localSong && !!(root.media.albumArtist || root.media.artist) && root.hasLocal; height: visible ? implicitHeight : 0; onTriggered: localState.openArtist(root.media.localId) }
    ContextMenuItem { objectName: "showInFolder"; text: "Show in Folder"; visible: root.localSong && !!root.media.path; height: visible ? implicitHeight : 0; onTriggered: appState.showInFolder(root.media.path) }
    ContextMenuItem { objectName: "localRemoveSong"; text: "Remove from Local Music"; visible: root.localSong && root.hasLocal && !root.context.queueKey; height: visible ? implicitHeight : 0; onTriggered: localState.removeSong(root.media.localId) }
    ContextMenuItem { text: "Go to Album"; visible: root.song && !!(root.media.album && root.media.album.id); height: visible ? implicitHeight : 0; onTriggered: browseState.open({kind: "album", id: root.media.album.id}) }
    ContextMenuItem { text: "Go to Artist"; visible: root.song && !!(root.media.artists && root.media.artists.length && root.media.artists[0].id); height: visible ? implicitHeight : 0; onTriggered: browseState.open({kind: "artist", id: root.media.artists[0].id}) }
    ThemedMenuSeparator { visible: root.playlistEntry || (root.media.kind === "playlist" && root.media.owned); height: visible ? implicitHeight : 0 }
    ContextMenuItem { text: "Remove from Playlist"; visible: root.playlistEntry; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.removeEntry(root.media) }
    ContextMenuItem { text: "Move Up"; visible: root.playlistEntry; height: visible ? implicitHeight : 0; enabled: root.canEdit && !catalogState.busy && !catalogState.reordered && root.context.index > 0; onTriggered: libraryState.moveEntry(root.media, -1) }
    ContextMenuItem { text: "Move Down"; visible: root.playlistEntry; height: visible ? implicitHeight : 0; enabled: root.canEdit && !catalogState.busy && !catalogState.reordered && (root.context.index + 1 < (catalogState.data.items || []).length || catalogState.data.cursor !== undefined && catalogState.data.cursor !== null); onTriggered: libraryState.moveEntry(root.media, 1) }
    ContextMenuItem { text: "Rename Playlist"; visible: root.media.kind === "playlist" && root.media.owned; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.edit("playlist_rename", root.media) }
    ContextMenuItem { text: "Delete Playlist"; visible: root.media.kind === "playlist" && root.media.owned; height: visible ? implicitHeight : 0; enabled: root.canEdit; onTriggered: libraryState.edit("playlist_delete", root.media) }
    ThemedMenuSeparator { visible: !!root.context.queueKey; height: visible ? implicitHeight : 0 }
    ContextMenuItem { text: "Remove from Queue"; visible: !!root.context.queueKey; height: visible ? implicitHeight : 0; onTriggered: playerState.removeKey(root.context.queueKey) }
    ContextMenuItem { text: "Move Up in Queue"; visible: !!root.context.queueKey && !!root.media.movable; height: visible ? implicitHeight : 0; onTriggered: playerState.moveKey(root.context.queueKey, -1) }
    ContextMenuItem { text: "Move Down in Queue"; visible: !!root.context.queueKey && !!root.media.movable; height: visible ? implicitHeight : 0; onTriggered: playerState.moveKey(root.context.queueKey, 1) }
}
