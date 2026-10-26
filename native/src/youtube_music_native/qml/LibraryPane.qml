import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    objectName: "libraryPane"
    property real gutter: Theme.gutter(width)
    // Do not incubate delegates for another route while the page is being replaced.
    property var result: (catalogState.route.indexOf("library_") === 0 || catalogState.route === "history") ? catalogState.data : ({})
    property bool history: catalogState.route === "history"
    property bool rows: history || catalogState.route === "library_songs" || catalogState.route === "library_liked"
    Component {
        id: controls
        Item {
            Row {
                width: parent.width; height: 52; spacing: 24; visible: !root.history
                Button { id: libraryTab; text: "Library"; flat: true; height: 52; palette.windowText: themeState.foreground; onClicked: libraryState.select("Playlists"); Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: themeState.accent } }
                Button { text: "Downloads"; flat: true; height: 52; palette.windowText: themeState.secondary; onClicked: appState.navigate("Downloads") }
            }
            Rectangle { y: 52; height: 1; width: parent.width; color: themeState.border; visible: !root.history }
            Row { spacing: 16; visible: root.history; height: 72; Text { text: "History"; color: themeState.foreground; font.family: Theme.headingFont; font.bold: true; font.pixelSize: 30 } }
            ListView {
                // Route views may be replaced immediately; avoid unfinished offscreen delegates.
                cacheBuffer: 0
                id: filters
                y: 84; width: parent.width - (sortOrder.visible ? 180 : 0); height: 36
                visible: !root.history; orientation: ListView.Horizontal; spacing: 12; clip: true
                model: libraryState.sections
                delegate: Button {
                    id: filter
                    required property string modelData
                    text: modelData; height: 36; leftPadding: 14; rightPadding: 14
                    palette.buttonText: libraryState.selectedSection === text ? themeState.onAccent : themeState.foreground
                    background: Rectangle { radius: 8; color: libraryState.selectedSection === filter.text ? themeState.accent : filter.hovered ? themeState.hover : themeState.surface; border.color: filter.visualFocus ? themeState.accent : "transparent" }
                    onClicked: libraryState.select(text)
                }
            }
            ComboBox {
                id: sortOrder
                x: parent.width - width; y: 84; width: 164; height: 36
                visible: !root.history && libraryState.selectedSection !== "Playlists" && libraryState.selectedSection !== "Liked songs"
                model: libraryState.orders; currentIndex: libraryState.orders.indexOf(libraryState.selectedOrder)
                palette.text: themeState.foreground; palette.buttonText: themeState.foreground; palette.windowText: themeState.foreground; palette.base: themeState.surface; palette.button: themeState.surface
                Accessible.name: "Library sort order"
                onActivated: libraryState.sort(currentText)
            }
        }
    }
    GridView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: grid
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        visible: !root.rows; clip: true; bottomMargin: 32
        property int columns: Math.max(1, Math.floor((width + 24) / (Theme.cardWidth + 24)))
        cellWidth: width / columns; cellHeight: cellWidth + 84
        model: root.result.items || []; ScrollBar.vertical: ScrollBar {}
        header: Loader { width: grid.width; height: 158; sourceComponent: controls }
        delegate: MediaCard {
            required property var modelData
            width: grid.cellWidth - 24; height: grid.cellHeight - 24; media: modelData
            onActivated: item => browseState.open(item)
            onPlayRequested: item => browseState.play(item)
        }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        onAtYEndChanged: if (atYEnd && root.result.cursor !== undefined && root.result.cursor !== null && !catalogState.busy) catalogState.more()
        footer: Button { text: "Load More"; visible: root.result.cursor !== undefined && root.result.cursor !== null; enabled: !catalogState.busy; onClicked: catalogState.more() }
    }
    ListView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: songs
        objectName: "librarySongs"
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        visible: root.rows; clip: true; bottomMargin: 32; model: root.result.items || []
        ScrollBar.vertical: ScrollBar {}
        header: Loader { width: songs.width; height: root.history ? 96 : 158; sourceComponent: controls }
        delegate: SongRow {
            required property var modelData
            width: songs.width; media: modelData
            onActivated: item => browseState.play(item)
        }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        onAtYEndChanged: if (atYEnd && root.result.cursor !== undefined && root.result.cursor !== null && !catalogState.busy) catalogState.more()
        footer: Button { text: "Load More"; visible: root.result.cursor !== undefined && root.result.cursor !== null; enabled: !catalogState.busy; onClicked: catalogState.more() }
    }
    Column {
        anchors.centerIn: parent; width: parent.width - 80; spacing: 20
        visible: !catalogState.busy && !(root.result.items || []).length
        Text { width: parent.width; text: catalogState.error || (!accountState.connected && !appState.fixtureMode ? "Connect YouTube Music to browse your library." : root.history ? "No listening history yet." : "Your " + libraryState.selectedSection.toLowerCase() + " will appear here."); textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 16; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
        Button { anchors.horizontalCenter: parent.horizontalCenter; text: "Retry"; visible: !!catalogState.error; onClicked: catalogState.refresh() }
        Button { anchors.horizontalCenter: parent.horizontalCenter; text: "Connect YouTube Music"; visible: !accountState.connected && !appState.fixtureMode; onClicked: appState.openAccount() }
    }
    BusyIndicator { anchors.centerIn: parent; running: catalogState.busy; visible: running }
    property int revision: -1
    function restoreScroll() {
        if (catalogState.busy || revision === catalogState.revision) return
        revision = catalogState.revision
        Qt.callLater(function() { var view = root.rows ? songs : grid; if (catalogState.hasScrollPosition) view.contentY = catalogState.scrollPosition; else view.positionViewAtBeginning() })
    }
    Component.onCompleted: restoreScroll()
    Connections { target: catalogState; function onChanged() { root.restoreScroll() } }
}
