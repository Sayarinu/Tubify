import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "lyricsSettingsDialog"
    anchors.centerIn: Overlay.overlay
    width: Overlay.overlay ? Math.min(560, Overlay.overlay.width - 48) : 560
    modal: true
    title: "Lyrics settings"
    standardButtons: Dialog.Close
    onOpened: lyricState.keyAction("status", "")
    onClosed: apiKey.clear()
    contentItem: ScrollView {
        id: optionsScroll
        objectName: "lyricsSettingsScroll"
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        implicitHeight: Overlay.overlay ? Math.min(620, Overlay.overlay.height - 180) : 620
        clip: true
        ColumnLayout {
            width: optionsScroll.availableWidth
            spacing: 12
            Label { Layout.fillWidth: true; text: "Native timed lyrics are always checked first. Native plain lyrics remain a fallback."; wrapMode: Text.Wrap; color: themeState.secondary }
            CheckBox { objectName: "externalLyricsOption"; text: "Use external lyric providers"; checked: lyricState.options.external; onClicked: lyricState.setOption("external", checked) }
            Label { Layout.fillWidth: true; text: "When enabled, song title, artist, album, duration or video ID are sent to the selected providers. Your YouTube session stays private."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            Repeater {
                model: lyricState.providers
                delegate: RowLayout {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    enabled: lyricState.options.external
                    CheckBox { Layout.fillWidth: true; text: modelData.name; checked: modelData.enabled; onClicked: lyricState.setProviderEnabled(modelData.id, checked) }
                    ThemeActionButton { text: "Up"; enabled: index > 0; Accessible.name: "Move " + modelData.name + " earlier"; onClicked: lyricState.moveProvider(modelData.id, -1) }
                    ThemeActionButton { text: "Down"; enabled: index < 2; Accessible.name: "Move " + modelData.name + " later"; onClicked: lyricState.moveProvider(modelData.id, 1) }
                }
            }
            CheckBox { text: "Allow approximate recording matches"; enabled: lyricState.options.external; checked: lyricState.options.approximate; onClicked: lyricState.setOption("approximate", checked) }
            Label { Layout.fillWidth: true; text: "Better Lyrics often cannot confirm a recording on cached responses. With approximate matches off, those results are skipped."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            CheckBox { text: "Use human YouTube captions as a fallback"; checked: lyricState.options.captions; onClicked: lyricState.setOption("captions", checked) }
            Label { Layout.fillWidth: true; text: "Only published human captions are used. Songs without them stay on the other lyric sources."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            Label { text: "Display"; font.bold: true; color: themeState.foreground }
            CheckBox { objectName: "lyricTimestampsOption"; text: "Show timestamps"; checked: lyricState.options.timestamps; onClicked: lyricState.setOption("timestamps", checked) }
            RowLayout {
                Label { text: "Timing style"; color: themeState.foreground }
                ComboBox {
                    objectName: "lyricStyleOption"
                    Layout.fillWidth: true
                    model: ["Line", "Word", "Syllable"]
                    currentIndex: ["line", "word", "syllable"].indexOf(lyricState.options.style)
                    onActivated: lyricState.setOption("style", ["line", "word", "syllable"][currentIndex])
                }
            }
            Label { Layout.fillWidth: true; text: "Word and syllable highlighting use supplied timestamps only. Other lyrics keep line highlighting."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            CheckBox { text: "Open lyrics when a song starts"; checked: lyricState.options.autoOpen; onClicked: lyricState.setOption("autoOpen", checked) }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            Label { text: "Better Lyrics API key"; font.bold: true; color: themeState.foreground }
            Label { Layout.fillWidth: true; text: "Cached songs need no key. Uncached songs require an existing key; the provider currently does not issue new keys."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            TextField { id: apiKey; objectName: "lyricApiKey"; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "Existing API key"; maximumLength: 2048; enabled: !lyricState.keyBusy; Accessible.name: "Better Lyrics API key" }
            RowLayout {
                ThemeActionButton { text: "Save key"; enabled: !!apiKey.text.trim() && !lyricState.keyBusy; onClicked: { lyricState.keyAction("save", apiKey.text); apiKey.clear() } }
                ThemeActionButton { text: "Remove key"; enabled: lyricState.hasKey && !lyricState.keyBusy; onClicked: lyricState.keyAction("clear", "") }
            }
            Label { Layout.fillWidth: true; text: lyricState.keyBusy ? "Checking system keyring…" : lyricState.keyMessage; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
        }
    }
}
