import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

ToolButton {
    id: root
    property string iconName: "more"
    property string tip: ""
    property color iconColor: Theme.foreground
    property int iconSize: 24
    property bool outlined: false
    implicitWidth: 44
    implicitHeight: 44
    Accessible.name: tip
    ToolTip.text: tip
    ToolTip.visible: hovered && tip.length > 0
    ToolTip.delay: 600
    background: Rectangle {
        radius: width / 2
        color: root.down ? "#444444" : root.hovered ? Theme.hover : "transparent"
        border.width: root.visualFocus ? 2 : root.outlined ? 1 : 0
        border.color: root.visualFocus ? Theme.foreground : "#3a3a3a"
    }
    contentItem: Item {
        Symbol {
            anchors.centerIn: parent
            width: root.iconSize
            height: root.iconSize
            name: root.iconName
            color: root.enabled ? root.iconColor : "#666666"
        }
    }
}
