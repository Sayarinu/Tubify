import QtQuick

Item {
    id: root
    required property real panelWidth
    signal resized(real requestedWidth)
    signal finished()
    z: 10; x: -width / 2; width: 12
    anchors.top: parent.top; anchors.bottom: parent.bottom
    HoverHandler { id: hover; cursorShape: Qt.SizeHorCursor }
    Rectangle { anchors.centerIn: parent; width: 2; height: parent.height; color: themeState.accent; opacity: hover.hovered || mouse.pressed ? 0.9 : 0 }
    MouseArea {
        id: mouse
        anchors.fill: parent; cursorShape: Qt.SizeHorCursor; preventStealing: true
        property real startWidth: 0
        property real startX: 0
        onPressed: function(event) { startWidth = root.panelWidth; startX = mapToItem(null, event.x, event.y).x }
        onPositionChanged: function(event) { if (pressed) root.resized(startWidth - mapToItem(null, event.x, event.y).x + startX) }
        onReleased: root.finished()
    }
}
