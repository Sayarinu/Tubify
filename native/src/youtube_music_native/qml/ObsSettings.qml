import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SettingsPage {
    id: root
    objectName: "obsSettings"
    property alias scrollView: scroll
    title: "OBS Now Playing"
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
                model: [{name: "Full Card", key: "full"}, {name: "Compact", key: "compact"}, {name: "Text Only", key: "text"}, {name: "Badge", key: "badge"}, {name: "Poster", key: "poster"}, {name: "Ticker", key: "ticker"}, {name: "Scene Display", key: "display"}]
                textRole: "name"; valueRole: "key"
                currentIndex: model.findIndex(item => item.key === obsState.options.layout)
                onActivated: obsState.setOption("layout", currentValue)
            }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                Repeater {
                    model: [{name: "Artwork", key: "art"}, {name: "Title", key: "title"}, {name: "Artist", key: "artist"}, {name: "Progress", key: "progress"}, {name: "Transparent Page", key: "transparent"}]
                    SettingsCheckBox { required property var modelData; text: modelData.name; checked: obsState.options[modelData.key]; onToggled: obsState.setOption(modelData.key, checked) }
                }
            }
            RowLayout {
                Label { text: "Overlay Scale"; color: themeState.foreground }
                SpinBox { from: 25; to: 400; stepSize: 25; value: Math.round(obsState.options.scale * 100); Accessible.name: "Overlay scale percent"; onValueModified: obsState.setOption("scale", value / 100) }
                Label { text: "%"; color: themeState.secondary }
            }
            SettingsCheckBox { text: "Hide While Paused"; checked: obsState.options.paused === "hide"; onToggled: obsState.setOption("paused", checked ? "hide" : "show") }
            Label { Layout.fillWidth: true; text: "Suggested Browser Source size: " + obsState.suggestedSize + " pixels at 100%. Copy the URL again after changing layout options."; color: themeState.secondary; wrapMode: Text.Wrap }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                ThemeActionButton { objectName: "obsPreview"; text: "Preview in Browser"; enabled: apiState.active; onClicked: obsState.preview() }
                ThemeActionButton { objectName: "obsGenerate"; text: obsState.hasClient ? "Replace Source URL" : "Create Source URL"; enabled: apiState.active; onClicked: obsState.generate() }
                ThemeActionButton { text: "Copy Source URL"; enabled: apiState.active && obsState.hasSource; onClicked: obsState.copySource() }
                ThemeActionButton { text: "Revoke OBS Access"; enabled: obsState.hasClient; onClicked: obsState.revoke() }
            }
            Label { Layout.fillWidth: true; text: "The URL grants access to current song information and artwork only. Keep it private. The source token is held in memory; after restarting, create a replacement URL or revoke the existing source."; color: themeState.secondary; wrapMode: Text.Wrap }
            Label { Layout.fillWidth: true; text: obsState.status; visible: !!text; color: themeState.foreground; wrapMode: Text.Wrap }
        }
    }
}
