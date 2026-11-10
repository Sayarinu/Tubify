import QtQuick

IconButton {
    id: root
    required property var media
    readonly property bool song: media.kind === "song"
    readonly property string mediaId: media.videoId || media.id || ""
    // Looked up by key on each state change instead of scanning every download.
    property var entry: { downloadsState.revision; return downloadsState.collectionEntry(media.kind + ":" + mediaId) }
    readonly property string status: { downloadsState.revision; return song ? downloadsState.songState(mediaId) : entry.state || "" }
    readonly property real progress: { downloadsState.progressRevision; return song ? downloadsState.songProgress(mediaId) : (entry.progress || 0) }
    iconName: status === "complete" || status === "ready" ? "circleCheck" : "download"
    tip: status === "complete" || status === "ready" ? entry.state === "complete" ? "Remove Download" : "Downloaded" : status === "downloading" || status === "queued" ? "Cancel Download" : status === "damaged" ? "Repair Download" : "Download"
    iconColor: status === "complete" || status === "ready" ? themeState.accent : status === "damaged" ? themeState.error : themeState.foreground
    // A downloaded song cannot be downloaded again, but its check keeps the accent like every other downloaded item.
    disabledIconColor: status === "complete" || status === "ready" ? themeState.accent : themeState.muted
    enabled: !!mediaId && !(song && (status === "complete" || status === "ready") && entry.state !== "complete")
    onClicked: {
        if ((entry.state === "complete" || entry.state === "ready") && entry.key) downloadsState.remove(entry.key)
        else if (entry.state === "downloading" || entry.state === "queued") downloadsState.cancel(entry.key)
        else if (entry.key) downloadsState.retry(entry.key)
        else downloadsState.download(media)
    }
    Canvas {
        id: progressRing
        anchors.centerIn: parent
        width: 32; height: 32
        visible: root.status === "downloading"
        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.beginPath()
            ctx.arc(width / 2, height / 2, 14, 0, Math.PI * 2)
            ctx.strokeStyle = themeState.border
            ctx.lineWidth = 2
            ctx.stroke()
            if (root.progress > 0) {
                ctx.beginPath()
                ctx.arc(width / 2, height / 2, 14, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, root.progress))
                ctx.strokeStyle = themeState.accent
                ctx.lineWidth = 2
                ctx.lineCap = "round"
                ctx.stroke()
            }
        }
        // Repaints only when this button's own progress or theme changes.
        Connections {
            target: root
            function onProgressChanged() { if (progressRing.visible) progressRing.requestPaint() }
        }
        onVisibleChanged: if (visible) requestPaint()
        Component.onCompleted: requestPaint()
    }
}
