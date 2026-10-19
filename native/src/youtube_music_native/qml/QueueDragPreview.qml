import QtQuick
import QtQuick.Window

Item {
    id: root
    objectName: "queueDragPreview"
    property bool dragging: false
    property var track: ({})
    property point position: Qt.point(0, 0)
    property Item viewportItem: Window.window ? Window.window.contentItem : parent
    readonly property point viewportPosition: parent && viewportItem ? parent.mapToItem(viewportItem, position.x, position.y) : position
    x: {
        if (!parent || !viewportItem) return position.x + 16
        var targetX = viewportPosition.x + 16
        if (targetX + width > viewportItem.width - 8) targetX = viewportPosition.x - width - 16
        targetX = Math.max(8, Math.min(targetX, viewportItem.width - width - 8))
        return parent.mapFromItem(viewportItem, targetX, viewportPosition.y).x
    }
    y: {
        if (!parent || !viewportItem) return position.y + 16
        var targetY = viewportPosition.y + 16
        if (targetY + height > viewportItem.height - 8) targetY = viewportPosition.y - height - 16
        targetY = Math.max(8, Math.min(targetY, viewportItem.height - height - 8))
        return parent.mapFromItem(viewportItem, viewportPosition.x, targetY).y
    }
    width: 264
    height: 64
    z: 1000
    visible: dragging
    enabled: false

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: themeState.surface
        border.color: themeState.accent
        border.width: 2
        opacity: 0.97
    }
    Cover {
        x: 8
        anchors.verticalCenter: parent.verticalCenter
        width: 48
        height: 48
        radius: 6
        source: root.track.thumbnail || ""
        mediaKey: root.track.videoId || root.track.id || ""
        accent: themeState.selected
    }
    Column {
        anchors.left: parent.left
        anchors.leftMargin: 66
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4
        Text {
            width: parent.width
            text: root.track.title || ""
            textFormat: Text.PlainText
            color: themeState.foreground
            font.pixelSize: 13
            font.bold: true
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            text: root.track.artists && root.track.artists.length ? root.track.artists.map(artist => artist.name).join(" • ") : root.track.artist || ""
            textFormat: Text.PlainText
            color: themeState.secondary
            font.pixelSize: 12
            elide: Text.ElideRight
        }
    }
}
