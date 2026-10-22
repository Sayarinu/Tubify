import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    objectName: "queuePane"
    property bool showCloseButton: true
    property real gutter: Theme.gutter(width)
    property var draggedTrack: ({})
    property string draggingKey: ""
    property string dropKey: ""
    property string dropTargetList: ""
    property int dropIndex: -1
    property bool dropAfter: false
    property bool dropToManual: false
    property string dropSection: ""
    property point dragPosition: Qt.point(0, 0)
    property point lastHandlePosition: Qt.point(0, 0)
    property var currentEntry: playerState.entries.find(entry => entry.group === "Now playing") || ({})
    property var queueEntries: playerState.entries.filter(entry => entry.group === "Next in queue")
    property var nextEntries: playerState.entries.filter(entry => entry.group !== "Now playing" && entry.group !== "Previously played" && entry.group !== "Next in queue")
    property var historyEntries: playerState.entries.filter(entry => entry.group === "Previously played")

    HoverHandler {
        enabled: root.draggingKey.length > 0
        onPointChanged: root.updateDrag(point.scenePosition.x, point.scenePosition.y)
    }
    function updateDrag(sceneX, sceneY) {
        dragPosition = root.mapFromItem(null, sceneX, sceneY)
        var addPoint = addToQueueDrop.mapFromItem(null, sceneX, sceneY)
        var inAddZone = addToQueueDrop.visible && addPoint.x >= 0 && addPoint.x <= addToQueueDrop.width && addPoint.y >= 0 && addPoint.y <= addToQueueDrop.height
        if (inAddZone) {
            dropToManual = true
            dropTargetList = ""
            dropTargetList = ""
            dropSection = "Queue"
            dropKey = ""
            dropIndex = -1
            dropAfter = false
            return
        }
        dropToManual = false
        dropSection = ""
        var targetList = null
        var rows = []
        var point = queueList.mapFromItem(null, sceneX, sceneY)
        if (point.x >= 0 && point.x <= queueList.width && point.y >= 0 && point.y <= queueList.height) {
            targetList = queueList
            rows = queueEntries
            dropTargetList = "queue"
        } else {
            point = nextList.mapFromItem(null, sceneX, sceneY)
            if (point.x >= 0 && point.x <= nextList.width && point.y >= 0 && point.y <= nextList.height) {
                targetList = nextList
                rows = nextEntries
                dropTargetList = "next"
            }
        }
        if (!targetList) {
            dropTargetList = ""
            dropKey = ""
            dropIndex = -1
            dropAfter = false
            return
        }
        var contentY = point.y + targetList.contentY
        var destination = targetList.indexAt(point.x + targetList.contentX, contentY)
        if (destination >= 0 && destination < rows.length) {
            dropKey = rows[destination].key
            dropIndex = destination
            var targetItem = targetList.itemAtIndex(destination)
            dropAfter = !!targetItem && contentY >= targetItem.y + targetItem.height / 2
        } else {
            dropKey = ""
            dropIndex = -1
            dropAfter = false
        }
    }

    function beginDrag(track, sceneX, sceneY) {
        draggingKey = track.key
        draggedTrack = track
        updateDrag(sceneX, sceneY)
    }

    function finishDrag(sourceKey, sceneX, sceneY) {
        if (!sourceKey || !draggingKey) return
        updateDrag(sceneX, sceneY)
        var rows = dropTargetList === "queue" ? queueEntries : nextEntries
        var destination = dropIndex >= 0 && dropIndex < rows.length ? rows[dropIndex] : null
        var targetKey = dropKey
        var addToManual = dropToManual || dropTargetList === "queue"
        var manualHeaderTarget = dropToManual
        var insertAfter = dropAfter
        draggingKey = ""
        dropKey = ""
        dropTargetList = ""
        dropIndex = -1
        dropToManual = false
        dropSection = ""
        draggedTrack = ({})
        if (addToManual) playerState.moveToManual(sourceKey, manualHeaderTarget ? "" : targetKey, insertAfter)
        else if (targetKey) playerState.moveToKey(sourceKey, targetKey)
    }

    Column {
        id: panels
        property real sectionSpace: Math.max(0, height - nowPanel.height - 3)
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: root.gutter
        anchors.rightMargin: root.gutter
        spacing: 0

        Item {
            id: nowPanel
            objectName: "queueNowPlayingPanel"
            width: panels.width
            height: 100
            Text {
                text: "Now Playing"
                color: themeState.accent
                font.pixelSize: 14
                font.bold: true
                anchors.left: parent.left
                anchors.verticalCenter: parent.top
                anchors.verticalCenterOffset: 18
            }
            IconButton {
                objectName: "queueCollapseButton"
                visible: root.showCloseButton
                anchors.right: parent.right
                anchors.verticalCenter: parent.top
                anchors.verticalCenterOffset: 18
                width: 36
                height: 36
                iconSize: 20
                iconName: "right"
                tip: "Collapse Queue Sidebar"
                onClicked: appState.toggleQueue()
            }
            SongRow {
                objectName: "queueSidebarSong-" + (root.currentEntry.key || "current")
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.topMargin: 36
                height: 64
                queueRow: true
                media: root.currentEntry
                menuContext: root.currentEntry.key ? ({queueKey: root.currentEntry.key}) : ({})
                onActivated: if (root.currentEntry.key) playerState.selectKey(root.currentEntry.key)
            }
        }

        Rectangle { width: panels.width; height: 1; color: themeState.border }

        Item {
            id: queuePanel
            objectName: "queuePanel"
            width: panels.width
            height: Math.min(panels.sectionSpace / 3, 44 + (playerState.manualCount === 0 ? 56 : playerState.manualCount * 64))
            Rectangle {
                id: queueHeading
                width: parent.width
                height: 44
                color: "transparent"
                objectName: "queueSectionHeading"
                Text {
                    text: "Queue"
                    color: themeState.accent
                    font.pixelSize: 14
                    font.bold: true
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                }
                Button {
                    objectName: "queueClearButton"
                    text: "Clear Queue"
                    visible: playerState.manualCount > 0
                    enabled: !browseState.queueBusy
                    height: 36
                    leftPadding: 16
                    rightPadding: 16
                    anchors.right: parent.right
                    anchors.rightMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    font.pixelSize: 14
                    palette.buttonText: themeState.foreground
                    background: Rectangle {
                        radius: 18
                        color: parent.down ? themeState.border : parent.hovered ? themeState.hover : themeState.surface
                        border.color: parent.visualFocus ? themeState.accent : themeState.border
                    }
                    onClicked: playerState.clearManualQueue()
                }
            }
            Item {
                id: addToQueueDrop
                objectName: "queueSidebarAddToQueueDrop"
                anchors.top: queueHeading.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 56
                visible: playerState.manualCount === 0
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 2
                    radius: 8
                    color: root.dropToManual ? themeState.selected : themeState.surface
                    border.color: root.dropToManual ? themeState.accent : themeState.border
                    border.width: root.dropToManual ? 2 : 1
                    Text {
                        anchors.centerIn: parent
                        text: root.dropToManual ? "Drop Here To Add This Song" : "+  Add To Queue · Drop Songs Here"
                        color: root.dropToManual ? themeState.accent : themeState.foreground
                        font.pixelSize: 13
                        font.bold: true
                    }
                }
                HoverHandler {
                    onPointChanged: if (root.draggingKey) root.updateDrag(point.scenePosition.x, point.scenePosition.y)
                }
            }
            ListView {
                id: queueList
                objectName: "pinnedQueueList"
                anchors.top: playerState.manualCount === 0 ? addToQueueDrop.bottom : queueHeading.bottom
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: root.queueEntries
                delegate: queueSongDelegate
                ScrollBar.vertical: ScrollBar { objectName: "queueSidebarScrollbar"; parent: queuePanel; anchors.left: queueList.right; anchors.top: queueList.top; anchors.bottom: queueList.bottom }
                Text {
                    anchors.centerIn: parent
                    text: "Queue Is Empty"
                    color: themeState.secondary
                    visible: queueList.count === 0
                    font.pixelSize: 13
                }
            }
        }

        Rectangle { width: panels.width; height: 1; color: themeState.border }

        Item {
            id: nextPanel
            objectName: "queueNextPanel"
            width: panels.width
            height: Math.max(0, (panels.sectionSpace - queuePanel.height) / 2)
            Rectangle {
                id: nextRowsHeading
                objectName: "queueNextHeading"
                width: parent.width
                height: 44
                color: "transparent"
                Text {
                    text: "Next"
                    color: themeState.accent
                    font.pixelSize: 14
                    font.bold: true
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            ListView {
                id: nextList
                objectName: "pinnedQueueNextList"
                anchors.top: nextRowsHeading.bottom
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: root.nextEntries
                delegate: queueSongDelegate
                ScrollBar.vertical: ScrollBar { objectName: "queueNextScrollbar"; parent: nextPanel; anchors.left: nextList.right; anchors.top: nextList.top; anchors.bottom: nextList.bottom }
                Text {
                    anchors.centerIn: parent
                    text: "No Upcoming Songs"
                    color: themeState.secondary
                    visible: nextList.count === 0
                    font.pixelSize: 13
                }
            }
        }

        Rectangle { width: panels.width; height: 1; color: themeState.border }

        Item {
            id: historyPanel
            objectName: "queuePreviousPanel"
            width: panels.width
            height: Math.max(0, (panels.sectionSpace - queuePanel.height) / 2)
            Rectangle {
                id: previousHeading
                width: parent.width
                height: 44
                color: "transparent"
                Text {
                    text: "Previously Played"
                    color: themeState.accent
                    font.pixelSize: 14
                    font.bold: true
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            ListView {
                id: historyList
                objectName: "queueHistoryList"
                anchors.top: previousHeading.bottom
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: root.historyEntries
                delegate: queueSongDelegate
                ScrollBar.vertical: ScrollBar { objectName: "queueHistoryScrollbar"; parent: historyPanel; anchors.left: historyList.right; anchors.top: historyList.top; anchors.bottom: historyList.bottom }
                Text {
                    anchors.centerIn: parent
                    text: "No Recently Played Songs"
                    color: themeState.secondary
                    visible: historyList.count === 0
                    font.pixelSize: 13
                }
            }
        }
    }

    Component {
        id: queueSongDelegate
        FocusScope {
            id: queueEntry
            required property var modelData
            required property int index
            property var listView: ListView.view
            width: listView.width
            height: 64
            opacity: root.draggingKey === queueEntry.modelData.key ? 0.38 : 1
            property bool dropTarget: (queueEntry.listView === queueList && root.dropTargetList === "queue" || queueEntry.listView === nextList && root.dropTargetList === "next") && root.dropIndex === queueEntry.index && root.draggingKey !== queueEntry.modelData.key
            function focusEntry() { song.forceActiveFocus() }
            HoverHandler { id: rowHover }
            property bool rowHovered: rowHover.hovered
            Rectangle {
                objectName: "queueSidebarRowHighlight-" + queueEntry.modelData.key
                anchors.fill: parent
                radius: 4
                color: queueEntry.dropTarget ? themeState.selected : rowHover.hovered || queueEntry.activeFocus ? themeState.hover : "transparent"
                border.color: queueEntry.dropTarget ? themeState.accent : rowHover.hovered || queueEntry.activeFocus ? themeState.border : "transparent"
                border.width: queueEntry.dropTarget || rowHover.hovered || queueEntry.activeFocus ? 1 : 0
            }
            Rectangle {
                objectName: "queueSidebarDropBefore-" + queueEntry.modelData.key
                z: 2
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 3
                color: themeState.accent
                visible: (queueEntry.listView === queueList && root.dropTargetList === "queue" || queueEntry.listView === nextList && root.dropTargetList === "next") && root.dropIndex === queueEntry.index && !root.dropAfter && root.draggingKey !== queueEntry.modelData.key
            }
            Rectangle {
                objectName: "queueSidebarDropAfter-" + queueEntry.modelData.key
                z: 2
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 3
                color: themeState.accent
                visible: (queueEntry.listView === queueList && root.dropTargetList === "queue" || queueEntry.listView === nextList && root.dropTargetList === "next") && root.dropIndex === queueEntry.index && root.dropAfter && root.draggingKey !== queueEntry.modelData.key
            }
            Rectangle {
                z: 1
                anchors.fill: parent
                radius: 4
                color: "transparent"
                border.color: themeState.accent
                border.width: 1
                visible: queueEntry.dropTarget
            }
            SongRow {
                id: song
                objectName: "queueSidebarSong-" + queueEntry.modelData.key
                focus: true
                anchors.fill: parent
                anchors.rightMargin: 28
                reorderable: !!queueEntry.modelData.movable
                queueRow: true
                media: queueEntry.modelData
                menuContext: ({queueKey: queueEntry.modelData.key})
                onActivated: {
                    if (queueEntry.modelData.group === "Previously played") playerState.selectHistoryKey(queueEntry.modelData.key)
                    else playerState.selectKey(queueEntry.modelData.key)
                }
                onReorderDragStarted: (sceneX, sceneY) => root.beginDrag(queueEntry.modelData, sceneX, sceneY)
                onReorderDragMoved: (sceneX, sceneY) => root.updateDrag(sceneX, sceneY)
                onReorderDragFinished: (sceneX, sceneY) => root.finishDrag(queueEntry.modelData.key, sceneX, sceneY)
                Keys.onDeletePressed: if (queueEntry.modelData.movable) playerState.removeKey(queueEntry.modelData.key)
                Keys.onUpPressed: event => {
                    if (queueEntry.modelData.movable && event.modifiers & Qt.AltModifier) playerState.moveKey(queueEntry.modelData.key, -1)
                    else { queueEntry.listView.decrementCurrentIndex(); if (queueEntry.listView.currentItem) queueEntry.listView.currentItem.focusEntry() }
                }
                Keys.onDownPressed: event => {
                    if (queueEntry.modelData.movable && event.modifiers & Qt.AltModifier) playerState.moveKey(queueEntry.modelData.key, 1)
                    else { queueEntry.listView.incrementCurrentIndex(); if (queueEntry.listView.currentItem) queueEntry.listView.currentItem.focusEntry() }
                }
                onActiveFocusChanged: if (activeFocus) { queueEntry.listView.currentIndex = queueEntry.index }
            }
            IconButton {
                id: handle
                objectName: "queueSidebarDrag-" + queueEntry.modelData.key
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: 28
                background: Rectangle { radius: width / 2; color: "transparent" }
                visible: !!queueEntry.modelData.movable
                iconName: "drag"
                iconSize: 20
                tip: "Reorder song; Alt+Up or Alt+Down also moves it"
                onClicked: appState.showMenu(queueEntry.modelData, {queueKey: queueEntry.modelData.key})
                DragHandler {
                    target: null
                    onCentroidChanged: if (active) { root.lastHandlePosition = centroid.scenePosition; root.updateDrag(root.lastHandlePosition.x, root.lastHandlePosition.y) }
                    onActiveChanged: {
                        if (active) { root.lastHandlePosition = centroid.scenePosition; root.beginDrag(queueEntry.modelData, root.lastHandlePosition.x, root.lastHandlePosition.y) }
                        else root.finishDrag(queueEntry.modelData.key, root.lastHandlePosition.x, root.lastHandlePosition.y)
                    }
                }
            }
        }
    }

    QueueDragPreview {
        objectName: "queueDragPreview"
        dragging: root.draggingKey.length > 0
        track: root.draggedTrack
        position: root.dragPosition
    }
}
