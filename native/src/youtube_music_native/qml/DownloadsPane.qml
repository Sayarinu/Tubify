import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

Item {
    id: root
    objectName: "downloadsPane"
    property real gutter: Theme.gutter(width)
    property string selectedKind: "All"
    property var selectedEntry: ({})
    property bool blockingShortcuts: options.opened || removal.opened
    property var entries: downloadsState.collections.filter(function(entry) { return root.selectedKind === "All" || entry.kind === root.selectedKind.toLowerCase().slice(0, -1) })
    function bytesLabel(value) {
        if (value >= 1073741824) return (value / 1073741824).toFixed(1) + " GB"
        return (value / 1048576).toFixed(1) + " MB"
    }
    function stateLabel(entry) {
        if (entry.state === "complete") return "Downloaded"
        if (entry.state === "damaged") return "Repair needed · " + entry.ready + " of " + entry.total + " available"
        if (entry.state === "downloading") return "Downloading · " + Math.round(entry.progress * 100) + "%"
        if (entry.state === "queued") return "Waiting to download"
        if (entry.state === "cancelled") return "Cancelled · " + entry.ready + " of " + entry.total + " available"
        return entry.error || "Download stopped · Retry to continue"
    }
    ListView {
        id: list
        objectName: "downloadsList"
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        clip: true; bottomMargin: 32
        model: root.entries
        ScrollBar.vertical: ScrollBar {}
        header: Item {
            width: list.width; height: 204
            Row {
                width: parent.width; height: 52; spacing: 24
                Button { text: "Library"; flat: true; height: 52; palette.windowText: themeState.secondary; onClicked: libraryState.select("Playlists") }
                Button { text: "Downloads"; flat: true; height: 52; palette.windowText: themeState.foreground; Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: themeState.accent } }
            }
            Rectangle { y: 52; height: 1; width: parent.width; color: themeState.border }
            Row {
                y: 84; height: 36; spacing: 12
                Repeater {
                    model: ["All", "Songs", "Albums", "Playlists"]
                    Button {
                        id: filter
                        required property string modelData
                        text: modelData; height: 36; leftPadding: 14; rightPadding: 14
                        palette.buttonText: root.selectedKind === text ? themeState.onAccent : themeState.foreground
                        background: Rectangle { radius: 8; color: root.selectedKind === filter.text ? themeState.accent : filter.hovered ? themeState.hover : themeState.surface; border.width: filter.visualFocus ? 2 : 0; border.color: themeState.accent }
                        onClicked: root.selectedKind = text
                    }
                }
            }
            Column {
                y: 148; width: parent.width - 48; spacing: 5
                Text { width: parent.width; text: root.bytesLabel(downloadsState.usedBytes) + " downloaded · " + root.bytesLabel(downloadsState.freeBytes) + " free"; color: themeState.secondary; elide: Text.ElideRight; font.pixelSize: 14 }
            }
            IconButton { anchors.right: parent.right; y: 138; iconName: "refresh"; tip: "Refresh Download Status"; onClicked: downloadsState.refresh() }
        }
        delegate: ItemDelegate {
            id: entry
            required property var modelData
            width: list.width; height: 104; padding: 0
            Accessible.name: modelData.title + ", " + root.stateLabel(modelData)
            onClicked: downloadsState.open(modelData.key)
            background: Rectangle { radius: 4; color: entry.hovered ? themeState.surface : "transparent"; border.color: entry.visualFocus ? themeState.accent : "transparent"; border.width: 1 }
            contentItem: Item {
                Cover { x: 8; anchors.verticalCenter: parent.verticalCenter; width: 64; height: 64; source: entry.modelData.thumbnail || ""; mediaKey: entry.modelData.key; radius: 3 }
                Column {
                    x: 88; anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - x - controls.width - 16; spacing: 5
                    Text { width: parent.width; text: entry.modelData.title; textFormat: Text.PlainText; color: themeState.foreground; elide: Text.ElideRight; font.pixelSize: 16 }
                    Text { width: parent.width; text: entry.modelData.kind.charAt(0).toUpperCase() + entry.modelData.kind.slice(1) + " · " + entry.modelData.total + (entry.modelData.total === 1 ? " song" : " songs"); color: themeState.secondary; elide: Text.ElideRight; font.pixelSize: 12 }
                    Text { width: parent.width; text: root.stateLabel(entry.modelData); textFormat: Text.PlainText; color: entry.modelData.state === "damaged" || entry.modelData.state === "failed" ? "#ffb4a6" : themeState.secondary; elide: Text.ElideRight; font.pixelSize: 12 }
                    ProgressBar { width: parent.width; height: 3; value: entry.modelData.progress || 0; visible: entry.modelData.state === "downloading" || entry.modelData.state === "queued" }
                }
                Row {
                    id: controls
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 4
                    IconButton { iconName: "play"; tip: "Play " + entry.modelData.title; enabled: entry.modelData.ready > 0; onClicked: downloadsState.play(entry.modelData.key, false) }
                    IconButton { iconName: "close"; tip: "Cancel Download"; visible: entry.modelData.state === "queued" || entry.modelData.state === "downloading"; onClicked: downloadsState.cancel(entry.modelData.key) }
                    IconButton { iconName: "download"; tip: entry.modelData.state === "damaged" ? "Repair Download" : "Retry Download"; visible: entry.modelData.state === "failed" || entry.modelData.state === "cancelled" || entry.modelData.state === "damaged"; onClicked: downloadsState.retry(entry.modelData.key) }
                    IconButton { iconName: "more"; tip: "Download Options for " + entry.modelData.title; onClicked: { root.selectedEntry = entry.modelData; options.popup() } }
                }
            }
        }
    }
    Column {
        anchors.centerIn: parent; width: parent.width - 80; spacing: 16
        visible: !root.entries.length
        Text { width: parent.width; text: "Music Wherever You Go"; color: themeState.foreground; font.family: Theme.headingFont; font.bold: true; font.pixelSize: 28; horizontalAlignment: Text.AlignHCenter }
        Text { width: parent.width; text: downloadsState.collections.length ? "No downloaded " + root.selectedKind.toLowerCase() + " yet." : "Download songs, albums and playlists from their menus.\nCompleted music stays available offline."; color: themeState.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 15 }
    }
    ThemedMenu {
        id: options
        objectName: "downloadOptionsMenu"
        ContextMenuItem { text: "Shuffle Play"; enabled: root.selectedEntry.ready > 0; onTriggered: downloadsState.play(root.selectedEntry.key, true) }
        ContextMenuItem { text: "Refresh Download"; enabled: (accountState.connected || appState.fixtureMode) && root.selectedEntry.state !== "queued" && root.selectedEntry.state !== "downloading"; onTriggered: downloadsState.download(root.selectedEntry) }
        ContextMenuItem { text: "Remove Download"; onTriggered: removal.open() }
    }
    ThemedDialog {
        id: removal
        objectName: "downloadRemovalDialog"
        parent: Overlay.overlay
        width: Math.min(460, root.width - 48)
        title: "Remove Download?"
        contentItem: ColumnLayout {
            spacing: 16
            Label { Layout.fillWidth: true; text: "Remove “" + (root.selectedEntry.title || "this music") + "” from this device? Songs used by another download will stay."; textFormat: Text.PlainText; color: themeState.foreground; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: removal.reject() }
                ThemeActionButton { text: "Remove"; primary: true; onClicked: removal.accept() }
            }
        }
        onAccepted: downloadsState.remove(root.selectedEntry.key)
    }
}
