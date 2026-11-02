import QtQuick
import QtQuick.Controls

// Column label that sorts the current collection: ascending, descending, then original order.
AbstractButton {
    id: root
    property string label: ""
    property string sortKey: ""
    // The "#" header (empty key) marks the original order and never shows a direction.
    readonly property bool active: catalogState.sortKey === sortKey
    readonly property bool directional: active && sortKey !== ""
    implicitWidth: row.implicitWidth + 8
    implicitHeight: 32
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.ColumnHeader
    Accessible.name: sortKey ? "Sort by " + label + (directional ? (catalogState.sortDescending ? ", descending" : ", ascending") : "") : "Original order"
    onClicked: catalogState.sortBy(sortKey)
    contentItem: Row {
        id: row
        spacing: 4
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.label
            color: root.active || root.hovered ? themeState.foreground : themeState.secondary
            font.pixelSize: 12; font.letterSpacing: 1; font.bold: root.active
        }
        Symbol {
            anchors.verticalCenter: parent.verticalCenter
            width: 14; height: 14
            visible: root.directional
            name: catalogState.sortDescending ? "down" : "up"
            color: themeState.accent
        }
    }
    background: Rectangle {
        radius: 6
        color: "transparent"
        border.width: root.visualFocus ? 2 : 0
        border.color: themeState.accent
    }
}
