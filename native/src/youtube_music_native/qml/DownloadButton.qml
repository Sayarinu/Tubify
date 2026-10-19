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
    readonly property real progress: song ? (downloadsState.trackProgress[mediaId] || 0) : (entry.progress || 0)
    iconName: status === "complete" || status === "ready" ? "circleCheck" : "download"
    tip: status === "complete" || status === "ready" ? entry.state === "complete" ? "Remove download" : "Downloaded" : status === "downloading" || status === "queued" ? "Cancel download" : status === "damaged" ? "Repair download" : "Download"
    iconColor: status === "complete" || status === "ready" ? themeState.accent : status === "damaged" ? "#ffb4a6" : themeState.foreground
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
        Connections {
            target: downloadsState
            function onChanged() { progressRing.requestPaint() }
        }
        Component.onCompleted: requestPaint()
    }
}
