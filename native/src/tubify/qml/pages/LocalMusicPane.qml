import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "../Theme.js" as Theme
import "../components"

// Music already on this computer, laid out like Downloads: filter chips, a sort menu, a filter
// field, albums, artists and folders as cards, and every song as a row. Files are played where
// they are; nothing here changes or deletes them.
Item {
    id: root
    objectName: "localMusicPane"
    property real gutter: Theme.gutter(width)
    readonly property real rightGutter: appState.panel ? 0 : gutter
    readonly property bool songs: localState.filter === "Songs"
    readonly property bool empty: localState.initialized && localState.folders.length === 0
    property var selectedFolder: ({})
    property bool blockingShortcuts: removal.opened || folderDialog.visible
    Connections {
        target: localState
        function onFolderRemovalRequested(folder) { root.selectedFolder = folder; removal.open() }
    }
    FolderDialog {
        id: folderDialog
        title: "Choose a Music Folder"
        onAccepted: localState.addFolder(selectedFolder)
    }
    Component {
        id: controls
        Item {
            LibraryTabs { width: parent.width; current: "Local Music" }
            ListView {
                id: filters
                objectName: "localFilters"
                y: 84; width: parent.width - 216; height: 36
                orientation: ListView.Horizontal; spacing: Theme.spacingMedium; clip: true
                model: localState.filters
                delegate: FilterChip {
                    required property string modelData
                    text: modelData
                    selected: localState.filter === modelData
                    onClicked: localState.setFilter(modelData)
                }
            }
            EdgeArrows { target: filters }
            ThemedComboBox {
                objectName: "localSortOrder"
                x: parent.width - width; y: 84; width: 200; height: 36
                model: localState.orders; currentIndex: localState.orders.indexOf(localState.order)
                Accessible.name: "Local Music sort order"
                onActivated: localState.sort(currentText)
            }
            ThemedTextField {
                id: filterField
                objectName: "localFilterField"
                y: 132; width: Math.min(280, parent.width * 0.38); height: 40
                placeholderText: "Filter " + localState.filter.toLowerCase()
                text: localState.query
                Accessible.name: "Filter Local Music"
                onTextEdited: localState.setQuery(text)
                Keys.onEscapePressed: { text = ""; localState.setQuery("") }
            }
            Text {
                objectName: "localSummary"
                anchors.left: filterField.right; anchors.leftMargin: Theme.spacingLarge
                anchors.right: folderActions.left; anchors.rightMargin: Theme.spacingMedium
                anchors.verticalCenter: filterField.verticalCenter
                text: localState.scanning ? localState.scanLabel : localState.summary
                textFormat: Text.PlainText; color: themeState.secondary; elide: Text.ElideRight; font.pixelSize: Theme.textBody
            }
            Row {
                id: folderActions
                anchors.right: parent.right; anchors.verticalCenter: filterField.verticalCenter; spacing: Theme.spacingSmall
                IconButton {
                    objectName: "localRescan"
                    iconName: "refresh"; tip: localState.scanning ? "Scanning Local Music" : "Rescan Local Music"
                    enabled: !localState.scanning && localState.folders.length > 0
                    onClicked: localState.rescan(-1)
                }
                FilterChip {
                    objectName: "localAddFolder"
                    choice: false
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Add Folder"
                    onClicked: folderDialog.open()
                }
            }
            // Scan progress; it fills in place, so rows below never move.
            Rectangle {
                objectName: "localScanProgress"
                y: 180; width: parent.width; height: 3; radius: 2
                color: themeState.border
                opacity: localState.scanning ? 1 : 0
                Behavior on opacity { enabled: !appState.reducedMotion; NumberAnimation { duration: Theme.motionFast } }
                Rectangle {
                    height: parent.height; radius: parent.radius; color: themeState.accent
                    width: parent.width * Math.max(0.02, Math.min(1, localState.scanProgress))
                    Behavior on width { enabled: !appState.reducedMotion; NumberAnimation { duration: Theme.motionFast } }
                }
            }
            Text {
                objectName: "localMessage"
                y: 190; width: parent.width
                visible: !!localState.message
                text: localState.message
                textFormat: Text.PlainText; color: themeState.secondary; elide: Text.ElideRight; font.pixelSize: Theme.textSmall
            }
        }
    }
    GridView {
        id: grid
        objectName: "localGrid"
        WheelScroll { view: grid }
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        visible: !root.songs && !root.empty; clip: true; bottomMargin: 32
        property int columns: Math.max(1, Math.floor((width + 24) / (Theme.cardWidth + 24)))
        cellWidth: width / columns; cellHeight: cellWidth + 84
        model: localState.cardsModel; ScrollBar.vertical: ScrollBar {}
        header: Loader { width: grid.width; height: 216; sourceComponent: controls; active: grid.visible }
        delegate: MediaCard {
            required property var modelData
            width: grid.cellWidth - 24; height: grid.cellHeight - 24
            media: modelData
            onActivated: localState.open(modelData.key)
            onPlayRequested: localState.play(modelData.key, false)
        }
    }
    ListView {
        id: songList
        objectName: "localSongs"
        WheelScroll { view: songList }
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        visible: root.songs && !root.empty; clip: true; bottomMargin: 32
        model: localState.songsModel
        ScrollBar.vertical: ScrollBar {}
        header: Loader { width: songList.width; height: 216; sourceComponent: controls; active: songList.visible }
        delegate: SongRow {
            required property var modelData
            required property int index
            width: songList.width; media: modelData
            onActivated: localState.playSongs(index)
        }
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter; y: 260
        width: parent.width - 80
        visible: !root.empty && localState.initialized && localState.count === 0
        text: localState.query ? "No " + localState.filter.toLowerCase() + " match “" + localState.query + "”." : localState.scanning ? "Looking for music…" : "No " + localState.filter.toLowerCase() + " in your music folders yet."
        textFormat: Text.PlainText; color: themeState.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.textTitle
    }
    // First run: no folders chosen yet.
    Item {
        anchors.fill: parent
        visible: root.empty
        LibraryTabs { x: root.gutter; width: parent.width - root.gutter - root.rightGutter; current: "Local Music" }
        Column {
            objectName: "localEmptyState"
            anchors.centerIn: parent; width: Math.min(520, parent.width - 80); spacing: Theme.spacingLarge
            Text { width: parent.width; text: "Play Your Own Music"; color: themeState.foreground; font.bold: true; font.pixelSize: Theme.textHeading; horizontalAlignment: Text.AlignHCenter }
            Text { width: parent.width; text: "Add a folder with music you already have, such as your Digital Audio Manager library or music from other apps. Tubify plays the files where they are and never changes them."; color: themeState.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.textTitle }
            ThemeActionButton {
                objectName: "localAddFirstFolder"
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Add Music Folder"; primary: true
                onClicked: folderDialog.open()
            }
            Column {
                width: parent.width; spacing: Theme.spacingSmall
                visible: !!localState.suggestedFolder
                ThemeActionButton {
                    objectName: "localAddSuggested"
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Add Digital Audio Manager Library"
                    onClicked: localState.addSuggestedFolder()
                }
                Text { width: parent.width; text: localState.suggestedFolder; textFormat: Text.PlainText; color: themeState.secondary; elide: Text.ElideMiddle; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.textSmall }
            }
        }
    }
    ThemedDialog {
        id: removal
        objectName: "localFolderRemovalDialog"
        parent: Overlay.overlay
        width: Math.min(460, root.width - 48)
        title: "Remove Folder?"
        contentItem: ColumnLayout {
            spacing: Theme.spacingLarge
            Label {
                Layout.fillWidth: true
                text: "Stop listing “" + (root.selectedFolder.name || "this folder") + "” in Local Music? " + (root.selectedFolder.songs || 0).toLocaleString() + " songs will disappear from Tubify. The files stay where they are and aren't changed."
                textFormat: Text.PlainText; color: themeState.foreground; wrapMode: Text.Wrap
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: removal.reject() }
                ThemeActionButton { text: "Remove Folder"; primary: true; onClicked: removal.accept() }
            }
        }
        onAccepted: localState.removeFolder(root.selectedFolder.id)
    }
}
