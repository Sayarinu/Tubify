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
    // Saved audio files are reported after the download itself.
    function filesLabel(entry) {
        var files = entry.files
        if (!files) return ""
        if (files.state === "saved") return " · Files saved"
        if (files.state === "saving") return " · Saving files · " + files.saved + " of " + files.total
        if (files.state === "pending") return entry.state === "complete" ? " · Saving files" : ""
        if (files.state === "failed") return " · Files not saved"
        return ""
    }
    function stateLabel(entry) { return downloadLabel(entry) + filesLabel(entry) }
    function downloadLabel(entry) {
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
                orientation: ListView.Horizontal; spacing: Theme.spacingMedium; clip: true
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
            // Where downloads are kept and the page's actions, wrapping onto a second line when narrow.
            Flow {
                id: storageActions
                objectName: "downloadStyles"
                y: 136; width: parent.width; spacing: Theme.spacingSmall
                Row {
                    spacing: Theme.spacingSmall
                    Text { anchors.verticalCenter: parent.verticalCenter; text: "Save downloads"; color: themeState.secondary; font.pixelSize: Theme.textBody }
                    DownloadStyleChoice { objectName: "downloadStyleChoice"; anchors.verticalCenter: parent.verticalCenter }
                }
                Row {
                    spacing: Theme.spacingSmall
                    IconButton { iconName: "refresh"; tip: "Refresh Download Status"; onClicked: downloadsState.refresh() }
                    FilterChip {
                        objectName: "downloadAllPlaylists"
                        choice: false
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Download All Playlists"
                        enabled: (accountState.connected || appState.fixtureMode) && appState.playlists.length > 0
                        onClicked: downloadsState.downloadAll(appState.playlists)
                    }
                }
            }
            // How much space each place uses.
            Row {
                id: storageStatus
                y: storageActions.y + storageActions.height + Theme.spacingSmall
                width: parent.width; spacing: 4
                Text {
                    objectName: "audioFilesStatus"
                    width: Math.min(implicitWidth, parent.width - openFiles.width - 8)
                    text: root.bytesLabel(downloadsState.usedBytes) + " in Tubify · " + (downloadsState.fileBytes > 0 || downloadsState.downloadStyle === "files" ? root.bytesLabel(downloadsState.fileBytes) + " as audio files · " : "") + root.bytesLabel(downloadsState.freeBytes) + " free"
                    textFormat: Text.PlainText; color: themeState.secondary; elide: Text.ElideMiddle; font.pixelSize: Theme.textBody
                }
                InlineLink {
                    id: openFiles
                    text: "Open Folder"
                    font.pixelSize: Theme.textBody
                    onActivated: downloadsState.openFilesFolder()
                }
            }
            implicitHeight: storageStatus.y + storageStatus.height + 24
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
        header: Loader { width: grid.width; height: item ? item.implicitHeight : 220; sourceComponent: controls; active: grid.visible }
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
        header: Loader { width: songList.width; height: item ? item.implicitHeight : 220; sourceComponent: controls; active: songList.visible }
        delegate: SongRow {
            required property var modelData
            required property int index
            width: songList.width; media: modelData
            onActivated: downloadsState.playSongs(index)
        }
    }
    Column {
        anchors.centerIn: parent; width: parent.width - 80; spacing: Theme.spacingLarge
        visible: downloadsState.count === 0
        Text { width: parent.width; text: "Music Wherever You Go"; color: themeState.foreground; font.bold: true; font.pixelSize: Theme.textHeading; horizontalAlignment: Text.AlignHCenter }
        Text { width: parent.width; text: downloadsState.collections.length ? "No downloaded " + downloadsState.filter.toLowerCase() + " yet." : "Download songs, albums and playlists from their menus.\nCompleted music stays available offline."; color: themeState.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.textTitle }
    }
    ThemedDialog {
        id: removal
        objectName: "downloadRemovalDialog"
        parent: Overlay.overlay
        width: Math.min(460, root.width - 48)
        title: "Remove Download?"
        contentItem: ColumnLayout {
            spacing: Theme.spacingLarge
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
