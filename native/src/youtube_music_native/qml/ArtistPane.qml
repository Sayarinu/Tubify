import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    clip: true
    property var artist: catalogState.data
    property real gutter: Theme.gutter(width)
    property bool descriptionExpanded: false
    Image { id: hero; objectName: "artistHero"; y: (sections.headerItem ? sections.headerItem.y : 0) - sections.contentY; width: root.width; height: 400; source: root.artist.hero || ""; visible: !!root.artist.hero; asynchronous: true; fillMode: Image.PreserveAspectCrop; opacity: 0.45 }
    Rectangle { y: hero.y; width: root.width; height: 400; visible: !!root.artist.hero; gradient: Gradient { GradientStop { position: 0; color: "#00000000" } GradientStop { position: 1; color: themeState.background } } }
    ListView {
        id: sections
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        clip: true; spacing: 36; bottomMargin: 48
        model: root.artist.shelves || []; ScrollBar.vertical: ScrollBar {}
        header: Item {
            width: sections.width; height: summary.y + summary.height + 48
            Column {
                id: summary
                y: 224; width: parent.width
                Text { width: parent.width; text: root.artist.title || "Artist"; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.foreground; font.family: Theme.headingFont; font.pixelSize: root.width > 900 ? 48 : 36; font.bold: true }
                Text { text: root.artist.monthlyListeners ? root.artist.monthlyListeners + " monthly audience" : ""; textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 14; height: 17 }
                Item { width: 1; height: 16 }
                Text { width: Math.min(parent.width, 700); text: root.artist.subtitle || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: root.descriptionExpanded ? 1000 : 2; elide: Text.ElideRight; color: themeState.foreground; font.pixelSize: 14; lineHeight: 1.25 }
                Button { text: root.descriptionExpanded ? "LESS" : "MORE"; flat: true; palette.windowText: themeState.foreground; height: 24; leftPadding: 0; visible: !!root.artist.subtitle; onClicked: root.descriptionExpanded = !root.descriptionExpanded }
                Item { width: 1; height: 20 }
                Row {
                    spacing: 8
                    Button { id: shuffle; objectName: "artistShuffle"; text: "Shuffle"; height: 36; width: 136; enabled: !!root.artist.shuffleId; palette.buttonText: themeState.onAccent; background: Rectangle { radius: 18; color: shuffle.hovered ? themeState.accentHover : themeState.accent; border.width: shuffle.visualFocus ? 2 : 0; border.color: themeState.foreground } onClicked: browseState.startRadio(root.artist.shuffleId, true) }
                    Button { id: mix; objectName: "artistMix"; text: "Mix"; height: 36; width: 136; enabled: !!root.artist.radioId; palette.buttonText: themeState.onAccent; background: Rectangle { radius: 18; color: mix.hovered ? themeState.accentHover : themeState.accent; border.width: mix.visualFocus ? 2 : 0; border.color: themeState.foreground } onClicked: browseState.startRadio(root.artist.radioId, false) }
                    Button {
                        id: subscription
                        objectName: "artistSubscribe"
                        text: (root.artist.subscribed ? "Subscribed" : "Subscribe") + (root.artist.subscribers ? " " + root.artist.subscribers : "")
                        height: 36; leftPadding: 16; rightPadding: 16
                        visible: !!root.artist.subscriptionId
                        enabled: !actionsState.busy && (accountState.connected || appState.fixtureMode)
                        palette.buttonText: root.artist.subscribed ? themeState.foreground : themeState.accent
                        background: Rectangle { radius: 18; color: subscription.hovered ? themeState.surface : "transparent"; border.width: subscription.visualFocus ? 2 : 1; border.color: subscription.visualFocus ? themeState.foreground : root.artist.subscribed ? themeState.muted : themeState.accent }
                        onClicked: actionsState.set("artist_subscription", root.artist.subscriptionId, !root.artist.subscribed, catalogState.parameters.id)
                    }
                }
                Label { text: actionsState.message; visible: text.length > 0; color: themeState.secondary; wrapMode: Text.Wrap; width: parent.width }
            }
        }
        delegate: Loader {
            required property var modelData
            property var section: modelData
            width: sections.width
            sourceComponent: modelData.title === "Top songs" ? songSection : cardSection
            Component {
                id: songSection
                Column {
                    property var section: parent.section
                    width: parent.width
                    Text { text: "Top songs"; color: themeState.foreground; font.family: Theme.headingFont; font.pixelSize: 24; font.bold: true; height: 45 }
                    Repeater { model: parent.section.items; delegate: ArtistSongRow { required property var modelData; width: sections.width; media: modelData; onActivated: item => browseState.play(item) } }
                    Button { text: "More"; flat: true; palette.windowText: themeState.foreground; onClicked: browseState.openSection(parent.section) }
                }
            }
            Component { id: cardSection; Shelf { width: sections.width; section: parent.section; onActivated: item => browseState.open(item); onPlayRequested: item => browseState.play(item); onMoreRequested: browseState.openSection(section); onPlayAllRequested: browseState.playItems(section.items) } }
        }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
    }
    BusyIndicator { anchors.centerIn: parent; running: catalogState.busy; visible: running }
    RetryBanner { message: catalogState.error; busy: catalogState.busy; onRetry: catalogState.refresh() }
    property int revision: -1
    function restoreScroll() {
        if (catalogState.busy || revision === catalogState.revision) return
        revision = catalogState.revision
        Qt.callLater(function() { if (catalogState.hasScrollPosition) sections.contentY = catalogState.scrollPosition; else sections.positionViewAtBeginning() })
    }
    Component.onCompleted: restoreScroll()
    Connections { target: catalogState; function onChanged() { root.restoreScroll() } }
}
