import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

// Navigation rail: the main pages, New Playlist and the account's playlists, with a resize handle.
// The window places it beside the content or, when space is short, inside the navigation drawer.
Rectangle {
    id: sidebar
    objectName: "navigationRail"
    // Show labels beside the icons; off, the rail shows icons with tooltips.
    property bool wide: true
    // Emitted after a page or playlist is chosen, so the drawer can close.
    signal navigated()
    focus: true
    property bool collapsed: false
    visible: !collapsed
    color: themeState.background
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: themeState.border }
    Item {
        id: sidebarResizeHandle
        objectName: "sidebarResizeHandle"
        z: 10
        visible: true
        x: sidebar.width - width
        width: 12
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        HoverHandler { id: sidebarResizeHover; cursorShape: Qt.SizeHorCursor }
        Rectangle {
            objectName: "sidebarResizeLine"
            // Drawn over the sidebar's 1 px border (its right edge), not the middle of the grab area.
            anchors.right: parent.right
            width: 2
            height: parent.height
            color: themeState.accent
            opacity: sidebarResizeHover.hovered || sidebarResizeMouse.pressed ? 0.9 : 0
        }
        MouseArea {
            id: sidebarResizeMouse
            anchors.fill: parent
            cursorShape: Qt.SizeHorCursor
            preventStealing: true
            property real startWidth: 240
            property real startX: 0
            onPressed: function(mouse) {
                startWidth = sidebar.width
                startX = sidebarResizeMouse.mapToItem(null, mouse.x, mouse.y).x
            }
            onPositionChanged: function(mouse) {
                if (pressed) {
                    var sceneX = sidebarResizeMouse.mapToItem(null, mouse.x, mouse.y).x
                    appState.setSidebarWidth(startWidth + (sceneX - startX) / appState.uiScaleFactor)
                }
            }
            onReleased: appState.saveSidebarWidths()
        }
    }
    Column {
        id: navigation
        x: 8; y: 8; width: sidebar.width - 16
        Repeater {
            model: [{label:"Home",icon:"home"}, {label:"Explore",icon:"explore"}, {label:"Library",icon:"library"}, {label:"Downloads",icon:"download"}]
            delegate: Button {
                id: nav
                required property var modelData
                objectName: "navigationButton-" + modelData.label
                readonly property bool selected: appState.page === text
                hoverEnabled: true
                width: navigation.width
                height: 48
                padding: 0
                leftInset: 0; rightInset: 0; topInset: 0; bottomInset: 0
                text: modelData.label
                Accessible.name: text
                onClicked: { if (!browseState.atTabRoot(text)) appState.navigate(text); sidebar.navigated() }
                background: Rectangle {
                    objectName: "navigationBackground-" + nav.text
                    anchors.fill: parent
                    radius: 8
                    color: nav.selected ? themeState.selected : nav.hovered ? themeState.hover : "transparent"
                    border.width: nav.visualFocus ? 2 : 0
                    border.color: themeState.accent
                    Rectangle { objectName: "navigationMarker-" + nav.text; x: 4; anchors.verticalCenter: parent.verticalCenter; width: 3; height: 24; radius: 2; color: themeState.accent; visible: nav.selected }
                }
                contentItem: Row {
                    leftPadding: 16; spacing: 20
                    Symbol { anchors.verticalCenter: parent.verticalCenter; name: nav.modelData.icon; color: nav.selected ? themeState.accent : themeState.secondary }
                    Text { anchors.verticalCenter: parent.verticalCenter; visible: sidebar.wide; text: nav.text; color: themeState.foreground; font.pixelSize: 16 }
                }
                ToolTip.text: text
                ToolTip.visible: !sidebar.wide && hovered
            }
        }
    }
    Rectangle { objectName: "navigationDivider"; x: 8; y: navigation.y + navigation.height + 12; width: sidebar.width - 16; height: 1; color: themeState.border }
    Button {
        id: newPlaylist
        objectName: "newPlaylistButton"
        x: 8; y: navigation.y + navigation.height + 24
        width: sidebar.width - 16; height: 40
        text: "New Playlist"
        Accessible.name: text
        ToolTip.text: text
        ToolTip.visible: hovered
        contentItem: Item {
            Row {
                anchors.centerIn: parent
                spacing: Theme.spacingSmall
                Symbol { anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18; name: "plus"; color: themeState.foreground }
                Text { anchors.verticalCenter: parent.verticalCenter; visible: sidebar.wide; text: newPlaylist.text; color: themeState.foreground; font.pixelSize: Theme.textBody }
            }
        }
        background: Rectangle { radius: height / 2; color: newPlaylist.hovered ? themeState.hover : themeState.surface; border.width: newPlaylist.visualFocus ? 2 : 0; border.color: themeState.foreground }
        onClicked: appState.requestAction("newPlaylist")
    }
    ListView {
        id: sidebarPlaylists
        objectName: "sidebarPlaylists"
        WheelScroll { view: sidebarPlaylists }
        anchors.top: newPlaylist.bottom
        anchors.topMargin: 12
        anchors.bottom: parent.bottom
        // Inset like the navigation items so hover highlights never cover the sidebar border.
        x: 8; width: parent.width - 16
        clip: true
        model: appState.playlists
        delegate: ItemDelegate {
            required property var modelData
            width: ListView.view.width
            height: 56
            padding: 0
            Accessible.name: modelData.title
            ToolTip.text: modelData.title
            ToolTip.visible: hovered && !sidebar.wide
            contentItem: Item {
                Cover { x: 8; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; radius: 8; source: modelData.thumbnail || ""; mediaKey: "playlist:" + modelData.id; accent: themeState.selected }
                Column {
                    x: 60; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 72; spacing: 4
                    visible: sidebar.wide
                    Text { width: parent.width; text: modelData.title; textFormat: Text.PlainText; color: themeState.foreground; font.pixelSize: 14; elide: Text.ElideRight }
                    Text { width: parent.width; text: modelData.owner || ""; textFormat: Text.PlainText; color: themeState.secondary; font.pixelSize: 12; elide: Text.ElideRight }
                }
            }
            background: Rectangle { radius: 8; color: parent.hovered ? themeState.hover : "transparent"; border.color: parent.visualFocus ? themeState.accent : "transparent" }
            onClicked: { appState.requestAction("playlist:" + modelData.id); sidebar.navigated() }
        }
    }
}
