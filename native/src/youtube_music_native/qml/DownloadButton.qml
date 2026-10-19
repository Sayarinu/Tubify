import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

IconButton {
    id: root
    required property var media
    property var entry: {
        var values = downloadsState.collections
        for (var i = 0; i < values.length; i++) if (values[i].key === media.kind + ":" + media.id) return values[i]
        return ({})
    }
    iconName: entry.state === "complete" ? "check" : "download"
    tip: entry.state === "complete" ? "Remove download" : entry.state === "downloading" || entry.state === "queued" ? "Cancel download" : "Download"
    enabled: !!media.id
    onClicked: {
        if (entry.state === "complete") removal.open()
        else if (entry.state === "downloading" || entry.state === "queued") downloadsState.cancel(entry.key)
        else if (entry.key) downloadsState.retry(entry.key)
        else downloadsState.download(media)
    }
    Rectangle { anchors.bottom: parent.bottom; height: 2; width: parent.width * (root.entry.progress || 0); color: Theme.accent; visible: root.entry.state === "downloading" }
    Menu { id: removal; MenuItem { text: "Remove download"; onTriggered: downloadsState.remove(root.entry.key) } }
}
