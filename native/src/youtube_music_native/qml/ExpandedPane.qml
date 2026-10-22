import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    objectName: "expandedPlayer"
    Item {
        id: artworkPane
        width: parent.width * (root.width < 1000 ? 0.40 : 0.48)
        height: parent.height
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter; y: 32
            width: 120; height: 32; radius: 16; color: themeState.hover
            Text { anchors.centerIn: parent; text: "Now playing"; color: themeState.foreground; font.pixelSize: 14 }
        }
        Cover {
            largeArtwork: true
            media: playerState.currentTrack
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.max(120, Math.min(artworkPane.width - 112, artworkPane.height - 144))
            height: width
            y: 64 + (artworkPane.height - 64 - height) / 2
            source: playerState.currentTrack.largeThumbnail || playerState.currentTrack.thumbnail || ""
            mediaKey: playerState.currentTrack.videoId || playerState.currentTrack.id || ""
            accent: playerState.currentTrack.accent || themeState.selected
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
            width: 232; height: 48
            anchors.horizontalCenter: parent.horizontalCenter
            currentIndex: appState.playerTab === "Lyrics" ? 1 : 0
            background: Rectangle { color: "transparent" }
            Repeater {
                model: ["Up next", "Lyrics"]
                TabButton {
                    required property string modelData
                    text: modelData.toUpperCase()
                    width: 112; height: 36
                    font.pixelSize: 14; font.bold: true
                    onClicked: appState.setPlayerTab(modelData)
                    contentItem: Text { text: parent.text; color: parent.checked ? themeState.foreground : themeState.secondary; font: parent.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle {
                        radius: 18
                        color: parent.checked ? themeState.surface : parent.hovered ? themeState.hover : "transparent"
                        border.width: 1
                        border.color: parent.checked || parent.visualFocus ? themeState.accent : themeState.border
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
                    id: queuePageRoot
                    property var draggedTrack: ({})
                    Item {
                        id: autoplayHeader
                        width: parent.width; height: 112
                        Column {
                            y: 22; width: parent.width - 68; spacing: 4
                            Text { text: "Autoplay"; color: themeState.foreground; font.pixelSize: 14 }
                            Text { width: parent.width; text: "Add similar music"; color: themeState.secondary; font.pixelSize: 12; elide: Text.ElideRight }
                        }
                        Switch {
                            id: autoplaySwitch
                            anchors.right: parent.right; y: 16
                            checked: playerState.autoplay; Accessible.name: "Autoplay similar music"
                            onClicked: playerState.toggleAutoplay()
                            indicator: Rectangle {
                                implicitWidth: 40; implicitHeight: 24; x: autoplaySwitch.leftPadding; y: (autoplaySwitch.height - height) / 2
                                radius: 12; color: autoplaySwitch.checked ? themeState.accent : themeState.border
                                border.width: autoplaySwitch.visualFocus ? 2 : 0; border.color: themeState.foreground
                                Rectangle { x: autoplaySwitch.checked ? parent.width - width - 3 : 3; y: 3; width: 18; height: 18; radius: 9; color: autoplaySwitch.checked ? themeState.onAccent : themeState.secondary }
                            }
                        }
                    }
                    Button {
                        objectName: "clearQueuedSongs"
                        text: "Clear Queue"
                        visible: playerState.manualCount > 0
                        enabled: !browseState.queueBusy
                        height: 36
                        leftPadding: 16; rightPadding: 16
                        anchors.right: parent.right; y: 70
                        palette.buttonText: themeState.foreground
                        onClicked: playerState.clearManualQueue()
                        background: Rectangle {
                            radius: 18
                            color: parent.down ? themeState.border : parent.hovered ? themeState.hover : themeState.surface
                            border.color: parent.visualFocus ? themeState.accent : themeState.border
                        }
                    }
                    ListView {
                        id: queue
                        objectName: "queueList"
                        anchors.top: autoplayHeader.bottom; anchors.bottom: parent.bottom; width: parent.width
                        clip: true; boundsBehavior: Flickable.StopAtBounds
                        model: playerState.entries
                        section.property: "group"
                        section.criteria: ViewSection.FullString
                        section.delegate: Item {
                            required property string section
                            objectName: "expandedQueueSectionHeader-" + section
                            width: queue.width; height: 56
                            Rectangle {
                                anchors.fill: parent; anchors.margins: 2; radius: 8
                                visible: queue.dropToManual && queue.dropSection === section
                                color: themeState.selected; border.color: themeState.accent; border.width: 1
                            }
                            Column {
                                anchors.centerIn: parent
                                width: parent.width - 24
                                spacing: 4
                                Text {
                                    width: parent.width
                                    text: queue.dropToManual && queue.dropSection === section ? "Add To Queue" : section
                                    textFormat: Text.PlainText; elide: Text.ElideRight
                                    color: themeState.accent; font.pixelSize: 14; font.bold: true
                                    horizontalAlignment: queue.dropToManual && queue.dropSection === section ? Text.AlignHCenter : Text.AlignLeft
                                }
                                Text {
                                    width: parent.width
                                    visible: queue.dropToManual && queue.dropSection === section
                                    text: "Drop Here To Add This Song"
                                    color: themeState.secondary; font.pixelSize: 12
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }
                        property string focusKey: ""
                        property string restoreKey: ""
                        property string draggingKey: ""
                        property string dropKey: ""
                        property int dropIndex: -1
                        property bool dropAfter: false
                        property bool dropToManual: false
                        property string dropSection: ""
                        property point dragPosition: Qt.point(0, 0)
                        property bool browsingHistory: false
                        property bool positioningForPlayback: false
                        property real previousContentY: 0
                        property string lastCurrentKey: ""
                        property int lastHistoryCount: 0
                        function syncPlaybackPosition() {
                            var rows = playerState.entries
                            var currentIndex = -1
                            var historyCount = 0
                            var currentKey = ""
                            for (var i = 0; i < rows.length; i++) {
                                if (rows[i].group === "Previously played") historyCount++
                                if (rows[i].group === "Now playing") { currentIndex = i; currentKey = rows[i].key }
                            }
                            var playbackMoved = currentKey !== lastCurrentKey || historyCount !== lastHistoryCount
                            lastCurrentKey = currentKey
                            lastHistoryCount = historyCount
                            if (playbackMoved && !browsingHistory && currentIndex >= 0) {
                                positioningForPlayback = true
                                Qt.callLater(function() {
                                    queue.positionViewAtIndex(currentIndex, ListView.Beginning)
                                    queue.positioningForPlayback = false
                                })
                            }
                        }
                        onContentYChanged: {
                            if (!positioningForPlayback) {
                                if (contentY < previousContentY) browsingHistory = true
                                else if (contentY > previousContentY) browsingHistory = false
                            }
                            previousContentY = contentY
                        }
                        function manualDropSectionAt(contentY) {
                            var rows = playerState.entries
                            var targetIndex = -1
                            for (var i = 0; i < rows.length; i++) {
                                if (rows[i].group === "Next in queue") { targetIndex = i; break }
                            }
                            if (targetIndex < 0) {
                                for (var j = 0; j < rows.length; j++) {
                                if (rows[j].group !== "Now playing" && rows[j].group !== "Previously played") { targetIndex = j; break }
                                }
                            }
                            if (targetIndex < 0) return ""
                            var targetGroup = rows[targetIndex].group
                            var firstRow = queue.itemAtIndex(targetIndex)
                            if (firstRow) {
                                var firstRowY = queue.contentItem.mapFromItem(firstRow, 0, 0).y
                                return contentY >= firstRowY - 56 && contentY <= firstRowY ? targetGroup : ""
                            }
                            return ""
                        }
                        function updateDrag(sceneX, sceneY) {
                            var point = queue.mapFromItem(null, sceneX, sceneY)
                            dragPosition = queuePageRoot.mapFromItem(null, sceneX, sceneY)
                            var contentY = point.y + queue.contentY
                            dropSection = manualDropSectionAt(contentY)
                            dropToManual = dropSection.length > 0
                            if (dropToManual) {
                                dropKey = ""
                                dropIndex = -1
                                dropAfter = false
                                return
                            }
                            var destination = queue.indexAt(point.x + queue.contentX, point.y + queue.contentY)
                            if (destination < 0 || destination >= playerState.entries.length) {
                                dropKey = ""
                                dropIndex = -1
                                return
                            }
                            dropKey = playerState.entries[destination].key
                            dropIndex = destination
                            var targetItem = queue.itemAtIndex(destination)
                            dropAfter = !!targetItem && point.y + queue.contentY >= targetItem.y + targetItem.height / 2
                        }
                        function beginDrag(track, sceneX, sceneY) {
                            draggingKey = track.key
                            queuePageRoot.draggedTrack = track
                            updateDrag(sceneX, sceneY)
                        }
                        function finishDrag(sourceKey) {
                            if (!sourceKey || !draggingKey) return
                            var targetKey = dropKey
                            var destination = dropIndex >= 0 ? playerState.entries[dropIndex] : null
                            var manualHeaderTarget = dropToManual
                            var addToManual = manualHeaderTarget || !!destination && destination.group === "Next in queue"
                            draggingKey = ""
                            dropKey = ""
                            dropIndex = -1
                            dropToManual = false
                            dropSection = ""
                            queuePageRoot.draggedTrack = ({})
                            if (addToManual) playerState.moveToManual(sourceKey, manualHeaderTarget ? "" : targetKey, dropAfter)
                            else if (targetKey) playerState.moveToKey(sourceKey, targetKey)
                        }
                        ScrollBar.vertical: ScrollBar {}
                        delegate: FocusScope {
                            id: queueEntry
                            required property var modelData
                            required property int index
                            width: queue.width; height: 64
                            opacity: queue.draggingKey === queueEntry.modelData.key ? 0.38 : 1
                            property bool dropTarget: queue.dropIndex === queueEntry.index && queue.draggingKey !== queueEntry.modelData.key
                            function focusEntry() { song.forceActiveFocus() }
                            HoverHandler { id: rowHover }
                            property bool rowHovered: rowHover.hovered
                            Rectangle {
                                objectName: "expandedQueueRowHighlight-" + queueEntry.modelData.key
                                anchors.fill: parent; radius: 4
                                color: queueEntry.dropTarget ? themeState.selected : queueEntry.modelData.current || rowHover.hovered || queueEntry.activeFocus ? themeState.hover : "transparent"
                                border.color: queueEntry.dropTarget ? themeState.accent : rowHover.hovered || queueEntry.activeFocus ? themeState.border : "transparent"
                                border.width: queueEntry.dropTarget || rowHover.hovered || queueEntry.activeFocus ? 1 : 0
                            }
                            Rectangle {
                                objectName: "expandedQueueDropBefore-" + queueEntry.modelData.key
                                z: 2
                                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                height: 3; color: themeState.accent
                                visible: queue.dropIndex === queueEntry.index && !queue.dropAfter && queue.draggingKey !== queueEntry.modelData.key
                            }
                            Rectangle {
                                objectName: "expandedQueueDropAfter-" + queueEntry.modelData.key
                                z: 2
                                anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                                height: 3; color: themeState.accent
                                visible: queue.dropIndex === queueEntry.index && queue.dropAfter && queue.draggingKey !== queueEntry.modelData.key
                            }
                            Rectangle {
                                z: 1
                                anchors.fill: parent; radius: 4
                                color: "transparent"; border.color: themeState.accent; border.width: 1
                                visible: queueEntry.dropTarget
                            }
                            SongRow {
                                id: song
                                focus: true
                                objectName: "queueSong-" + queueEntry.modelData.key
                                anchors.fill: parent; anchors.rightMargin: 28
                                reorderable: !!queueEntry.modelData.movable
                                queueRow: true
                                media: queueEntry.modelData
                                menuContext: ({queueKey: queueEntry.modelData.key})
                                onActivated: playerState.selectKey(queueEntry.modelData.key)
                                onReorderDragStarted: (sceneX, sceneY) => queue.beginDrag(queueEntry.modelData, sceneX, sceneY)
                                onReorderDragMoved: (sceneX, sceneY) => queue.updateDrag(sceneX, sceneY)
                                onReorderDragFinished: () => queue.finishDrag(queueEntry.modelData.key)
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
                                width: 28; visible: !!queueEntry.modelData.movable; iconName: "drag"; iconSize: 20
                                background: Rectangle { radius: width / 2; color: "transparent" }
                                tip: "Reorder song; Alt+Up or Alt+Down also moves it"
                                onClicked: appState.showMenu(queueEntry.modelData, {queueKey: queueEntry.modelData.key})
                                DragHandler {
                                    id: drag
                                    target: null
                                    onCentroidChanged: if (active) queue.updateDrag(centroid.scenePosition.x, centroid.scenePosition.y)
                                    onActiveChanged: {
                                        if (active) queue.beginDrag(queueEntry.modelData, centroid.scenePosition.x, centroid.scenePosition.y)
                                        else queue.finishDrag(queueEntry.modelData.key)
                                    }
                                }
                            }
                        }
                        Text { anchors.centerIn: parent; width: parent.width; visible: queue.count === 0; text: "Your queue is empty"; color: themeState.secondary; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
                        Connections {
                            target: playerState
                            function onChanged() {
                                queue.syncPlaybackPosition()
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
                        Component.onCompleted: {
                            lastCurrentKey = ""
                            Qt.callLater(syncPlaybackPosition)
                        }
                    }
                    QueueDragPreview {
                        dragging: queue.draggingKey.length > 0
                        track: queuePageRoot.draggedTrack
                        position: queue.dragPosition
                    }
                }
            }
        }
    }
}
