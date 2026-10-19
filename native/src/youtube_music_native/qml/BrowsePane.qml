import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme

Item {
    id: root
    property real gutter: Theme.gutter(width)
    property var result: catalogState.data
    property bool landing: catalogState.route === "home" || catalogState.route === "explore"
    property bool songs: (root.result.items || []).length > 0 && (root.result.items || []).every(item => (item.kind || "song") === "song")
    function moodItems() {
        var values = []
        var groups = root.result.groups || {}
        for (var group in groups) {
            for (var i = 0; i < groups[group].length; i++) values.push(groups[group][i])
        }
        return values
    }
    property int revision: -1
    function restoreScroll() {
        if (catalogState.busy || revision === catalogState.revision) return
        revision = catalogState.revision
        Qt.callLater(function() {
            var view = sections.visible ? sections : songList.visible ? songList : collectionGrid
            if (catalogState.hasScrollPosition) view.contentY = catalogState.scrollPosition
            else view.positionViewAtBeginning()
        })
    }
    Component.onCompleted: restoreScroll()
    Connections { target: catalogState; function onChanged() { root.restoreScroll() } }
    ListView {
        id: sections
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        topMargin: catalogState.route === "home" ? 46 : 32
        clip: true; spacing: 80; boundsBehavior: Flickable.StopAtBounds
        visible: (root.result.shelves || []).length > 0
        model: root.result.shelves || []
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        ScrollBar.vertical: ScrollBar {}
        header: Item {
            width: sections.width
            height: catalogState.route === "home" ? 82 : catalogState.route === "explore" ? 144 : 112
            ListView {
                width: parent.width; height: 36; orientation: ListView.Horizontal; spacing: 12; clip: true
                visible: catalogState.route === "home"
                model: ["Energize", "Feel good", "Workout", "Relax", "Party", "Commute", "Romance", "Focus", "Sad"]
                delegate: Button {
                    id: mood
                    required property string modelData
                    text: modelData; height: 36; leftPadding: 13; rightPadding: 13
                    palette.buttonText: Theme.foreground
                    background: Rectangle { radius: 8; color: mood.hovered ? Theme.hover : Theme.surface; border.width: mood.visualFocus ? 2 : 0; border.color: "white" }
                    onClicked: browseState.homeMood(text)
                }
            }
            RowLayout {
                width: parent.width; spacing: 24; visible: catalogState.route === "explore"
                Repeater {
                    model: [{title: "New releases", action: "releases", icon: "music"}, {title: "Charts", action: "charts", icon: "shuffle"}, {title: "Moods & genres", action: "moods", icon: "explore"}]
                    delegate: Button {
                        id: category
                        required property var modelData
                        Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.preferredHeight: 60
                        background: Rectangle { radius: 6; color: category.hovered ? Theme.hover : Theme.surface; border.color: category.visualFocus ? Theme.accent : "transparent" }
                        contentItem: Row { spacing: 14; leftPadding: 16; topPadding: 16; Symbol { name: category.modelData.icon; width: 24; height: 24; color: Theme.secondary } Text { text: category.modelData.title; color: "white"; font.pixelSize: 16; font.bold: true } }
                        onClicked: browseState.shortcut(modelData.action)
                    }
                }
            }
            Column {
                width: parent.width; visible: !root.landing; spacing: 12
                Text { width: parent.width; text: root.result.title || ""; textFormat: Text.PlainText; color: "white"; font.family: Theme.headingFont; font.pixelSize: 32; font.bold: true; elide: Text.ElideRight }
            }
        }
        delegate: Shelf {
            required property var modelData
            width: sections.width
            section: modelData
            profile: accountState.profile
            onActivated: item => browseState.open(item)
            onPlayRequested: item => browseState.play(item)
            onMoreRequested: browseState.showShelf(modelData)
            onPlayAllRequested: browseState.playItems(modelData.items)
        }
        footer: Item {
            width: sections.width; height: 64
            Row { anchors.centerIn: parent; spacing: 16; Button { text: "More music"; visible: root.result.cursor !== undefined && root.result.cursor !== null; enabled: !catalogState.busy; onClicked: catalogState.more() } Button { text: "Refresh"; enabled: !catalogState.busy; onClicked: catalogState.refresh() } }
        }
    }

    ListView {
        id: songList
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        topMargin: 32; bottomMargin: 48; clip: true; visible: root.songs
        model: root.result.items || []; boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        header: Column {
            width: songList.width; spacing: 20; bottomPadding: 32
            Row {
                width: parent.width; spacing: 24
                Cover { width: 128; height: 128; source: root.result.thumbnail || ""; visible: source.length > 0 }
                Column {
                    width: parent.width - (root.result.thumbnail ? 152 : 0); spacing: 16
                    Text { width: parent.width; text: root.result.title || "Music"; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: "white"; font.family: Theme.headingFont; font.pixelSize: 32; font.bold: true }
                    Button { text: "Play all"; onClicked: browseState.playView() }
                }
            }
        }
        delegate: SongRow { required property int index; required property var modelData; width: songList.width; media: modelData; number: index + 1; onActivated: browseState.playAt(index) }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        onAtYEndChanged: if (atYEnd && root.result.cursor !== undefined && root.result.cursor !== null && !catalogState.busy) catalogState.more()
        footer: Button { text: "Load more"; visible: root.result.cursor !== undefined && root.result.cursor !== null; enabled: !catalogState.busy; onClicked: catalogState.more() }
    }

    GridView {
        id: collectionGrid
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        topMargin: 32; bottomMargin: 48; clip: true
        visible: !root.songs && (root.result.items || []).length > 0
        cellWidth: Theme.cardWidth + 24; cellHeight: Theme.cardHeight + 24; model: root.result.items || []
        ScrollBar.vertical: ScrollBar {}
        header: Column { width: collectionGrid.width; spacing: 20; bottomPadding: 32; Text { width: parent.width; text: root.result.title || "Music"; textFormat: Text.PlainText; wrapMode: Text.Wrap; font.family: Theme.headingFont; font.pixelSize: 32; font.bold: true; color: "white" } }
        delegate: MediaCard { required property var modelData; width: Theme.cardWidth; media: modelData; onActivated: item => browseState.open(item); onPlayRequested: item => browseState.play(item) }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        onAtYEndChanged: if (atYEnd && root.result.cursor !== undefined && root.result.cursor !== null && !catalogState.busy) catalogState.more()
        footer: Button { text: "Load more"; visible: root.result.cursor !== undefined && root.result.cursor !== null; enabled: !catalogState.busy; onClicked: catalogState.more() }
    }

    ScrollView {
        anchors.fill: parent; anchors.margins: root.gutter
        visible: catalogState.route === "moods" && root.moodItems().length > 0
        Flow {
            width: parent.width; spacing: 16
            Repeater { model: root.moodItems(); delegate: Button { required property var modelData; text: modelData.title || "Mood"; width: 180; height: 60; onClicked: browseState.mood(modelData) } }
        }
    }
    Column {
        anchors.centerIn: parent; width: Math.min(parent.width - 80, 480); spacing: 18
        visible: !catalogState.busy && !(root.result.items || []).length && !(root.result.shelves || []).length && !root.moodItems().length
        Text { width: parent.width; text: catalogState.error ? "Couldn’t load this page" : accountState.connected ? "No music here yet" : "Your music, ready when you are"; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.family: Theme.headingFont; font.pixelSize: 30; font.bold: true; color: "white" }
        Text { width: parent.width; text: catalogState.error || (accountState.connected ? "Refresh to check for music." : "Connect YouTube Music to browse your music and recommendations."); textFormat: Text.PlainText; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 15; color: Theme.secondary }
        Button { anchors.horizontalCenter: parent.horizontalCenter; text: accountState.connected ? "Retry" : "Connect YouTube Music"; onClicked: accountState.connected ? catalogState.refresh() : appState.openAccount() }
    }
    BusyIndicator { anchors.centerIn: parent; running: catalogState.busy; visible: running && !(root.result.items || []).length && !(root.result.shelves || []).length }
    Label { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: Math.min(600, root.width - 48); padding: 12; wrapMode: Text.Wrap; textFormat: Text.PlainText; text: browseState.message || catalogState.error || (root.result.stale ? "Showing saved music. Refresh when you’re online." : ""); visible: text.length > 0; color: Theme.secondary; background: Rectangle { color: Theme.surface; radius: 4 } }
}
