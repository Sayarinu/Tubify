import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Theme.js" as Theme
import "../components"
import "../settings"

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
            // Filters this page's downloads; the search at the top still searches YouTube Music.
            ThemedTextField {
                id: filterField
                objectName: "downloadFilterField"
                y: 132; width: Math.min(280, Math.max(160, parent.width - 56)); height: 40
                placeholderText: "Search downloaded " + downloadsState.filter.toLowerCase()
                text: downloadsState.query
                Accessible.name: "Search Downloads"
                onTextEdited: downloadsState.setQuery(text)
                Keys.onEscapePressed: { text = ""; downloadsState.setQuery("") }
            }
            // Every page action lives in this menu; its badge counts the downloads that failed.
            IconButton {
                id: moreActions
                objectName: "downloadsMore"
                x: parent.width - width
                y: filterField.y + (filterField.height - height) / 2
                iconName: "more"
                tip: downloadsState.retryableCount > 0 ? "More Download Options · " + downloadsState.retryableCount + " failed" : "More Download Options"
                onClicked: moreMenu.popup(moreActions, moreActions.width - moreMenu.implicitWidth, moreActions.height, null)
                CountBadge { objectName: "downloadsMoreBadge"; x: parent.width - width + 2; y: -2; count: downloadsState.retryableCount }
                ThemedMenu {
                    id: moreMenu
                    implicitWidth: 252
                    ContextMenuItem {
                        objectName: "retryFailedDownloads"
                        text: "Retry Failed (" + downloadsState.retryableCount + ")"
                        visible: downloadsState.retryableCount > 0; height: visible ? implicitHeight : 0
                        Accessible.description: "Download every failed song and audio file again"
                        onTriggered: downloadsState.retryFailed()
                    }
                    ContextMenuItem {
                        objectName: "downloadAllPlaylists"
                        text: "Download All Playlists"
                        enabled: (accountState.connected || appState.fixtureMode) && appState.playlists.length > 0
                        onTriggered: downloadsState.downloadAll(appState.playlists)
                    }
                    ContextMenuItem { objectName: "refreshDownloads"; text: "Refresh Download Status"; onTriggered: downloadsState.refresh() }
                    ThemedMenuSeparator {}
                    ContextMenuItem { text: "Open Audio Files Folder"; onTriggered: downloadsState.openFilesFolder() }
                    ContextMenuItem {
                        objectName: "deleteAllAudioFiles"
                        text: "Delete Audio Files…"
                        enabled: downloadsState.savedFileCount > 0
                        Accessible.description: "Delete every audio file Tubify saved"
                        onTriggered: downloadsState.requestAllFilesDeletion()
                    }
                }
            }
            // Where downloads are kept, then how much space each place uses: beside the choice,
            // or under it when narrow.
            Row {
                id: storageChoice
                objectName: "downloadStyles"
                y: filterField.y + filterField.height + Theme.spacingSmall
                spacing: Theme.spacingSmall
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Save as"; color: themeState.secondary; font.pixelSize: Theme.textBody }
                DownloadStyleChoice { objectName: "downloadStyleChoice"; anchors.verticalCenter: parent.verticalCenter }
            }
            Text {
                id: storageStatus
                objectName: "audioFilesStatus"
                readonly property bool below: parent.width - storageChoice.width - Theme.spacingLarge < Math.min(implicitWidth, 240)
                x: below ? 0 : storageChoice.width + Theme.spacingLarge
                y: below ? storageChoice.y + storageChoice.height + Theme.spacingSmall : storageChoice.y + (storageChoice.height - height) / 2
                width: parent.width - x
                text: root.bytesLabel(downloadsState.usedBytes) + " in Tubify · " + (downloadsState.fileBytes > 0 || downloadsState.downloadStyle === "files" ? root.bytesLabel(downloadsState.fileBytes) + " as audio files · " : "") + root.bytesLabel(downloadsState.freeBytes) + " free"
                textFormat: Text.PlainText; color: themeState.secondary; elide: Text.ElideMiddle; font.pixelSize: Theme.textBody
            }
            implicitHeight: Math.max(storageChoice.y + storageChoice.height, storageStatus.y + storageStatus.height) + 24
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
        Text { width: parent.width; visible: !downloadsState.query; text: "Music Wherever You Go"; color: themeState.foreground; font.bold: true; font.pixelSize: Theme.textHeading; horizontalAlignment: Text.AlignHCenter }
        Text { width: parent.width; text: downloadsState.query && downloadsState.collections.length ? "No downloaded " + downloadsState.filter.toLowerCase() + " match “" + downloadsState.query + "”." : downloadsState.collections.length ? "No downloaded " + downloadsState.filter.toLowerCase() + " yet." : "Download songs, albums and playlists from their menus.\nCompleted music stays available offline."; color: themeState.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.textTitle }
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
            // Saved audio files stay unless the person chooses to delete them too.
            SettingsCheckBox {
                id: alsoFiles
                objectName: "removeAlsoDeletesFiles"
                Layout.fillWidth: true
                visible: !!(root.selectedEntry.files && root.selectedEntry.files.state === "saved")
                text: "Also delete its audio files"
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: removal.reject() }
                ThemeActionButton { text: "Remove"; primary: true; onClicked: removal.accept() }
            }
        }
        onAboutToShow: alsoFiles.checked = false
        onAccepted: downloadsState.remove(root.selectedEntry.key, alsoFiles.visible && alsoFiles.checked)
    }
}
