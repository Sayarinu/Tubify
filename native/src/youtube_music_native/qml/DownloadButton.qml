import QtQuick
import "Theme.js" as Theme

IconButton {
    id: root
    required property var media
    readonly property bool song: media.kind === "song"
    readonly property string mediaId: media.videoId || media.id || ""
    property var entry: {
        var values = downloadsState.collections
        for (var i = 0; i < values.length; i++) if (values[i].key === media.kind + ":" + mediaId) return values[i]
        return ({})
    }
    readonly property string status: song ? (downloadsState.trackStates[mediaId] || "") : entry.state || ""
    iconName: status === "complete" || status === "ready" ? "circleCheck" : "download"
    tip: status === "complete" || status === "ready" ? entry.state === "complete" ? "Remove download" : "Downloaded" : status === "downloading" || status === "queued" ? "Cancel download" : status === "damaged" ? "Repair download" : "Download"
    iconColor: status === "complete" || status === "ready" ? Theme.accent : status === "damaged" ? "#ffb4a6" : Theme.foreground
    enabled: !!mediaId && !(song && (status === "complete" || status === "ready") && entry.state !== "complete")
    onClicked: {
        if ((entry.state === "complete" || entry.state === "ready") && entry.key) downloadsState.remove(entry.key)
        else if (entry.state === "downloading" || entry.state === "queued") downloadsState.cancel(entry.key)
        else if (entry.key) downloadsState.retry(entry.key)
        else downloadsState.download(media)
    }
    Rectangle { anchors.bottom: parent.bottom; height: 2; width: parent.width * (root.entry.progress || 0); color: Theme.accent; visible: root.entry.state === "downloading" }
}
