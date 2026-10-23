import QtQuick
import QtQuick.Controls

Item {
    id: root
    objectName: "queuePane"
    property bool showCloseButton: true
    property real gutter: 16
    property var draggedTrack: ({})
    property string draggingKey: ""
    property string dropKey: ""
    property string dropTargetList: ""
    property int dropIndex: -1
    property bool dropAfter: false
    property bool dropToManual: false
    property point dragPosition: Qt.point(0, 0)
    property point lastHandlePosition: Qt.point(0, 0)
    property var currentEntry: playerState.entries.find(entry => entry.current) || ({})
    property var queueEntries: playerState.entries.filter(entry => entry.group === "Next in queue")
    property var nextEntries: playerState.entries.filter(entry => !entry.current && entry.group !== "Next in queue")
    property var rows: [{rowType: "manualHeading"}].concat(queueEntries, [{rowType: "drop"}, {rowType: "sourceHeading"}], nextEntries.length ? nextEntries : [{rowType: "empty"}])

    function clearDrop() {
        dropKey = ""
        dropTargetList = ""
        dropIndex = -1
        dropAfter = false
        dropToManual = false
    }
    function updateDrag(sceneX, sceneY) {
        dragPosition = root.mapFromItem(null, sceneX, sceneY)
        clearDrop()
        var point = queueList.mapFromItem(null, sceneX, sceneY)
        if (point.x < 0 || point.x > queueList.width || point.y < 0 || point.y > queueList.height) return
        var contentY = point.y + queueList.contentY
        var index = queueList.indexAt(point.x + queueList.contentX, contentY)
        var row = index >= 0 ? rows[index] : null
        if (!row) return
        if (row.rowType === "drop" || row.rowType === "manualHeading") {
            dropToManual = true
            return
        }
        if (row.rowType || (draggedTrack.group === "Next in queue" && row.group !== "Next in queue")) return
        dropIndex = index
        dropKey = row.key
        dropTargetList = row.group === "Next in queue" ? "queue" : "next"
        var item = queueList.itemAtIndex(index)
        dropAfter = !!item && contentY >= item.y + item.height / 2
    }
    function beginDrag(track, sceneX, sceneY) {
        draggingKey = track.key
        draggedTrack = track
        updateDrag(sceneX, sceneY)
    }
    function appendToManual(key) {
        var last = queueEntries.length ? queueEntries[queueEntries.length - 1].key : ""
        playerState.moveToManual(key, last, true)
    }
    function finishDrag(sourceKey, sceneX, sceneY) {
        if (!sourceKey || !draggingKey) return
        updateDrag(sceneX, sceneY)
        var targetKey = dropKey
        var manual = dropToManual || dropTargetList === "queue"
        var append = dropToManual
        var after = dropAfter
        draggingKey = ""
        draggedTrack = ({})
        clearDrop()
        if (append) appendToManual(sourceKey)
        else if (manual) playerState.moveToManual(sourceKey, targetKey, after)
        else if (targetKey && targetKey !== sourceKey) {
            var from = nextEntries.findIndex(entry => entry.key === sourceKey)
            var to = nextEntries.findIndex(entry => entry.key === targetKey)
            var destination = to + (after ? 1 : 0) - (from < to ? 1 : 0)
            if (from >= 0 && destination >= 0 && destination < nextEntries.length) playerState.moveToKey(sourceKey, nextEntries[destination].key)
        }
    }
    HoverHandler {
        enabled: root.draggingKey.length > 0
        onPointChanged: root.updateDrag(point.scenePosition.x, point.scenePosition.y)
    }
    Timer {
        interval: 16
        repeat: true
        running: root.draggingKey.length > 0
        onTriggered: {
            var point = queueList.mapFromItem(root, root.dragPosition.x, root.dragPosition.y)
            if (point.x < 0 || point.x > queueList.width || point.y < 0 || point.y > queueList.height) return
            var delta = point.y < 32 ? -8 : point.y > queueList.height - 32 ? 8 : 0
            if (!delta) return
            queueList.contentY = Math.max(queueList.originY, Math.min(queueList.originY + Math.max(0, queueList.contentHeight - queueList.height), queueList.contentY + delta))
            var scene = root.mapToItem(null, root.dragPosition.x, root.dragPosition.y)
            root.updateDrag(scene.x, scene.y)
        }
    }

    Item {
        id: nowPanel
        objectName: "queueNowPlayingPanel"
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: root.gutter
        anchors.rightMargin: root.gutter
        height: 148
        Text {
            text: "Now playing"
            color: themeState.foreground
            font.pixelSize: 14
            font.bold: true
            y: 12
        }
        IconButton {
            objectName: "queueCollapseButton"
            visible: root.showCloseButton
            anchors.right: parent.right
            y: 2
            width: 36
            height: 36
            iconSize: 20
            iconName: "right"
            tip: "Close queue"
            onClicked: appState.toggleQueue()
        }
        SongRow {
            objectName: "queueSidebarSong-" + (root.currentEntry.key || "current")
            anchors.left: parent.left
            anchors.right: parent.right
            y: 36
            height: 64
            visible: playerState.hasTrack
            queueRow: true
            media: root.currentEntry
            menuContext: root.currentEntry.key ? ({queueKey: root.currentEntry.key}) : ({})
            onActivated: if (root.currentEntry.key) playerState.selectKey(root.currentEntry.key)
        }
        Text {
            x: 0; y: 54
            visible: !playerState.hasTrack
            text: "Choose a song to start listening"
            width: parent.width
            elide: Text.ElideRight
            color: themeState.secondary
            font.pixelSize: 13
        }
        Switch {
            objectName: "queueAutoplay"
            y: 104; width: parent.width; height: 36
            text: "Autoplay"
            checked: playerState.autoplay
            Accessible.name: "Autoplay similar music"
            onClicked: playerState.toggleAutoplay()
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: themeState.border }
    }

    ListView {
        id: queueList
        objectName: "queueUpcomingList"
        anchors.top: nowPanel.bottom
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: root.gutter
        anchors.rightMargin: root.gutter
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: root.rows
        // Avoid pending offscreen delegates when a dock or tray queue is destroyed.
        cacheBuffer: 0
        property string focusKey: ""
        property string restoreKey: ""
        function focusSong(index, direction) {
            while (index >= 0 && index < count && root.rows[index].rowType) index += direction
            if (index < 0 || index >= count) return
            currentIndex = index
            positionViewAtIndex(index, ListView.Contain)
            if (currentItem) currentItem.focusEntry()
        }
        function restoreFocus() {
            var key = restoreKey || focusKey
            restoreKey = ""
            var index = root.rows.findIndex(entry => entry.key === key)
            if (index >= 0) focusSong(index, 1)
        }
        Connections {
            target: playerState
            function onChanged() {
                if (queueList.restoreKey || (queueList.activeFocus && queueList.focusKey)) Qt.callLater(queueList.restoreFocus)
            }
        }
        ScrollBar.vertical: ScrollBar {
            objectName: "queueSidebarScrollbar"
            parent: root
            anchors.left: queueList.right
            anchors.top: queueList.top
            anchors.bottom: queueList.bottom
        }
        delegate: FocusScope {
            id: queueEntry
            required property var modelData
            required property int index
            property bool songRow: !modelData.rowType
            property bool dropTarget: root.dropIndex === index && root.draggingKey !== modelData.key
            property bool rowHovered: rowHover.hovered
            width: queueList.width
            height: songRow ? 64 : modelData.rowType === "drop" ? 56 : modelData.rowType === "empty" ? 72 : 44
            opacity: songRow && root.draggingKey === modelData.key ? 0.38 : 1
            function focusEntry() { if (songRow) song.forceActiveFocus() }
            HoverHandler { id: rowHover }
            Text {
                objectName: modelData.rowType === "manualHeading" ? "queueSectionHeading" : modelData.rowType === "sourceHeading" ? "queueNextHeading" : ""
                visible: modelData.rowType === "manualHeading" || modelData.rowType === "sourceHeading"
                text: modelData.rowType === "manualHeading" ? "Queued songs" : playerState.nextGroup
                textFormat: Text.PlainText
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - (clearQueue.visible ? clearQueue.width + 8 : 0)
                elide: Text.ElideRight
                color: themeState.foreground
                font.pixelSize: 14
                font.bold: true
            }
            Button {
                id: clearQueue
                objectName: modelData.rowType === "manualHeading" ? "queueClearButton" : ""
                visible: modelData.rowType === "manualHeading" && (playerState.manualCount > 0 || browseState.queueBusy)
                text: browseState.queueBusy ? "Cancel" : "Clear"
                Accessible.name: "Clear queued songs and cancel pending additions"
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                height: 32
                leftPadding: 12
                rightPadding: 12
                font.pixelSize: 13
                palette.buttonText: themeState.foreground
                background: Rectangle {
                    radius: 16
                    color: parent.down ? themeState.border : parent.hovered ? themeState.hover : themeState.surface
                    border.color: parent.visualFocus ? themeState.accent : themeState.border
                }
                onClicked: playerState.clearManualQueue()
            }
            Rectangle {
                objectName: modelData.rowType === "drop" ? "queueSidebarAddToQueueDrop" : ""
                visible: modelData.rowType === "drop"
                x: 0; y: 4
                width: parent.width; height: 48
                radius: 8
                color: root.dropToManual ? themeState.selected : themeState.surface
                border.color: root.dropToManual ? themeState.accent : themeState.border
                border.width: root.dropToManual ? 2 : 1
                Text {
                    anchors.fill: parent
                    anchors.margins: 8
                    text: root.dropToManual ? "Drop to queue" : "+  Drop songs here"
                    color: themeState.foreground
                    font.pixelSize: 13
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                Accessible.role: Accessible.StaticText
                Accessible.name: "Drop songs here to add them to the end of queued songs"
            }
            Text {
                visible: modelData.rowType === "empty"
                anchors.centerIn: parent
                text: "No upcoming songs"
                color: themeState.secondary
                font.pixelSize: 13
            }
            Rectangle {
                objectName: songRow ? "queueSidebarRowHighlight-" + modelData.key : ""
                visible: queueEntry.songRow
                anchors.fill: parent
                radius: 4
                color: queueEntry.dropTarget ? themeState.selected : rowHover.hovered || queueEntry.activeFocus ? themeState.hover : "transparent"
                border.color: queueEntry.dropTarget ? themeState.accent : rowHover.hovered || queueEntry.activeFocus ? themeState.border : "transparent"
                border.width: queueEntry.dropTarget || rowHover.hovered || queueEntry.activeFocus ? 1 : 0
            }
            Rectangle {
                objectName: songRow ? "queueSidebarDropBefore-" + modelData.key : ""
                z: 2
                width: parent.width; height: 3
                color: themeState.accent
                visible: queueEntry.songRow && queueEntry.dropTarget && !root.dropAfter
            }
            Rectangle {
                objectName: songRow ? "queueSidebarDropAfter-" + modelData.key : ""
                z: 2
                anchors.bottom: parent.bottom
                width: parent.width; height: 3
                color: themeState.accent
                visible: queueEntry.songRow && queueEntry.dropTarget && root.dropAfter
            }
            SongRow {
                id: song
                objectName: queueEntry.songRow ? "queueSidebarSong-" + queueEntry.modelData.key : ""
                visible: queueEntry.songRow
                focus: queueEntry.songRow
                anchors.fill: parent
                anchors.rightMargin: 28
                reorderable: queueEntry.songRow
                queueRow: true
                media: queueEntry.modelData
                menuContext: ({queueKey: queueEntry.modelData.key})
                onActivated: playerState.selectKey(queueEntry.modelData.key)
                onReorderDragStarted: (sceneX, sceneY) => root.beginDrag(queueEntry.modelData, sceneX, sceneY)
                onReorderDragMoved: (sceneX, sceneY) => root.updateDrag(sceneX, sceneY)
                onReorderDragFinished: (sceneX, sceneY) => root.finishDrag(queueEntry.modelData.key, sceneX, sceneY)
                Keys.onDeletePressed: {
                    var following = root.rows.slice(queueEntry.index + 1).find(entry => !!entry.key)
                    var preceding = root.rows.slice(0, queueEntry.index).reverse().find(entry => !!entry.key)
                    queueList.restoreKey = following ? following.key : preceding ? preceding.key : ""
                    playerState.removeKey(queueEntry.modelData.key)
                }
                Keys.onUpPressed: event => {
                    if (event.modifiers & Qt.AltModifier) { queueList.restoreKey = queueEntry.modelData.key; playerState.moveKey(queueEntry.modelData.key, -1) }
                    else queueList.focusSong(queueEntry.index - 1, -1)
                }
                Keys.onDownPressed: event => {
                    if (event.modifiers & Qt.AltModifier) { queueList.restoreKey = queueEntry.modelData.key; playerState.moveKey(queueEntry.modelData.key, 1) }
                    else queueList.focusSong(queueEntry.index + 1, 1)
                }
                Keys.onRightPressed: event => {
                    if (event.modifiers & Qt.AltModifier) { queueList.restoreKey = queueEntry.modelData.key; root.appendToManual(queueEntry.modelData.key) }
                    else event.accepted = false
                }
                onActiveFocusChanged: if (activeFocus) { queueList.currentIndex = queueEntry.index; queueList.focusKey = queueEntry.modelData.key }
            }
            IconButton {
                objectName: queueEntry.songRow ? "queueSidebarDrag-" + queueEntry.modelData.key : ""
                visible: queueEntry.songRow
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: 28
                background: Rectangle { color: "transparent" }
                iconName: "drag"
                iconSize: 20
                tip: "Reorder song: Alt+Up/Down; Alt+Right moves to queued songs"
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
