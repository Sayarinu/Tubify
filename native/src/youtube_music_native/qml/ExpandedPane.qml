import QtQuick
import QtQuick.Controls
import "Theme.js" as Theme

Item {
    id: root
    objectName: "expandedPlayer"
    readonly property var track: playerState.currentTrack
    readonly property var artists: track.artists && track.artists.length ? track.artists : track.artist ? [{name: track.artist}] : []
    readonly property var album: typeof track.album === "object" && track.album ? track.album : ({})
    readonly property string albumName: typeof track.album === "string" ? track.album : album.name || track.albumName || track.albumTitle || ""
    readonly property string albumId: album.id || album.browseId || ""
    readonly property real coverSize: Math.max(80, Math.min(width - 48, height - metadata.height - 64, 720))
    function focusStage() { title.forceActiveFocus() }

    ArtworkBackdrop {
        anchors.fill: parent
        source: root.track.thumbnail || ""
        mediaKey: root.track.videoId || root.track.id || ""
    }
    Column {
        anchors.centerIn: parent
        width: Math.min(root.width - 48, 760)
        spacing: 24
        Cover {
            objectName: "immersiveArtwork"
            anchors.horizontalCenter: parent.horizontalCenter
            width: root.coverSize; height: width; radius: 12
            largeArtwork: true
            media: root.track
            source: root.track.largeThumbnail || root.track.thumbnail || ""
            mediaKey: root.track.videoId || root.track.id || ""
            Accessible.role: Accessible.Graphic
            Accessible.name: "Artwork for " + (root.track.title || "current song")
        }
        Column {
            id: metadata
            width: parent.width
            spacing: 4
            Button {
                id: title
                objectName: "immersiveTrackTitle"
                width: parent.width
                padding: 4
                Accessible.name: (root.track.title || "Current song") + " options"
                enabled: playerState.hasTrack
                onClicked: appState.showMenu(root.track, {})
                contentItem: Text {
                    text: root.track.title || "Nothing playing"
                    textFormat: Text.PlainText
                    color: themeState.foreground; font.family: Theme.headingFont
                    font.pixelSize: root.width < 600 ? 24 : 32; font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                }
                background: Rectangle { radius: 8; color: title.hovered ? themeState.hover : "transparent"; border.width: title.visualFocus ? 2 : 0; border.color: themeState.accent }
            }
            Flow {
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(implicitWidth, parent.width)
                layoutDirection: Qt.LeftToRight
                spacing: 4
                Repeater {
                    model: root.artists
                    Button {
                        id: artist
                        required property var modelData
                        required property int index
                        objectName: "immersiveArtist-" + index
                        width: Math.min(implicitWidth, metadata.width)
                        height: 36
                        text: modelData.name || ""
                        flat: true
                        Accessible.role: Accessible.Link
                        onClicked: browseState.openArtist(modelData)
                        contentItem: Text { text: artist.text; textFormat: Text.PlainText; elide: Text.ElideRight; font.pixelSize: 16; color: themeState.foreground; font.underline: artist.hovered; verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter }
                        background: Rectangle { radius: 8; color: artist.hovered ? themeState.hover : "transparent"; border.width: artist.visualFocus ? 2 : 0; border.color: themeState.accent }
                    }
                }
            }
            Button {
                id: albumLink
                objectName: "immersiveAlbum"
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(implicitWidth, parent.width)
                height: 36
                visible: !!root.albumName
                enabled: !!root.albumId
                text: root.albumName
                flat: true
                Accessible.role: enabled ? Accessible.Link : Accessible.StaticText
                onClicked: browseState.open({kind: "album", id: root.albumId, title: root.albumName})
                contentItem: Text { text: albumLink.text; textFormat: Text.PlainText; elide: Text.ElideRight; font.pixelSize: 14; color: themeState.secondary; font.underline: albumLink.hovered && albumLink.enabled; verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter }
                background: Rectangle { radius: 8; color: albumLink.hovered && albumLink.enabled ? themeState.hover : "transparent"; border.width: albumLink.visualFocus ? 2 : 0; border.color: themeState.accent }
            }
        }
    }
}
