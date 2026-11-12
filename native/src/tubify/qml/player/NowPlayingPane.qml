import QtQuick
import QtQuick.Controls
import "../components"

// The now-playing side panel: artwork, song and a preview of the first artist.
Item {
    id: root
    objectName: "nowPlayingPane"
    ScrollView {
        id: scroller
        objectName: "nowPlayingScroll"
        WheelScroll { view: scroller.contentItem }
        anchors.fill: parent
        anchors.leftMargin: 16; anchors.rightMargin: 16
        visible: playerState.hasTrack
        clip: true
        contentWidth: availableWidth
        contentHeight: details.height + 32
        NowPlayingDetails { id: details; y: 16; width: scroller.availableWidth }
    }
    Text {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.margins: 16; y: 16
        visible: !playerState.hasTrack
        text: "Choose a song to start listening"
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        color: themeState.secondary
        font.pixelSize: 13
    }
}
