import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "shortcutSettings"
    title: "Global Shortcuts"
    property alias scrollView: shortcutScroll
    property var bindingRows: shortcutState.bindings
    modal: true
    anchors.centerIn: parent
    width: Math.min(660, parent.width - 32)
    height: Math.min(720, parent.height - 32)
    standardButtons: Dialog.Close
    background: Rectangle { color: themeState.background; border.color: themeState.border; radius: 12 }
    contentItem: ColumnLayout {
        spacing: 12
        CheckBox { objectName: "globalShortcutsEnabled"; text: "Enable global shortcuts"; checked: shortcutState.enabled; onToggled: shortcutState.setEnabled(checked) }
        Text { Layout.fillWidth: true; text: shortcutState.help; color: themeState.secondary; wrapMode: Text.Wrap; font.pixelSize: 12 }
        Text { objectName: "globalShortcutsStatus"; Layout.fillWidth: true; text: shortcutState.status; color: themeState.foreground; wrapMode: Text.Wrap }
        RowLayout {
            spacing: 8
            ThemeActionButton { text: "Retry registration"; enabled: shortcutState.enabled; onClicked: shortcutState.retry() }
            ThemeActionButton { text: "Desktop shortcuts…"; visible: shortcutState.canConfigure; onClicked: shortcutState.configure() }
            ThemeActionButton { objectName: "resetGlobalShortcuts"; text: "Reset defaults"; onClicked: shortcutState.reset() }
        }
        ScrollView {
            id: shortcutScroll
            Layout.fillWidth: true; Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            Column {
                width: parent.width
                spacing: 12
                Repeater {
                    model: root.bindingRows.length
                    delegate: Column {
                        required property int index
                        property var modelData: root.bindingRows[index]
                        width: parent.width
                        spacing: 4
                        Text { text: modelData.title; color: themeState.foreground; font.bold: true }
                        RowLayout {
                            width: parent.width; spacing: 8
                            TextField {
                                id: binding
                                objectName: "globalShortcut-" + modelData.id
                                Layout.fillWidth: true
                                text: modelData.binding; placeholderText: "Not assigned"; maximumLength: 80
                                Accessible.name: modelData.title + " global shortcut"
                                onAccepted: shortcutState.setBinding(modelData.id, text)
                            }
                            ThemeActionButton { objectName: "applyShortcut-" + modelData.id; text: "Apply"; Accessible.name: "Apply " + modelData.title + " global shortcut"; onClicked: shortcutState.setBinding(modelData.id, binding.text) }
                            ThemeActionButton { text: "Clear"; Accessible.name: "Clear " + modelData.title + " global shortcut"; enabled: !!modelData.binding; onClicked: shortcutState.setBinding(modelData.id, "") }
                        }
                        Text {
                            width: parent.width
                            text: modelData.error || (modelData.registered ? "Active: " + modelData.registered : "")
                            visible: !!text
                            wrapMode: Text.Wrap
                            color: modelData.error ? themeState.foreground : themeState.secondary
                            font.pixelSize: 12
                        }
                    }
                }
            }
        }
    }
}
