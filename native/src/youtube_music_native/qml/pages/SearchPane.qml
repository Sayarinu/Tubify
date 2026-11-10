import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme
import "../components"

Item {
    id: root
    property real gutter: Theme.gutter(width)
    // Next to an open panel, the panel's own gap replaces the right gutter.
    readonly property real rightGutter: appState.panel ? 0 : gutter
    // Do not incubate delegates for another route while the page is being replaced.
    readonly property bool current: catalogState.route === "search"
    property var result: current ? catalogState.data : ({})
    // "All" shows a grouped overview; a specific filter shows the full paged list.
    readonly property bool overview: !!root.result.groups && searchState.selectedFilter === "All"
    readonly property var groups: root.result.groups || ({})
    readonly property var sections: {
        if (!root.overview) return []
        var rows = []
        if (root.result.topResult && root.result.topResult.title) rows.push({ type: "top" })
        var shelves = [["artist", "Artists", "Artists"], ["album", "Albums", "Albums"], ["playlist", "Playlists", "Playlists"]]
        for (var i = 0; i < shelves.length; ++i) {
            var values = root.groups[shelves[i][0]] || []
            if (values.length) rows.push({ type: "shelf", filter: shelves[i][2], section: { title: shelves[i][1], items: values, layout: "cards" } })
        }
        return rows
    }
    property AutoPager pager: AutoPager { view: results; active: root.current && !root.overview; cursor: root.result.cursor }
    ListView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: results
        objectName: "searchResults"
        WheelScroll { view: results; onScrolled: catalogState.saveScroll(view.contentY) }
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        topMargin: 32; bottomMargin: 48; clip: true; model: root.overview ? root.sections : root.current ? catalogState.itemsModel : null
        ScrollBar.vertical: ScrollBar {}
        header: Column {
            width: results.width; spacing: 30; bottomPadding: 24
            Row {
                spacing: 12
                Repeater {
                    model: searchState.filters
                    delegate: FilterChip {
                        required property string modelData
                        text: modelData
                        selected: searchState.selectedFilter === modelData
                        onClicked: searchState.selectFilter(modelData)
                    }
                }
            }
            Text { width: parent.width; visible: !root.overview; text: "Results for “" + (root.result.title || appState.query) + "”"; textFormat: Text.PlainText; color: themeState.foreground; font.pixelSize: 28; font.bold: true }
        }
        delegate: Loader {
            required property var modelData
            width: results.width
            sourceComponent: !root.overview ? resultRow : modelData.type === "top" ? topSection : shelfSection
        }
        Component {
            id: resultRow
            SongRow { width: parent.width; media: parent.modelData; onActivated: item => browseState.open(item) }
        }
        Component {
            id: topSection
            Item {
                readonly property bool stacked: width < 760
                readonly property var songs: (root.groups.song || []).slice(0, 4)
                width: parent.width
                height: (stacked ? topColumn.height + songColumn.height + 24 : Math.max(topColumn.height, songColumn.height)) + 40
                Column {
                    id: topColumn
                    width: parent.stacked ? parent.width : Math.min(460, parent.width * 0.42)
                    spacing: 16
                    Text { text: "Top result"; color: themeState.foreground; font.pixelSize: 24; font.bold: true }
                    TopResultCard { id: top; width: parent.width; media: root.result.topResult || ({}) }
                }
                Column {
                    id: songColumn
                    objectName: "searchTopSongs"
                    x: parent.stacked ? 0 : topColumn.width + 24
                    y: parent.stacked ? topColumn.height + 24 : 0
                    width: parent.stacked ? parent.width : parent.width - x
                    spacing: 4
                    visible: parent.songs.length > 0
                    Item {
                        width: parent.width; height: 40
                        Text { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; text: "Songs"; color: themeState.foreground; font.pixelSize: 24; font.bold: true }
                        ThemeActionButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; implicitHeight: 32; text: "Show all"; visible: (root.groups.song || []).length > 4; onClicked: searchState.selectFilter("Songs") }
                    }
                    Repeater {
                        model: parent.parent.songs
                        SongRow { required property var modelData; width: songColumn.width; showDuration: true; media: modelData; onActivated: item => browseState.open(item) }
                    }
                }
            }
        }
        Component {
            id: shelfSection
            Shelf {
                width: parent.width
                height: implicitHeight + 40
                section: parent.modelData.section
                alwaysShowMore: true
                moreLabel: "Show all"
                onActivated: item => browseState.open(item)
                onPlayRequested: item => browseState.play(item)
                onMoreRequested: searchState.selectFilter(parent.modelData.filter)
            }
        }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        footer: Column {
            width: results.width
            // Unfiltered results open as a top result and shelves; filtered results are rows.
            LoadingSkeleton { width: parent.width; view: results; mode: searchState.selectedFilter === "All" ? "shelves" : "rows"; shelfSpacing: 40 }
        }
    }
    Column {
        anchors.centerIn: parent; width: parent.width - 80; spacing: 20
        visible: !catalogState.busy && !(root.result.items || []).length
        Text { width: parent.width; text: catalogState.error || "No results. Try another song, artist, album or playlist."; textFormat: Text.PlainText; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 16 }
        ThemeActionButton { anchors.horizontalCenter: parent.horizontalCenter; text: "Retry"; visible: !!catalogState.error; onClicked: catalogState.refresh() }
    }
    BusyIndicator { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 16; running: catalogState.busy; visible: running && (root.result.items || []).length > 0 }
    property int revision: -1
    function restoreScroll() {
        if (catalogState.busy || revision === catalogState.revision) return
        revision = catalogState.revision
        Qt.callLater(function() { if (catalogState.hasScrollPosition) results.contentY = catalogState.scrollPosition; else results.contentY = results.originY - results.topMargin })
    }
    Component.onCompleted: restoreScroll()
    Connections { target: catalogState; function onChanged() { root.restoreScroll() } }
}
