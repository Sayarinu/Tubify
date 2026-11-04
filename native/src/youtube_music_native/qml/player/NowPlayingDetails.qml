import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme
import "../components"

// The queue dock's larger now-playing view: artwork, song and a preview of the first artist.
Column {
    id: root
    objectName: "queueNowPlayingDetails"
    readonly property var track: playerState.currentTrack
    readonly property var artists: track.artists && track.artists.length ? track.artists : []
    spacing: Theme.spacingMedium
    Cover {
        objectName: "queueNowPlayingArtwork"
        width: parent.width; height: width; radius: Theme.radiusMedium
        largeArtwork: true
        media: root.track
        source: root.track.largeThumbnail || root.track.thumbnail || ""
        mediaKey: root.track.videoId || root.track.id || ""
        Accessible.role: Accessible.Graphic
        Accessible.name: "Artwork for " + (root.track.title || "current song")
    }
    Item {
        width: parent.width; height: 48
        Column {
            anchors.left: parent.left; anchors.right: songOptions.left; anchors.rightMargin: Theme.spacingSmall
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Text {
                objectName: "queueNowPlayingTitle"
                width: parent.width; text: root.track.title || ""
                textFormat: Text.PlainText; elide: Text.ElideRight
                color: themeState.foreground; font.pixelSize: 18; font.bold: true
            }
            Text {
                width: parent.width
                text: root.artists.map(artist => artist.name).join(" • ") || root.track.artist || ""
                textFormat: Text.PlainText; elide: Text.ElideRight
                color: themeState.secondary; font.pixelSize: Theme.textBody
            }
        }
        IconButton {
            id: songOptions
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            width: 36; height: 36; iconSize: 20
            iconName: "more"; tip: "Current Song Options"
            onClicked: appState.showMenu(root.track, {nowPlaying: true})
        }
    }
    Rectangle {
        id: artistCard
        objectName: "queueArtistPreview"
        readonly property bool hasPreview: typeof artistPreview !== "undefined" && artistPreview.name.length > 0
        readonly property bool hasImage: hasPreview && artistPreview.image.length > 0
        function openArtist() {
            var artist = root.artists.length ? root.artists[0] : ({name: artistPreview.name})
            browseState.openArtist({id: artist.id || artist.browseId || artist.channelId, browseId: artist.browseId, channelId: artist.channelId, name: artist.name})
        }
        visible: hasPreview
        width: parent.width
        height: visible ? artistColumn.implicitHeight + 2 * Theme.spacingMedium : 0
        radius: Theme.radiusMedium
        color: artistHover.hovered || activeFocus ? themeState.hover : themeState.surface
        border.color: activeFocus ? themeState.accent : themeState.border
        border.width: activeFocus ? 2 : 1
        activeFocusOnTab: visible
        Accessible.role: Accessible.Button
        Accessible.name: hasPreview ? "Open artist " + artistPreview.name : ""
        Accessible.onPressAction: openArtist()
        Keys.onReturnPressed: openArtist()
        Keys.onSpacePressed: openArtist()
        HoverHandler { id: artistHover }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: artistCard.openArtist() }
        Column {
            id: artistColumn
            x: Theme.spacingMedium; y: Theme.spacingMedium
            width: parent.width - 2 * x
            spacing: 4
            Cover {
                objectName: "queueArtistImage"
                visible: artistCard.hasImage
                width: parent.width; height: visible ? width * 9 / 16 : 0
                radius: Theme.radiusSmall
                placeholder: "profile"
                source: artistCard.hasImage ? artistPreview.image : ""
            }
            Item { width: 1; height: artistCard.hasImage ? 4 : 0 }
            Text { text: "About the Artist"; color: themeState.secondary; font.pixelSize: Theme.textSmall; font.bold: true }
            Text {
                objectName: "queueArtistName"
                width: parent.width; text: artistCard.hasPreview ? artistPreview.name : ""
                textFormat: Text.PlainText; elide: Text.ElideRight
                color: themeState.foreground; font.pixelSize: Theme.textTitle; font.bold: true
            }
            Text {
                width: parent.width; visible: text.length > 0
                text: artistCard.hasPreview && artistPreview.audience ? artistPreview.audience + " monthly audience" : ""
                textFormat: Text.PlainText; elide: Text.ElideRight
                color: themeState.secondary; font.pixelSize: Theme.textSmall
            }
            Text {
                width: parent.width; visible: text.length > 0
                text: artistCard.hasPreview ? artistPreview.description : ""
                textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                color: themeState.secondary; font.pixelSize: Theme.textSmall
            }
        }
    }
}
