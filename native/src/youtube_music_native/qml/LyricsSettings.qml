import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SettingsPage {
    id: root
    property alias scrollView: optionsScroll
    objectName: "lyricsSettingsDialog"
    title: "Lyrics"
    onOpenedChanged: if (opened) lyricState.keyAction("status", "")
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
            SettingsCheckBox { objectName: "externalLyricsOption"; text: "Use External Lyric Providers"; checked: lyricState.options.external; onClicked: lyricState.setOption("external", checked) }
            Label { Layout.fillWidth: true; text: "When enabled, song title, artist, album, duration or video ID are sent to the selected providers. Your YouTube session stays private."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            Repeater {
                model: lyricState.providers
                delegate: RowLayout {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    enabled: lyricState.options.external
                    SettingsCheckBox { Layout.fillWidth: true; text: modelData.name; checked: modelData.enabled; onClicked: lyricState.setProviderEnabled(modelData.id, checked) }
                    ThemeActionButton { text: "Up"; enabled: index > 0; Accessible.name: "Move " + modelData.name + " earlier"; onClicked: lyricState.moveProvider(modelData.id, -1) }
                    ThemeActionButton { text: "Down"; enabled: index < 2; Accessible.name: "Move " + modelData.name + " later"; onClicked: lyricState.moveProvider(modelData.id, 1) }
                }
            }
            SettingsCheckBox { text: "Allow Approximate Recording Matches"; enabled: lyricState.options.external; checked: lyricState.options.approximate; onClicked: lyricState.setOption("approximate", checked) }
            Label { Layout.fillWidth: true; text: "Better Lyrics often cannot confirm a recording on cached responses. With approximate matches off, those results are skipped."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            SettingsCheckBox { text: "Use Human YouTube Captions"; checked: lyricState.options.captions; onClicked: lyricState.setOption("captions", checked) }
            Label { Layout.fillWidth: true; text: "Only published human captions are used. Songs without them stay on the other lyric sources."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            Label { text: "Display"; font.bold: true; color: themeState.foreground }
            SettingsCheckBox { objectName: "lyricTimestampsOption"; text: "Show Timestamps"; checked: lyricState.options.timestamps; onClicked: lyricState.setOption("timestamps", checked) }
            RowLayout {
                Label { text: "Timing Style"; color: themeState.foreground }
                ComboBox {
                    objectName: "lyricStyleOption"
                    Layout.fillWidth: true
                    model: ["Line", "Word", "Syllable"]
                    currentIndex: ["line", "word", "syllable"].indexOf(lyricState.options.style)
                    onActivated: lyricState.setOption("style", ["line", "word", "syllable"][currentIndex])
                }
            }
            Label { Layout.fillWidth: true; text: "Word and syllable highlighting use supplied timestamps only. Other lyrics keep line highlighting."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            SettingsCheckBox { text: "Open Lyrics When a Song Starts"; checked: lyricState.options.autoOpen; onClicked: lyricState.setOption("autoOpen", checked) }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            Label { text: "Better Lyrics API Key"; font.bold: true; color: themeState.foreground }
            Label { Layout.fillWidth: true; text: "Cached songs need no key. Uncached songs require an existing key; the provider currently does not issue new keys."; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
            TextField { id: apiKey; objectName: "lyricApiKey"; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "Existing API key"; maximumLength: 2048; enabled: !lyricState.keyBusy; Accessible.name: "Better Lyrics API Key" }
            RowLayout {
                ThemeActionButton { text: "Save Key"; enabled: !!apiKey.text.trim() && !lyricState.keyBusy; onClicked: { lyricState.keyAction("save", apiKey.text); apiKey.clear() } }
                ThemeActionButton { text: "Remove Key"; enabled: lyricState.hasKey && !lyricState.keyBusy; onClicked: lyricState.keyAction("clear", "") }
            }
            Label { Layout.fillWidth: true; text: lyricState.keyBusy ? "Checking system keyring…" : lyricState.keyMessage; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 12 }
        }
    }
}
