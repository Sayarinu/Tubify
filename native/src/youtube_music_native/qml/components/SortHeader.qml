import QtQuick
import QtQuick.Controls

// Column label that sorts the current collection: ascending, descending, then by number.
AbstractButton {
    id: root
    property string label: ""
    property string sortKey: ""
    readonly property bool active: catalogState.sortKey === sortKey
    implicitWidth: row.implicitWidth + 8
    implicitHeight: 32
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.ColumnHeader
    Accessible.name: "Sort by " + (sortKey === "number" ? "number" : label) + (active ? (catalogState.sortDescending ? ", descending" : ", ascending") : "")
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
            visible: root.active
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
