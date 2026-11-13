import QtQuick
import QtQuick.Shapes
import "../Theme.js" as Theme

// A download's state: the arrow to download, a ring filling with progress while queued or
// downloading, and the check once downloaded. Finishing fills the ring, which gives way to the check.
IconButton {
    id: root
    required property var media
    readonly property bool song: media.kind === "song"
    readonly property string mediaId: media.videoId || media.id || ""
    // Looked up by key on each state change instead of scanning every download.
    property var entry: { downloadsState.revision; return downloadsState.collectionEntry(media.kind + ":" + mediaId) }
    readonly property string status: { downloadsState.revision; return song ? downloadsState.songState(mediaId) : entry.state || "" }
    readonly property real progress: { downloadsState.progressRevision; return song ? downloadsState.songProgress(mediaId) : (entry.progress || 0) }
    readonly property bool done: status === "complete" || status === "ready"
    readonly property bool active: status === "downloading" || status === "queued"
    // True while a download that just finished shows its full ring before the check.
    property bool finishing: false
    readonly property bool ringShown: active || finishing
    readonly property int percent: Math.round(Math.min(1, Math.max(0, progress)) * 100)
    // How full the ring is drawn: empty while queued, the downloaded share while downloading.
    readonly property real ringTarget: finishing ? 1 : status === "downloading" ? Math.min(1, Math.max(0, progress)) : 0
    property real ringValue: ringTarget
    Behavior on ringValue { enabled: !appState.reducedMotion; NumberAnimation { duration: Theme.motionMedium; easing.type: Easing.OutCubic } }
    iconName: done ? "circleCheck" : "download"
    tip: done ? entry.state === "complete" ? "Remove Download" : "Downloaded"
        : status === "downloading" ? "Downloading " + percent + "% · Cancel Download"
        : status === "queued" ? "Waiting to Download · Cancel Download"
        : status === "damaged" ? "Repair Download" : "Download"
    iconColor: done ? themeState.accent : status === "damaged" ? themeState.error : themeState.foreground
    // A downloaded song cannot be downloaded again, but its check keeps the accent like every other downloaded item.
    disabledIconColor: done ? themeState.accent : themeState.muted
    enabled: !!mediaId && !(song && done && entry.state !== "complete")
    onClicked: {
        if ((entry.state === "complete" || entry.state === "ready") && entry.key) downloadsState.remove(entry.key)
        else if (entry.state === "downloading" || entry.state === "queued") downloadsState.cancel(entry.key)
        else if (entry.key) downloadsState.retry(entry.key)
        else downloadsState.download(media)
    }

    // Only a download seen going from queued or downloading to done animates; a reused row showing
    // other music, or a status refresh that changes nothing, does not.
    property string seenStatus: ""
    property string seenId: ""
    onStatusChanged: {
        // Read from status itself: bindings that depend on it may not have updated yet.
        var isDone = status === "complete" || status === "ready"
        var finished = isDone && seenId === mediaId && (seenStatus === "downloading" || seenStatus === "queued")
        seenStatus = status
        seenId = mediaId
        if (finished && !appState.reducedMotion) finish.restart()
        else if (!isDone) { finish.stop(); finishing = false; ring.opacity = 1; ring.scale = 1; contentItem.scale = 1 }
    }
    onMediaIdChanged: { finish.stop(); finishing = false; seenId = mediaId; seenStatus = status }
    // The arrow or check hides behind the ring; the finishing animation brings the check back itself.
    readonly property bool iconShown: !ringShown
    onIconShownChanged: if (!finish.running) contentItem.opacity = iconShown ? 1 : 0
    Component.onCompleted: { seenStatus = status; seenId = mediaId; contentItem.opacity = iconShown ? 1 : 0 }

    SequentialAnimation {
        id: finish
        ScriptAction { script: { root.finishing = true; ring.opacity = 1; ring.scale = 1; root.contentItem.opacity = 0 } }
        // The ring fills to 100% through ringValue's own animation.
        PauseAnimation { duration: Theme.motionMedium + 80 }
        ParallelAnimation {
            NumberAnimation { target: ring; property: "opacity"; to: 0; duration: Theme.motionMedium; easing.type: Easing.InCubic }
            NumberAnimation { target: ring; property: "scale"; to: 0.6; duration: Theme.motionMedium; easing.type: Easing.InCubic }
            NumberAnimation { target: root.contentItem; property: "opacity"; from: 0; to: 1; duration: Theme.motionMedium }
            NumberAnimation { target: root.contentItem; property: "scale"; from: 0.4; to: 1; duration: Theme.motionSlow; easing.type: Easing.OutBack }
        }
        ScriptAction { script: { root.finishing = false; ring.opacity = 1; ring.scale = 1 } }
    }

    Item {
        id: ring
        objectName: "downloadProgressRing"
        anchors.centerIn: parent
        width: root.iconSize + 4; height: width
        visible: root.ringShown
        readonly property real stroke: 2.5
        readonly property real radius: (width - stroke) / 2
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            // The theme's progress track, with the accent filling clockwise from the top.
            ShapePath {
                strokeColor: themeState.progressTrack; strokeWidth: ring.stroke; fillColor: "transparent"
                PathAngleArc { centerX: ring.width / 2; centerY: ring.height / 2; radiusX: ring.radius; radiusY: ring.radius; startAngle: 0; sweepAngle: 360 }
            }
            ShapePath {
                strokeColor: themeState.accent; strokeWidth: ring.stroke; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: ring.width / 2; centerY: ring.height / 2; radiusX: ring.radius; radiusY: ring.radius; startAngle: -90; sweepAngle: 360 * root.ringValue }
            }
        }
        // Clicking a ring cancels, so it carries a stop mark.
        Rectangle {
            objectName: "downloadStopMark"
            anchors.centerIn: parent
            width: Math.round(ring.width * 0.3); height: width; radius: 2
            color: root.iconColor
            visible: root.active && !root.finishing
        }
    }
}
