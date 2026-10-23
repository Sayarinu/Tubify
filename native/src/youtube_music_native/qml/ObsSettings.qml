import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "obsSettings"
    property alias scrollView: scroll
    title: "OBS now playing"
    anchors.centerIn: Overlay.overlay
    width: Overlay.overlay ? Math.min(560, Overlay.overlay.width - 32) : 560
    height: Math.min(implicitHeight, Overlay.overlay ? Overlay.overlay.height - 48 : 560)
    modal: true; focus: true
    standardButtons: Dialog.Close
    background: Rectangle { color: themeState.background; border.color: themeState.border; radius: 12 }
    contentItem: ScrollView {
        id: scroll
        contentWidth: availableWidth; implicitHeight: body.implicitHeight; clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            id: body
            width: scroll.availableWidth; spacing: 16
            Label { Layout.fillWidth: true; text: "Add a Browser Source in OBS using a paired, read-only local URL. Enable Local API first. Music playback stays in the native app."; color: themeState.secondary; wrapMode: Text.Wrap }
            Label { text: "Layout"; color: themeState.foreground }
            ComboBox {
                objectName: "obsLayout"
                Layout.fillWidth: true
                model: [{name: "Full card", key: "full"}, {name: "Compact", key: "compact"}, {name: "Text only", key: "text"}, {name: "Badge", key: "badge"}, {name: "Poster", key: "poster"}, {name: "Ticker", key: "ticker"}, {name: "Scene display", key: "display"}]
                textRole: "name"; valueRole: "key"
                currentIndex: model.findIndex(item => item.key === obsState.options.layout)
                onActivated: obsState.setOption("layout", currentValue)
            }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                Repeater {
                    model: [{name: "Artwork", key: "art"}, {name: "Title", key: "title"}, {name: "Artist", key: "artist"}, {name: "Progress", key: "progress"}, {name: "Transparent page", key: "transparent"}]
                    CheckBox { required property var modelData; text: modelData.name; checked: obsState.options[modelData.key]; onToggled: obsState.setOption(modelData.key, checked) }
                }
            }
            RowLayout {
                Label { text: "Overlay scale"; color: themeState.foreground }
                SpinBox { from: 25; to: 400; stepSize: 25; value: Math.round(obsState.options.scale * 100); Accessible.name: "Overlay scale percent"; onValueModified: obsState.setOption("scale", value / 100) }
                Label { text: "%"; color: themeState.secondary }
            }
            CheckBox { text: "Hide while paused"; checked: obsState.options.paused === "hide"; onToggled: obsState.setOption("paused", checked ? "hide" : "show") }
            Label { Layout.fillWidth: true; text: "Suggested Browser Source size: " + obsState.suggestedSize + " pixels at 100%. Copy the URL again after changing layout options."; color: themeState.secondary; wrapMode: Text.Wrap }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                ThemeActionButton { objectName: "obsPreview"; text: "Preview in browser"; enabled: apiState.active; onClicked: obsState.preview() }
                ThemeActionButton { objectName: "obsGenerate"; text: obsState.hasClient ? "Replace source URL" : "Create source URL"; enabled: apiState.active; onClicked: obsState.generate() }
                ThemeActionButton { text: "Copy source URL"; enabled: apiState.active && obsState.hasSource; onClicked: obsState.copySource() }
                ThemeActionButton { text: "Revoke OBS access"; enabled: obsState.hasClient; onClicked: obsState.revoke() }
            }
            Label { Layout.fillWidth: true; text: "The URL grants access to current song information and artwork only. Keep it private. The source token is held in memory; after restarting, create a replacement URL or revoke the existing source."; color: themeState.secondary; wrapMode: Text.Wrap }
            Label { Layout.fillWidth: true; text: obsState.status; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
        }
    }
}
