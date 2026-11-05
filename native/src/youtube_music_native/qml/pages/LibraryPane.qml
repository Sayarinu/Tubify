import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme
import "../components"

Item {
    id: root
    objectName: "libraryPane"
    property real gutter: Theme.gutter(width)
    // Next to an open panel, the panel's own gap replaces the right gutter.
    readonly property real rightGutter: appState.panel ? 0 : gutter
    // Do not incubate delegates for another route while the page is being replaced.
    readonly property bool current: catalogState.route.indexOf("library_") === 0 || catalogState.route === "history"
    property var result: current ? catalogState.data : ({})
    property bool history: catalogState.route === "history"
    property bool rows: history || catalogState.route === "library_songs" || catalogState.route === "library_liked"
    Component {
        id: controls
        Item {
            LibraryTabs { width: parent.width; current: "Library"; visible: !root.history }
            Row { spacing: 16; visible: root.history; height: 72; Text { text: "History"; color: themeState.foreground; font.bold: true; font.pixelSize: 30 } }
            ListView {
                // Route views may be replaced immediately; avoid unfinished offscreen delegates.
                cacheBuffer: 0
                id: filters
                y: 84; width: parent.width - (sortOrder.visible ? 216 : 0); height: 36
                visible: !root.history; orientation: ListView.Horizontal; spacing: 12; clip: true
                model: libraryState.sections
                delegate: FilterChip {
                    required property string modelData
                    text: modelData
                    selected: libraryState.selectedSection === modelData
                    onClicked: libraryState.select(modelData)
                }
            }
            EdgeArrows { target: filters; visible: filters.visible }
            ThemedComboBox {
                id: sortOrder
                x: parent.width - width; y: 84; width: 200; height: 36
                visible: !root.history
                model: libraryState.orders; currentIndex: libraryState.orders.indexOf(libraryState.selectedOrder)
                Accessible.name: "Library sort order"
                onActivated: libraryState.sort(currentText)
            }
        }
    }
    property list<QtObject> pagers: [
        AutoPager { view: grid; active: root.current; cursor: root.result.cursor },
        AutoPager { view: songs; active: root.current; cursor: root.result.cursor }
    ]
    GridView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: grid
        WheelScroll { view: grid; onScrolled: catalogState.saveScroll(view.contentY) }
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        visible: !root.rows; clip: true; bottomMargin: 32
        property int columns: Math.max(1, Math.floor((width + 24) / (Theme.cardWidth + 24)))
        cellWidth: width / columns; cellHeight: cellWidth + 84
        model: root.current ? catalogState.itemsModel : null; ScrollBar.vertical: ScrollBar {}
        header: Loader { width: grid.width; height: 158; sourceComponent: controls }
        delegate: MediaCard {
            required property var modelData
            width: grid.cellWidth - 24; height: grid.cellHeight - 24; media: modelData
            onActivated: item => browseState.open(item)
            onPlayRequested: item => browseState.play(item)
        }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        footer: Column {
            width: grid.width
            LoadingSkeleton { width: parent.width; view: grid; mode: "grid"; columns: grid.columns; cellWidth: grid.cellWidth; cellHeight: grid.cellHeight }
        }
    }
    ListView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: songs
        WheelScroll { view: songs; onScrolled: catalogState.saveScroll(view.contentY) }
        objectName: "librarySongs"
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        visible: root.rows; clip: true; bottomMargin: 32; model: root.current ? catalogState.itemsModel : null
        ScrollBar.vertical: ScrollBar {}
        header: Loader { width: songs.width; height: root.history ? 96 : 158; sourceComponent: controls }
        delegate: SongRow {
            required property var modelData
            width: songs.width; media: modelData
            // History is a log rather than a collection, so it has no numbers to sort by.
            number: root.history || modelData.position === undefined ? 0 : modelData.position + 1
            onActivated: item => browseState.play(item)
        }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        footer: Column {
            width: songs.width
            LoadingSkeleton { width: parent.width; view: songs; mode: "rows" }
        }
    }
    Column {
        anchors.centerIn: parent; width: parent.width - 80; spacing: 20
        visible: !catalogState.busy && !(root.result.items || []).length
        Text { width: parent.width; text: catalogState.error || (!accountState.connected && !appState.fixtureMode ? "Connect YouTube Music to browse your library." : root.history ? "No listening history yet." : "Your " + libraryState.selectedSection.toLowerCase() + " will appear here."); textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 16; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
        ThemeActionButton { anchors.horizontalCenter: parent.horizontalCenter; text: "Retry"; visible: !!catalogState.error; onClicked: catalogState.refresh() }
        ThemeActionButton { anchors.horizontalCenter: parent.horizontalCenter; primary: true; text: "Connect YouTube Music"; visible: !accountState.connected && !appState.fixtureMode; onClicked: appState.openAccount() }
    }
    BusyIndicator { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 16; running: catalogState.busy && !catalogState.revalidating; visible: running && (root.result.items || []).length > 0 }
    property int revision: -1
    function restoreScroll() {
        if (catalogState.busy || revision === catalogState.revision) return
        revision = catalogState.revision
        Qt.callLater(function() { var view = root.rows ? songs : grid; if (catalogState.hasScrollPosition) view.contentY = catalogState.scrollPosition; else view.contentY = view.originY - view.topMargin })
    }
    Component.onCompleted: restoreScroll()
    Connections { target: catalogState; function onChanged() { root.restoreScroll() } }
}
