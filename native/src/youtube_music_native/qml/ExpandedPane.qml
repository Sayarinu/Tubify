import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    objectName: "expandedPlayer"
    Item {
        id: artworkPane
        width: parent.width * 0.625
        height: parent.height
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter; y: 32
            width: 76; height: 32; radius: 16; color: "#303030"
            Text { anchors.centerIn: parent; text: "Song"; color: "white"; font.pixelSize: 14 }
        }
        Cover {
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.max(120, Math.min(artworkPane.width - 112, artworkPane.height - 144))
            height: width
            y: 64 + (artworkPane.height - 64 - height) / 2
            source: playerState.currentTrack.thumbnail || ""
            accent: playerState.currentTrack.accent || "#29363b"
            radius: 4
            Accessible.role: Accessible.Graphic
            Accessible.name: "Artwork for " + (playerState.currentTrack.title || "current song")
        }
    }
    Item {
        id: details
        anchors.left: artworkPane.right; anchors.right: parent.right
        anchors.rightMargin: root.width > 800 ? 56 : 24
        anchors.top: parent.top; anchors.topMargin: 32
        anchors.bottom: parent.bottom; anchors.bottomMargin: 16
        TabBar {
            id: tabs
            width: parent.width; height: 48
            currentIndex: appState.playerTab === "Lyrics" ? 1 : 0
            background: Rectangle { color: "transparent"; Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border } }
            Repeater {
                model: ["Up next", "Lyrics"]
                TabButton {
                    required property string modelData
                    text: modelData.toUpperCase()
                    height: 48
                    font.pixelSize: 14; font.bold: true
                    onClicked: appState.setPlayerTab(modelData)
                    contentItem: Text { text: parent.text; color: parent.checked ? "white" : Theme.secondary; font: parent.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle {
                        color: parent.hovered ? "#202020" : "transparent"
                        border.width: parent.visualFocus ? 1 : 0; border.color: "white"
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: "white"; visible: parent.parent.checked }
                    }
                }
            }
        }
        Loader {
            anchors.top: tabs.bottom; anchors.bottom: parent.bottom
            width: parent.width
            sourceComponent: appState.playerTab === "Lyrics" ? lyricsPage : queuePage
            Component { id: lyricsPage; LyricsPane {} }
            Component {
                id: queuePage
                Item {
                    Item {
                        id: autoplayHeader
                        width: parent.width; height: 76
                        Column {
                            anchors.verticalCenter: parent.verticalCenter; width: parent.width - 68; spacing: 4
                            Text { text: "Autoplay"; color: "white"; font.pixelSize: 14 }
                            Text { width: parent.width; text: "Add similar music"; color: Theme.secondary; font.pixelSize: 12; elide: Text.ElideRight }
                        }
                        Switch { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; checked: playerState.autoplay; Accessible.name: "Autoplay similar music"; onClicked: playerState.toggleAutoplay() }
                    }
                    ListView {
                        id: queue
                        objectName: "queueList"
                        anchors.top: autoplayHeader.bottom; anchors.bottom: parent.bottom; width: parent.width
                        clip: true; boundsBehavior: Flickable.StopAtBounds
                        model: playerState.entries
                        property string focusKey: ""
                        property string restoreKey: ""
                        ScrollBar.vertical: ScrollBar {}
                        delegate: FocusScope {
                            id: queueEntry
                            required property var modelData
                            required property int index
                            width: queue.width; height: 64
                            function focusEntry() { song.forceActiveFocus() }
                            Rectangle { anchors.fill: parent; color: queueEntry.modelData.current ? "#292929" : "transparent" }
                            SongRow {
                                id: song
                                focus: true
                                objectName: "queueSong-" + queueEntry.modelData.key
                                anchors.fill: parent; anchors.rightMargin: 28
                                media: queueEntry.modelData
                                subtitle: queueEntry.modelData.artist || ""
                                menuContext: ({queueKey: queueEntry.modelData.key})
                                onActivated: playerState.selectKey(queueEntry.modelData.key)
                                Keys.onDeletePressed: playerState.removeKey(queueEntry.modelData.key)
                                Keys.onUpPressed: event => {
                                    if (event.modifiers & Qt.AltModifier) { queue.restoreKey = queueEntry.modelData.key; playerState.moveKey(queueEntry.modelData.key, -1) }
                                    else { queue.decrementCurrentIndex(); if (queue.currentItem) queue.currentItem.focusEntry() }
                                }
                                Keys.onDownPressed: event => {
                                    if (event.modifiers & Qt.AltModifier) { queue.restoreKey = queueEntry.modelData.key; playerState.moveKey(queueEntry.modelData.key, 1) }
                                    else { queue.incrementCurrentIndex(); if (queue.currentItem) queue.currentItem.focusEntry() }
                                }
                                onActiveFocusChanged: if (activeFocus) { queue.currentIndex = queueEntry.index; queue.focusKey = queueEntry.modelData.key }
                            }
                            IconButton {
                                id: handle
                                objectName: "queueDrag-" + queueEntry.modelData.key
                                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                width: 28; iconName: "drag"; iconSize: 20
                                tip: "Reorder song; Alt+Up or Alt+Down also moves it"
                                onClicked: appState.showMenu(queueEntry.modelData, {queueKey: queueEntry.modelData.key})
                                DragHandler {
                                    id: drag
                                    target: null
                                    property string movingKey: ""
                                    onActiveChanged: {
                                        if (active) movingKey = queueEntry.modelData.key
                                        else if (movingKey) {
                                            var point = queue.mapFromItem(null, centroid.scenePosition.x, centroid.scenePosition.y)
                                            var destination = queue.indexAt(point.x + queue.contentX, point.y + queue.contentY)
                                            if (destination >= 0 && destination < playerState.entries.length)
                                                playerState.moveToKey(movingKey, playerState.entries[destination].key)
                                            movingKey = ""
                                        }
                                    }
                                }
                            }
                        }
                        Text { anchors.centerIn: parent; width: parent.width; visible: queue.count === 0; text: "Your queue is empty"; color: Theme.secondary; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
                        Connections {
                            target: playerState
                            function onChanged() {
                                if (!queue.restoreKey && (!queue.activeFocus || !queue.focusKey)) return
                                var key = queue.restoreKey || queue.focusKey
                                queue.restoreKey = ""
                                Qt.callLater(function() {
                                    var rows = playerState.entries
                                    for (var i = 0; i < rows.length; i++) if (rows[i].key === key) {
                                        queue.currentIndex = i
                                        queue.positionViewAtIndex(i, ListView.Contain)
                                        if (queue.currentItem) queue.currentItem.focusEntry()
                                        break
                                    }
                                })
                            }
                        }
                    }
                }
            }
        }
    }
}
