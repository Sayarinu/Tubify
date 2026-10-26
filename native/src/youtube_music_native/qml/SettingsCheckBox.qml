import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

CheckBox {
    id: root
    Layout.fillWidth: true
    implicitWidth: 240
    implicitHeight: Math.max(48, contentItem.implicitHeight + topPadding + bottomPadding)
    padding: 12
    spacing: 12
    Accessible.name: text
    Accessible.checkable: true
    contentItem: Text {
        text: root.text
        font.pixelSize: 14
        color: root.enabled ? themeState.foreground : themeState.secondary
        rightPadding: 36
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
    indicator: Rectangle {
        x: root.width - width - root.rightPadding
        y: (root.height - height) / 2
        implicitWidth: 24; implicitHeight: 24; radius: 12
        color: root.checked ? themeState.accent : themeState.background
        border.width: 1
        border.color: root.checked ? themeState.accent : themeState.secondary
        opacity: root.enabled ? 1 : 0.6
        Symbol { anchors.centerIn: parent; width: 16; height: 16; name: "check"; visible: root.checked; color: themeState.onAccent }
    }
    background: Rectangle {
        radius: 10
        color: root.down || root.checked ? themeState.selected : root.hovered ? themeState.hover : themeState.background
        border.width: root.visualFocus ? 2 : 1
        border.color: root.visualFocus || root.checked ? themeState.accent : themeState.border
    }
}
