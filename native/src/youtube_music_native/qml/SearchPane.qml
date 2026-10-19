import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    property real gutter: Theme.gutter(width)
    property var result: catalogState.data
    ListView {
        id: results
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        topMargin: 32; bottomMargin: 48; clip: true; model: root.result.items || []
        ScrollBar.vertical: ScrollBar {}
        header: Column {
            width: results.width; spacing: 30; bottomPadding: 24
            Row {
                spacing: 12
                Repeater {
                    model: searchState.filters
                    delegate: Button {
                        id: filter
                        required property string modelData
                        text: modelData; height: 36
                        palette.buttonText: searchState.selectedFilter === text ? themeState.onAccent : themeState.foreground
                        background: Rectangle { radius: 8; color: searchState.selectedFilter === filter.text ? themeState.accent : filter.hovered ? themeState.hover : themeState.surface; border.color: filter.visualFocus ? themeState.accent : "transparent" }
                        onClicked: searchState.selectFilter(text)
                    }
                }
            }
            Text { width: parent.width; text: "Results for “" + (root.result.title || appState.query) + "”"; textFormat: Text.PlainText; color: themeState.foreground; font.family: Theme.headingFont; font.pixelSize: 28; font.bold: true }
        }
        delegate: SongRow {
            required property var modelData
            width: results.width; media: modelData
            onActivated: item => browseState.open(item)
        }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        onAtYEndChanged: if (atYEnd && root.result.cursor !== undefined && root.result.cursor !== null && !catalogState.busy) catalogState.more()
        footer: Button { text: "Load more"; visible: root.result.cursor !== undefined && root.result.cursor !== null; enabled: !catalogState.busy; onClicked: catalogState.more() }
    }
    Column {
        anchors.centerIn: parent; width: parent.width - 80; spacing: 20
        visible: !catalogState.busy && !(root.result.items || []).length
        Text { width: parent.width; text: catalogState.error || "No results. Try another song, artist, album or playlist."; textFormat: Text.PlainText; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 16 }
        Button { anchors.horizontalCenter: parent.horizontalCenter; text: "Retry"; visible: !!catalogState.error; onClicked: catalogState.refresh() }
    }
    BusyIndicator { anchors.centerIn: parent; running: catalogState.busy; visible: running }
    property int revision: -1
    function restoreScroll() {
        if (catalogState.busy || revision === catalogState.revision) return
        revision = catalogState.revision
        Qt.callLater(function() { if (catalogState.hasScrollPosition) results.contentY = catalogState.scrollPosition; else results.positionViewAtBeginning() })
    }
    Component.onCompleted: restoreScroll()
    Connections { target: catalogState; function onChanged() { root.restoreScroll() } }
}
