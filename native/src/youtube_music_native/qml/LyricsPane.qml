import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    objectName: "lyricsPane"
    readonly property bool hasLyrics: !!lyricState.data.available
    readonly property bool timed: hasLyrics && !!lyricState.data.timed
    readonly property bool following: !resumeFollow.running
    readonly property int lyricFontSize: width < 360 ? 20 : width < 520 ? 22 : 24

    function centerCurrent() {
        if (!visible || !timed || !following || lyricState.currentLine < 0) return
        lines.forceLayout()
        lines.positionViewAtIndex(lyricState.currentLine, ListView.Center)
    }
    function followCurrent() {
        resumeFollow.stop()
        lines.cancelFlick()
        Qt.callLater(centerCurrent)
    }
    function pauseFollow() {
        if (timed) resumeFollow.restart()
    }
    function scrollWithKey(event) {
        var distance = 0
        switch (event.key) {
        case Qt.Key_Up: distance = -48; break
        case Qt.Key_Down: distance = 48; break
        case Qt.Key_PageUp: distance = -lines.height * 0.8; break
        case Qt.Key_PageDown: distance = lines.height * 0.8; break
        case Qt.Key_Home: distance = -lines.contentHeight; break
        case Qt.Key_End: distance = lines.contentHeight; break
        default: return
        }
        pauseFollow()
        lines.cancelFlick()
        lines.contentY = Math.max(lines.originY - lines.topMargin,
                                 Math.min(lines.originY + lines.contentHeight - lines.height + lines.bottomMargin,
                                          lines.contentY + distance))
        event.accepted = true
    }
    onVisibleChanged: if (visible) followCurrent()
    onWidthChanged: Qt.callLater(centerCurrent)
    onHeightChanged: Qt.callLater(centerCurrent)
    Component.onCompleted: followCurrent()
    Keys.onPressed: event => scrollWithKey(event)

    Timer {
        id: resumeFollow
        objectName: "lyricResumeTimer"
        interval: 6000
        onTriggered: {
            if (lines.moving || scrollBar.pressed) restart()
            else root.followCurrent()
        }
    }

    Column {
        id: emptyState
        objectName: "lyricEmptyState"
        anchors.top: parent.top
        anchors.topMargin: 24
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.max(0, parent.width - 32)
        spacing: 12
        visible: !root.hasLyrics
        BusyIndicator { anchors.horizontalCenter: parent.horizontalCenter; width: 28; height: 28; running: lyricState.busy; visible: running }
        Text {
            width: parent.width
            text: lyricState.busy ? "Loading lyrics…" : lyricState.error || "Lyrics aren’t available for this song."
            textFormat: Text.PlainText
            color: themeState.secondary
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            font.family: Theme.bodyFont
            font.pixelSize: 14
        }
        ThemeActionButton {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: !lyricState.busy
            text: "Retry"
            onClicked: lyricState.refresh()
        }
    }

    ListView {
        id: lines
        objectName: "lyricLines"
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: status.top
        visible: root.hasLyrics
        clip: true
        spacing: 8
        // Space at both ends lets the first and final lines sit in the same reading position.
        topMargin: root.timed ? height / 2 : 16
        bottomMargin: root.timed ? height / 2 : 16
        model: lyricState.data.lines || []
        boundsBehavior: Flickable.StopAtBounds
        keyNavigationEnabled: false
        activeFocusOnTab: true
        Accessible.name: "Lyrics"
        Accessible.description: "Use arrow keys or Page Up and Page Down to scroll"
        onDraggingChanged: if (dragging) root.pauseFollow()
        onMovementEnded: if (!root.following) root.pauseFollow()
        onCountChanged: Qt.callLater(root.centerCurrent)
        // Follow/status controls change this viewport without resizing the pane.
        onHeightChanged: Qt.callLater(root.centerCurrent)
        Keys.onPressed: event => root.scrollWithKey(event)
        WheelHandler {
            target: null
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            blocking: false
            onWheel: event => { root.pauseFollow(); event.accepted = false }
        }
        ScrollBar.vertical: ScrollBar {
            id: scrollBar
            objectName: "lyricScrollBar"
            onPressedChanged: root.pauseFollow()
            onPositionChanged: if (pressed) root.pauseFollow()
        }
        delegate: ItemDelegate {
            id: line
            required property var modelData
            required property int index
            objectName: "lyricLine-" + index
            readonly property bool seekable: root.timed && modelData.start >= 0
            width: Math.max(0, lines.width - scrollBar.width - 8)
            height: Math.max(44, label.implicitHeight + 20)
            leftPadding: 16
            rightPadding: 8
            topPadding: 10
            bottomPadding: 10
            hoverEnabled: seekable
            focusPolicy: seekable ? Qt.StrongFocus : Qt.NoFocus
            Accessible.role: seekable ? Accessible.Button : Accessible.StaticText
            Accessible.name: modelData.text || "Instrumental break"
            Accessible.description: seekable ? "Seek to " + Theme.timeLabel(modelData.start) : ""
            onClicked: if (seekable) { lyricState.seekLine(index); root.followCurrent() }
            onActiveFocusChanged: if (activeFocus && (focusReason === Qt.TabFocusReason || focusReason === Qt.BacktabFocusReason)) {
                root.pauseFollow()
                lines.positionViewAtIndex(index, ListView.Contain)
            }
            Keys.onShortcutOverride: event => {
                if (seekable && (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) event.accepted = true
            }
            Keys.onReturnPressed: if (seekable) clicked()
            Keys.onEnterPressed: if (seekable) clicked()
            contentItem: Text {
                id: label
                objectName: "lyricText-" + line.index
                text: line.modelData.text
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                color: !root.timed || line.index === lyricState.currentLine ? themeState.foreground : themeState.secondary
                font.family: Theme.bodyFont
                font.bold: true
                font.pixelSize: root.lyricFontSize
                lineHeight: 1.15
            }
            background: Rectangle {
                color: line.hovered && line.seekable ? themeState.surface : "transparent"
                border.color: line.visualFocus ? themeState.accent : "transparent"
                border.width: 1
                radius: 6
            }
        }
    }

    Column {
        id: status
        objectName: "lyricStatus"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 12
        spacing: 8
        visible: root.hasLyrics
        ThemeActionButton {
            objectName: "followLyrics"
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.timed && !root.following
            text: "Follow lyrics"
            onClicked: root.followCurrent()
        }
        Text {
            objectName: "lyricSource"
            width: parent.width
            text: [lyricState.data.source || "", lyricState.data.cached ? "Saved lyrics" : "", root.hasLyrics && !root.timed ? "Unsynced lyrics" : ""].filter(Boolean).join(" · ")
            textFormat: Text.PlainText
            color: themeState.secondary
            font.family: Theme.bodyFont
            font.pixelSize: 12
            wrapMode: Text.Wrap
            visible: !!text
        }
        Text {
            objectName: "lyricRefreshStatus"
            width: parent.width
            text: lyricState.busy ? "Refreshing lyrics…" : lyricState.error
            textFormat: Text.PlainText
            color: themeState.secondary
            font.family: Theme.bodyFont
            font.pixelSize: 12
            wrapMode: Text.Wrap
            visible: !!text
        }
        ThemeActionButton {
            visible: !!lyricState.error && !lyricState.busy
            text: "Retry"
            onClicked: lyricState.refresh()
        }
        onHeightChanged: Qt.callLater(root.centerCurrent)
    }

    Connections {
        target: lyricState
        function onChanged() {
            if (!root.hasLyrics) root.followCurrent()
            else Qt.callLater(root.centerCurrent)
        }
        function onCurrentLineChanged() { Qt.callLater(root.centerCurrent) }
    }
    Connections {
        target: playerState
        function onSeeked(position) { root.followCurrent() }
    }
}
