import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

// One pill holding a few options; the chosen one is filled with the accent, which slides between them.
// options is a list of {value, label, description}; choosing one emits chosen(value) and leaves
// current for the owner to update.
Item {
    id: root
    property var options: []
    property string current: ""
    signal chosen(string value)
    readonly property int currentIndex: {
        for (var index = 0; index < options.length; index++)
            if (options[index].value === current) return index
        return -1
    }
    implicitHeight: 36
    implicitWidth: row.implicitWidth + 8
    Accessible.role: Accessible.Grouping
    function choose(index) {
        if (index >= 0 && index < options.length && index !== currentIndex) root.chosen(options[index].value)
    }
    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: themeState.surface
        border.width: 1; border.color: themeState.border
    }
    // The accent under the chosen option.
    Rectangle {
        id: thumb
        objectName: "segmentedToggleThumb"
        readonly property Item target: root.currentIndex >= 0 && repeater.count > root.currentIndex ? repeater.itemAt(root.currentIndex) : null
        visible: target !== null
        x: row.x + (target ? target.x : 0); y: row.y
        width: target ? target.width : 0; height: row.height
        radius: height / 2
        color: themeState.accent
        Behavior on x { enabled: !appState.reducedMotion; NumberAnimation { duration: Theme.motionMedium; easing.type: Easing.OutCubic } }
        Behavior on width { enabled: !appState.reducedMotion; NumberAnimation { duration: Theme.motionMedium; easing.type: Easing.OutCubic } }
    }
    Row {
        id: row
        x: 4; y: 4; height: root.height - 8
        Repeater {
            id: repeater
            model: root.options
            delegate: AbstractButton {
                id: option
                required property var modelData
                required property int index
                readonly property bool selected: index === root.currentIndex
                objectName: "segmentedToggleOption-" + modelData.value
                height: row.height
                width: label.implicitWidth + 32
                focusPolicy: Qt.StrongFocus
                hoverEnabled: true
                text: modelData.label
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label
                Accessible.checkable: true
                Accessible.checked: selected
                Accessible.description: modelData.description || ""
                ToolTip.text: modelData.description || ""
                ToolTip.visible: hovered && !!modelData.description
                ToolTip.delay: 600
                onClicked: root.choose(index)
                Keys.onLeftPressed: { root.choose(index - 1); if (index > 0) repeater.itemAt(index - 1).forceActiveFocus() }
                Keys.onRightPressed: { root.choose(index + 1); if (index + 1 < repeater.count) repeater.itemAt(index + 1).forceActiveFocus() }
                background: Rectangle {
                    radius: height / 2
                    color: !option.selected && option.hovered ? themeState.hover : "transparent"
                    border.width: option.visualFocus ? 2 : 0
                    border.color: option.selected ? themeState.foreground : themeState.accent
                }
                contentItem: Text {
                    id: label
                    text: option.text
                    textFormat: Text.PlainText
                    color: option.selected ? themeState.onAccent : themeState.foreground
                    font.pixelSize: Theme.textBody
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    Behavior on color { enabled: !appState.reducedMotion; ColorAnimation { duration: Theme.motionMedium } }
                }
            }
        }
    }
}
