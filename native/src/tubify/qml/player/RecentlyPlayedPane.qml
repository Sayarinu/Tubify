import QtQuick
import QtQuick.Controls
import "../components"

// The queue panel's second tab: songs played earlier this session, newest first.
Item {
    id: root
    objectName: "recentlyPlayedPane"
    ListView {
        id: list
        objectName: "recentlyPlayedList"
        WheelScroll { view: list }
        anchors.fill: parent
        anchors.topMargin: 8
        anchors.leftMargin: 16; anchors.rightMargin: 16
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: playerState.recentTracks
        ScrollBar.vertical: ScrollBar { parent: root; anchors.left: list.right; anchors.top: list.top; anchors.bottom: list.bottom }
        delegate: Item {
            id: entry
            required property var modelData
            required property int index
            width: list.width
            height: 64
            HoverHandler { id: rowHover }
            Rectangle { anchors.fill: parent; radius: 6; color: rowHover.hovered || song.activeFocus ? themeState.hover : "transparent" }
            SongRow {
                id: song
                objectName: "recentlyPlayedSong-" + entry.index
                anchors.fill: parent
                queueRow: true
                media: entry.modelData
                onActivated: playerState.replay(entry.modelData)
            }
        }
    }
    Text {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.margins: 16; y: 24
        visible: list.count === 0
        text: "Songs you play will show up here"
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        color: themeState.secondary
        font.pixelSize: 13
    }
}
