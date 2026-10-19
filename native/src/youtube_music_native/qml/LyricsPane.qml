import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    objectName: "lyricsPane"
    Column {
        anchors.centerIn: parent; width: parent.width; spacing: 16
        visible: lyricState.busy || !!lyricState.error || !lyricState.data.available
        BusyIndicator { anchors.horizontalCenter: parent.horizontalCenter; running: lyricState.busy; visible: running }
        Text { width: parent.width; text: lyricState.busy ? "Loading lyrics…" : lyricState.error || "Lyrics aren’t available for this song."; textFormat: Text.PlainText; color: Theme.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 15 }
        Button { anchors.horizontalCenter: parent.horizontalCenter; visible: !lyricState.busy; text: "Retry"; palette.windowText: "white"; onClicked: lyricState.refresh() }
    }
    ListView {
        id: lines
        objectName: "lyricLines"
        anchors.fill: parent; anchors.topMargin: 24
        visible: !lyricState.busy && !lyricState.error && !!lyricState.data.available
        clip: true; spacing: 8
        model: lyricState.data.lines || []
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        onDraggingChanged: if (dragging) resumeFollow.restart()
        Timer { id: resumeFollow; interval: 6000 }
        delegate: ItemDelegate {
            required property var modelData
            required property int index
            width: lines.width
            height: Math.max(32, label.implicitHeight + 12)
            padding: 6
            Accessible.name: modelData.text || "Pause"
            Accessible.description: lyricState.data.timed ? "Seek to this line" : ""
            activeFocusOnTab: !!lyricState.data.timed
            onClicked: lyricState.seekLine(index)
            contentItem: Text { id: label; text: parent.modelData.text; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: !lyricState.data.timed || parent.index === lyricState.currentLine ? "white" : "#aaaaaa"; font.family: Theme.bodyFont; font.bold: true; font.pixelSize: lyricState.data.timed ? 24 : 20 }
            background: Rectangle { color: parent.hovered && lyricState.data.timed ? "#202020" : "transparent"; border.color: parent.visualFocus ? "white" : "transparent"; border.width: 1; radius: 4 }
        }
        footer: Text { width: lines.width; topPadding: 24; bottomPadding: 16; text: lyricState.data.source || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.secondary; font.pixelSize: 12 }
        Connections {
            target: lyricState
            function onCurrentLineChanged() { if (!resumeFollow.running && lyricState.currentLine >= 0) lines.positionViewAtIndex(lyricState.currentLine, ListView.Center) }
        }
    }
}
