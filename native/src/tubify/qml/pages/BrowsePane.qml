import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Theme.js" as Theme
import "../components"

Item {
    id: root
    objectName: "browsePane"
    property real gutter: Theme.gutter(width)
    // Next to an open panel, the panel's own gap replaces the right gutter.
    readonly property real rightGutter: appState.panel ? 0 : gutter
    // Do not incubate delegates for another route while the page is being replaced.
    readonly property bool current: ["album", "playlist", "artist", "search", "downloads", "history"].indexOf(catalogState.route) < 0 && catalogState.route.indexOf("library_") !== 0
    property var result: current ? catalogState.data : ({})
    property bool landing: catalogState.route === "home" || catalogState.route === "explore"
    property bool songs: (root.result.items || []).length > 0 && (root.result.items || []).every(item => (item.kind || "song") === "song")
    // While a page loads, the view its route will fill stays visible so its header shows above the skeleton.
    readonly property bool loading: catalogState.busy && !(root.result.items || []).length && !(root.result.shelves || []).length
    readonly property string loadingLayout: ["home", "explore", "charts"].indexOf(catalogState.route) >= 0 ? "shelves" : catalogState.route === "radio" ? "rows" : "grid"
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
            else view.contentY = view.originY - view.topMargin
        })
    }
    Component.onCompleted: restoreScroll()
    NumberAnimation { id: toTop; property: "contentY"; duration: Theme.duration(Theme.motionSlow, appState.reducedMotion); easing.type: Easing.OutCubic }
    Connections {
        target: catalogState
        function onChanged() { root.restoreScroll() }
        function onScrollToTopRequested() {
            var view = sections.visible ? sections : songList.visible ? songList : collectionGrid
            toTop.stop()
            toTop.target = view
            toTop.to = view.originY - view.topMargin
            toTop.start()
        }
    }
    property list<QtObject> pagers: [
        AutoPager { view: sections; active: root.current; cursor: root.result.cursor },
        AutoPager { view: songList; active: root.current; cursor: root.result.cursor },
        AutoPager { view: collectionGrid; active: root.current; cursor: root.result.cursor }
    ]
    ListView {
        // Route views may be replaced immediately; avoid unfinished offscreen delegates.
        cacheBuffer: 0
        id: sections
        WheelScroll { view: sections; onScrolled: catalogState.saveScroll(view.contentY) }
        objectName: "browseSections"
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        topMargin: catalogState.route === "home" || catalogState.route === "explore" ? 46 : 32
        clip: true; spacing: 80; boundsBehavior: Flickable.StopAtBounds
        visible: (root.result.shelves || []).length > 0 || root.loading && root.loadingLayout === "shelves"
        model: root.current ? catalogState.shelvesModel : null
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        ScrollBar.vertical: ScrollBar {
            objectName: "browseSectionsScrollbar"
            parent: root
            anchors.left: sections.right
            anchors.top: sections.top
            anchors.bottom: sections.bottom
        }
        header: Item {
            width: sections.width
            height: catalogState.route === "home" ? 82 : catalogState.route === "explore" ? 106 : 112
            EdgeArrows { objectName: "moodArrows"; target: moods; visible: moods.visible; height: 36 }
            ListView {
                // Route views may be replaced immediately; avoid unfinished offscreen delegates.
                cacheBuffer: 0
                id: moods
                objectName: "homeMoods"
                width: parent.width; height: 36; orientation: ListView.Horizontal; spacing: Theme.spacingMedium; clip: true
                boundsBehavior: Flickable.StopAtBounds
                visible: catalogState.route === "home"
                model: ["Energize", "Feel good", "Workout", "Relax", "Party", "Commute", "Romance", "Focus", "Sad"]
                delegate: FilterChip {
                    required property string modelData
                    text: modelData; choice: false; leftPadding: 16; rightPadding: 16
                    onClicked: browseState.homeMood(text)
                }
            }
            RowLayout {
                width: parent.width; spacing: 24; visible: catalogState.route === "explore"
                Repeater {
                    model: [{title: "New Releases", action: "releases", icon: "music"}, {title: "Charts", action: "charts", icon: "shuffle"}, {title: "Moods & Genres", action: "moods", icon: "explore"}]
                    delegate: Button {
                        id: category
                        required property var modelData
                        Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.preferredHeight: 60
                        background: Rectangle { radius: 14; color: category.hovered ? themeState.hover : themeState.surface; border.color: category.visualFocus ? themeState.accent : "transparent" }
                        contentItem: Row { spacing: 14; leftPadding: 16; topPadding: 16; Symbol { name: category.modelData.icon; width: 24; height: 24; color: themeState.secondary } Text { text: category.modelData.title; color: themeState.foreground; font.pixelSize: 16; font.bold: true } }
                        onClicked: browseState.shortcut(modelData.action)
                    }
                }
            }
            Column {
                width: parent.width; visible: !root.landing; spacing: Theme.spacingMedium
                Text { width: parent.width; text: root.result.title || ""; textFormat: Text.PlainText; color: themeState.foreground; font.pixelSize: 32; font.bold: true; elide: Text.ElideRight }
            }
        }
        delegate: Shelf {
            required property var modelData
            width: sections.width
            section: modelData
            profile: accountState.profile
            onActivated: item => browseState.open(item)
            onPlayRequested: item => browseState.play(item)
            onPlayAllRequested: browseState.playItems(mixed ? songItems : modelData.items)
        }
        footer: Column {
            width: sections.width
            LoadingSkeleton { width: parent.width; view: sections; mode: "shelves"; shelfSpacing: sections.spacing }
            Item { width: parent.width; height: 64 }
        }
    }

    ListView {

        // Route views may be replaced immediately; avoid unfinished offscreen delegates.

        cacheBuffer: 0
        id: songList
        WheelScroll { view: songList; onScrolled: catalogState.saveScroll(view.contentY) }
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        topMargin: 32; bottomMargin: 48; clip: true; visible: root.songs || root.loading && root.loadingLayout === "rows"
        model: root.current ? catalogState.itemsModel : null; boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {
            parent: root
            anchors.left: songList.right
            anchors.top: songList.top
            anchors.bottom: songList.bottom
        }
        header: Column {
            width: songList.width; spacing: 20; bottomPadding: 32
            Row {
                width: parent.width; spacing: 24
                Cover { width: 128; height: 128; source: root.result.thumbnail || ""; visible: source.length > 0 }
                Column {
                    width: parent.width - (root.result.thumbnail ? 152 : 0); spacing: Theme.spacingLarge
                    Text { width: parent.width; text: root.result.title || "Music"; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.foreground; font.pixelSize: 32; font.bold: true }
                    ThemeActionButton { text: "Play All"; primary: true; onClicked: browseState.playView() }
                }
            }
        }
        delegate: SongRow { required property int index; required property var modelData; width: songList.width; media: modelData; number: index + 1; onActivated: browseState.playAt(index) }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        footer: Column {
            width: songList.width
            LoadingSkeleton { width: parent.width; view: songList; mode: "rows"; textInset: 104 }
        }
    }

    GridView {

        // Route views may be replaced immediately; avoid unfinished offscreen delegates.

        cacheBuffer: 0
        id: collectionGrid
        WheelScroll { view: collectionGrid; onScrolled: catalogState.saveScroll(view.contentY) }
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.rightGutter
        topMargin: 32; bottomMargin: 48; clip: true
        visible: !root.songs && (root.result.items || []).length > 0 || root.loading && root.loadingLayout === "grid"
        cellWidth: Theme.cardWidth + 24; cellHeight: Theme.cardHeight + 24; model: root.current ? catalogState.itemsModel : null
        ScrollBar.vertical: ScrollBar {
            parent: root
            anchors.left: collectionGrid.right
            anchors.top: collectionGrid.top
            anchors.bottom: collectionGrid.bottom
        }
        header: Column { width: collectionGrid.width; spacing: 20; bottomPadding: 32; Text { width: parent.width; text: root.result.title || "Music"; textFormat: Text.PlainText; wrapMode: Text.Wrap; font.pixelSize: 32; font.bold: true; color: themeState.foreground } }
        delegate: MediaCard { required property var modelData; width: Theme.cardWidth; media: modelData; onActivated: item => browseState.open(item); onPlayRequested: item => browseState.play(item) }
        onContentYChanged: if (moving) catalogState.saveScroll(contentY)
        footer: Column {
            width: collectionGrid.width
            LoadingSkeleton { width: parent.width; view: collectionGrid; mode: "grid"; cellWidth: collectionGrid.cellWidth; cellHeight: collectionGrid.cellHeight }
        }
    }

    ScrollView {
        anchors.fill: parent; anchors.margins: root.gutter; anchors.rightMargin: root.rightGutter
        visible: catalogState.route === "moods" && root.moodItems().length > 0
        Flow {
            width: parent.width; spacing: Theme.spacingLarge
            Repeater { model: root.moodItems(); delegate: ThemeActionButton { required property var modelData; text: modelData.title || "Mood"; width: 180; implicitHeight: 52; font.pixelSize: Theme.textBody; onClicked: browseState.mood(modelData) } }
        }
    }
    Column {
        anchors.centerIn: parent; width: Math.min(parent.width - 80, 480); spacing: 18
        visible: !catalogState.busy && !(root.result.items || []).length && !(root.result.shelves || []).length && !root.moodItems().length
        Text { width: parent.width; text: catalogState.error ? "Couldn’t Load This Page" : accountState.connected ? "No Music Here Yet" : "Your Music, Ready When You Are"; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 30; font.bold: true; color: themeState.foreground }
        Text { width: parent.width; text: catalogState.error || (accountState.connected ? "Select Home or Explore again to check for music." : "Connect YouTube Music to browse your music and recommendations."); textFormat: Text.PlainText; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.textTitle; color: themeState.secondary }
        ThemeActionButton { anchors.horizontalCenter: parent.horizontalCenter; primary: !accountState.connected; text: accountState.connected ? "Retry" : "Connect YouTube Music"; onClicked: accountState.connected ? catalogState.refresh() : appState.openAccount() }
    }
    BusyIndicator { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 16; running: catalogState.busy; visible: running && !root.loading }
    Label { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: Math.min(600, root.width - 48); padding: 12; wrapMode: Text.Wrap; textFormat: Text.PlainText; text: browseState.message || catalogState.error || (root.result.stale ? "Showing saved music." : ""); visible: text.length > 0; color: themeState.secondary; background: Rectangle { color: themeState.surface; radius: 4 } }
}
