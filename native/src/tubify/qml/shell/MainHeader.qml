import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme
import "../components"

// Top bar: navigation toggle, Back and Forward, search with suggestions, and the update, history, settings and account buttons.
Item {
    id: header
    objectName: "mainHeader"
    // The navigation rail is in a drawer, so the header shows a button that opens it.
    property bool compactNavigation: false
    signal navigationRequested()
    signal settingsRequested()
    signal accountRequested()
    signal updateRequested()
    function focusSearch() { search.forceActiveFocus() }
    function focusNavigationToggle() { navigationToggle.forceActiveFocus() }
    function focusSettingsButton() { settingsButton.forceActiveFocus() }
    function showQuery(query) { search.text = query }
    property bool collapsed: false
    // How far the divider runs past the header, to meet the side panel's divider.
    property real dividerExtension: 0
    readonly property real fullHeight: 64
    // How far the side panel has slid in; its gap replaces the header's right gutter.
    property real panelRevealed: 0
    height: collapsed ? 0 : fullHeight
    visible: !collapsed
    Rectangle { objectName: "mainHeaderDivider"; anchors.left: parent.left; anchors.right: parent.right; anchors.rightMargin: -header.dividerExtension; anchors.bottom: parent.bottom; height: 1; color: themeState.border }
    IconButton { id: navigationToggle; objectName: "navigationToggle"; visible: header.compactNavigation; x: 8; y: 10; width: 36; height: 44; iconName: "menu"; tip: "Open Navigation"; Keys.onShortcutOverride: function(event) { if (event.key === Qt.Key_Space || event.key === Qt.Key_Return) event.accepted = true }; Keys.onReturnPressed: header.navigationRequested(); onClicked: header.navigationRequested() }
    IconButton { id: backButton; objectName: "backButton"; x: header.compactNavigation ? 44 : header.width < 480 ? 8 : 40; y: 10; width: 44; height: 44; iconName: "back"; tip: "Back"; outlined: true; enabled: browseState.canGoBack; onClicked: { appState.setExpanded(false); browseState.back() } }
    // Returns to the page Back left; there is nothing to return to after opening a new page.
    IconButton { id: forwardButton; objectName: "forwardButton"; x: backButton.x + 48; y: 10; width: 44; height: 44; iconName: "forward"; tip: "Forward"; outlined: true; enabled: browseState.canGoForward; onClicked: { appState.setExpanded(false); browseState.forward() } }
    ThemedTextField {
        id: search
        objectName: "searchField"
        x: forwardButton.x + forwardButton.width + (header.width < 480 ? 4 : 8)
        y: 11
        width: Math.max(80, Math.min(480, (updateButton.visible ? updateButton.x : historyButton.visible ? historyButton.x : settingsButton.x) - x - 12))
        height: 42
        leftPadding: header.width < 400 ? 34 : 52
        rightPadding: text.length > 0 ? 48 : 16
        radius: Theme.radiusMedium
        placeholderText: header.width < 400 ? "Search" : "Search songs, albums, artists"
        font.pixelSize: 16
        Accessible.name: "Search Tubify"
        Symbol { x: header.width < 400 ? 8 : 16; anchors.verticalCenter: parent.verticalCenter; name: "search"; width: 20; height: 20; color: themeState.secondary }
        IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; visible: search.text.length > 0; iconName: "close"; tip: "Clear Search"; onClicked: { search.clear(); searchState.clearSuggestions(); search.forceActiveFocus() } }
        onAccepted: {
            var chosen = suggestions.currentIndex >= 0 ? searchState.suggestions[suggestions.currentIndex] : search.text
            search.text = chosen
            appState.search(chosen)
        }
        onTextEdited: { suggestions.currentIndex = -1; searchState.suggest(text) }
        Keys.onDownPressed: suggestions.currentIndex = Math.min(suggestions.count - 1, suggestions.currentIndex + 1)
        Keys.onUpPressed: suggestions.currentIndex = Math.max(-1, suggestions.currentIndex - 1)
        Keys.onEscapePressed: searchState.clearSuggestions()
        Popup {
            id: suggestionPopup
            y: search.height + 4; width: search.width
            height: Math.min(360, searchState.suggestions.length * 44 + 16)
            padding: 8; focus: false
            visible: search.activeFocus && searchState.suggestions.length > 0
            background: Rectangle { color: themeState.hover; radius: Theme.radiusSmall }
            contentItem: ListView {
                id: suggestions
                clip: true; currentIndex: -1; model: searchState.suggestions
                delegate: ItemDelegate {
                    required property string modelData
                    required property int index
                    width: suggestions.width; height: 44
                    highlighted: index === suggestions.currentIndex
                    background: Rectangle { color: parent.highlighted ? themeState.selected : parent.hovered ? themeState.hover : "transparent"; radius: 4 }
                    contentItem: Text { text: modelData; textFormat: Text.PlainText; color: themeState.foreground; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; font.pixelSize: Theme.textTitle }
                    onClicked: { search.text = modelData; appState.search(modelData) }
                }
            }
        }
    }
    IconButton {
        id: profileButton
        objectName: "profileButton"
        anchors.right: parent.right
        anchors.rightMargin: (1 - header.panelRevealed) * (header.width < 480 ? 8 : 32)
        y: 10
        width: 44; height: 44
        iconName: "profile"
        tip: accountState.profile.name || "Account"
        onClicked: {
            if (accountState.connected) accountMenu.popup(profileButton, profileButton.width - accountMenu.implicitWidth, profileButton.height, null)
            else header.accountRequested()
        }
        contentItem: Item {
            Avatar {
                anchors.centerIn: parent
                width: 28; height: 28
                source: accountState.profile.avatar || ""
            }
        }
    }
    IconButton { id: settingsButton; objectName: "settingsButton"; anchors.right: profileButton.left; anchors.rightMargin: 12; y: 10; width: 44; height: 44; iconName: "settings"; tip: "Settings"; onClicked: header.settingsRequested() }
    IconButton { id: historyButton; objectName: "historyButton"; visible: header.width >= 640; anchors.right: settingsButton.left; anchors.rightMargin: 12; y: 10; width: 44; height: 44; iconName: "history"; tip: "Listening History"; onClicked: libraryState.history() }
    IconButton {
        id: updateButton
        objectName: "updateButton"
        // Shown only while a newer stable release is waiting or downloading.
        visible: maintenanceState.updateAvailable || maintenanceState.downloading
        anchors.right: historyButton.visible ? historyButton.left : settingsButton.left; anchors.rightMargin: 12
        y: 10; width: 44; height: 44
        iconName: "update"; iconColor: themeState.accent
        tip: maintenanceState.downloading ? "Downloading update " + maintenanceState.progress + "%" : maintenanceState.latestName + " is available"
        Accessible.name: "Update available"
        onClicked: header.updateRequested()
        Rectangle {
            objectName: "updateBadge"
            width: 10; height: 10; radius: 5
            x: parent.width - width - 8; y: 8
            color: themeState.accent
            border.width: 2; border.color: themeState.background
            SequentialAnimation on scale {
                running: updateButton.visible && !appState.reducedMotion
                loops: 3
                NumberAnimation { from: 1; to: 1.5; duration: 400; easing.type: Easing.OutQuad }
                NumberAnimation { from: 1.5; to: 1; duration: 400; easing.type: Easing.InQuad }
            }
        }
    }

    ThemedMenu {
        id: accountMenu
        objectName: "accountMenu"
        implicitWidth: 252
        MenuItem {
            enabled: false
            implicitHeight: 42
            contentItem: Item {
                Text {
                    anchors.fill: parent
                    verticalAlignment: Text.AlignVCenter
                    text: accountState.profile.name || "YouTube Music Account"
                    color: themeState.foreground
                    font.pixelSize: Theme.textBody
                    font.bold: true
                    elide: Text.ElideRight
                }
            }
            background: Rectangle { color: "transparent" }
        }
        ThemedMenuSeparator {}
        ContextMenuItem { text: "Connection Settings"; onTriggered: header.accountRequested() }
        ThemedMenuSeparator { visible: accountState.connected; height: visible ? implicitHeight : 0 }
        ContextMenuItem { text: "Sign Out"; visible: accountState.connected; height: visible ? implicitHeight : 0; onTriggered: accountState.signOut() }
    }
}
