import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Theme.js" as Theme
import "../components"

// Laid out like Library: filter chips and a sort menu, playlists and albums as cards,
// and every downloaded song as a row.
Item {
    id: root
    objectName: "downloadsPane"
    property real gutter: Theme.gutter(width)
    // Next to an open panel, the panel's own gap replaces the right gutter.
    readonly property real rightGutter: appState.panel ? 0 : gutter
    readonly property bool songs: downloadsState.filter === "Songs"
    property var selectedEntry: ({})
    property bool blockingShortcuts: removal.opened
    function bytesLabel(value) {
        if (value >= 1073741824) return (value / 1073741824).toFixed(1) + " GB"
        return (value / 1048576).toFixed(1) + " MB"
    }
    function songCount(entry) { return entry.total + (entry.total === 1 ? " song" : " songs") }
    function stateLabel(entry) {
        if (entry.state === "complete") return entry.error ? "Downloaded · " + entry.ready + " of " + songCount(entry) : "Downloaded · " + songCount(entry)
        if (entry.state === "damaged") return "Repair needed · " + entry.ready + " of " + entry.total + " available"
        if (entry.state === "downloading") return "Downloading · " + Math.round(entry.progress * 100) + "%"
        if (entry.state === "queued") return "Waiting to download · " + songCount(entry)
        if (entry.state === "cancelled") return "Cancelled · " + entry.ready + " of " + entry.total + " available"
        return entry.error || "Download stopped · Retry to continue"
    }
    Connections {
        target: downloadsState
        function onRemovalRequested(entry) { root.selectedEntry = entry; removal.open() }
    }
    Component {
        id: controls
        Item {
            LibraryTabs { width: parent.width; current: "Downloads" }
            ListView {
                id: filters
                objectName: "downloadFilters"
                y: 84; width: parent.width - 216; height: 36
                orientation: ListView.Horizontal; spacing: 12; clip: true
                model: downloadsState.filters
                delegate: FilterChip {
                    required property string modelData
                    text: modelData
                    selected: downloadsState.filter === modelData
                    onClicked: downloadsState.setFilter(modelData)
                }
            }
            EdgeArrows { target: filters }
            ThemedComboBox {
                id: sortOrder
                objectName: "downloadSortOrder"
                x: parent.width - width; y: 84; width: 200; height: 36
                model: downloadsState.orders; currentIndex: downloadsState.orders.indexOf(downloadsState.order)
                Accessible.name: "Downloads sort order"
                onActivated: downloadsState.sort(currentText)
            }
            Text {
                width: parent.width - storageActions.width - 16
                anchors.verticalCenter: storageActions.verticalCenter
                text: root.bytesLabel(downloadsState.usedBytes) + " downloaded · " + root.bytesLabel(downloadsState.freeBytes) + " free"
                color: themeState.secondary; elide: Text.ElideRight; font.pixelSize: 14
            }
            Row {
                id: storageActions
                anchors.right: parent.right; y: 136; spacing: 8
                IconButton { iconName: "refresh"; tip: "Refresh Download Status"; onClicked: downloadsState.refresh() }
                Button {
                    id: downloadAll
                    objectName: "downloadAllPlaylists"
                    height: 36; leftPadding: 14; rightPadding: 14
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Download All Playlists"
                    Accessible.name: "Download All Playlists"
                    enabled: (accountState.connected || appState.fixtureMode) && appState.playlists.length > 0
                    palette.buttonText: themeState.foreground
                    background: Rectangle { radius: height / 2; color: downloadAll.hovered ? themeState.hover : themeState.surface; border.width: downloadAll.visualFocus ? 2 : 0; border.color: themeState.accent }
                    onClicked: downloadsState.downloadAll(appState.playlists)
                }
            }
        }
    }
    GridView {
        id: grid
        objectName: "downloadsGrid"
        WheelScroll { view: grid }
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        visible: !root.songs; clip: true; bottomMargin: 32
        property int columns: Math.max(1, Math.floor((width + 24) / (Theme.cardWidth + 24)))
        cellWidth: width / columns; cellHeight: cellWidth + 84
        model: downloadsState.collectionsModel; ScrollBar.vertical: ScrollBar {}
        header: Loader { width: grid.width; height: 196; sourceComponent: controls; active: grid.visible }
        delegate: MediaCard {
            required property var modelData
            width: grid.cellWidth - 24; height: grid.cellHeight - 24
            // The subtitle carries the download's progress or outcome.
            media: Object.assign({}, modelData, {artist: root.stateLabel(modelData)})
            menuContext: ({downloadKey: modelData.key})
            onActivated: downloadsState.open(modelData.key)
            onPlayRequested: downloadsState.play(modelData.key, false)
        }
    }
    ListView {
        id: songList
        objectName: "downloadsSongs"
        WheelScroll { view: songList }
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        visible: root.songs; clip: true; bottomMargin: 32
        model: downloadsState.songsModel
        ScrollBar.vertical: ScrollBar {}
        header: Loader { width: songList.width; height: 196; sourceComponent: controls; active: songList.visible }
        delegate: SongRow {
            required property var modelData
            required property int index
            width: songList.width; media: modelData
            onActivated: downloadsState.playSongs(index)
        }
    }
    Column {
        anchors.centerIn: parent; width: parent.width - 80; spacing: 16
        visible: downloadsState.count === 0
        Text { width: parent.width; text: "Music Wherever You Go"; color: themeState.foreground; font.bold: true; font.pixelSize: 28; horizontalAlignment: Text.AlignHCenter }
        Text { width: parent.width; text: downloadsState.collections.length ? "No downloaded " + downloadsState.filter.toLowerCase() + " yet." : "Download songs, albums and playlists from their menus.\nCompleted music stays available offline."; color: themeState.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 15 }
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
