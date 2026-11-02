import QtQuick
import QtQuick.Controls
import Tubify.Video
import "Theme.js" as Theme

Item {
    id: root
    objectName: "expandedPlayer"
    readonly property var track: playerState.currentTrack
    readonly property var artists: track.artists && track.artists.length ? track.artists : track.artist ? [{name: track.artist}] : []
    readonly property var album: typeof track.album === "object" && track.album ? track.album : ({})
    readonly property string albumName: typeof track.album === "string" ? track.album : album.name || track.albumName || track.albumTitle || ""
    readonly property string albumId: album.id || album.browseId || ""
    readonly property real coverSize: Math.max(80, Math.min(width - 48, height - metadata.height - 64 - (modeSwitch.visible ? 52 : 0), 720))
    // Music videos play here; leaving the expanded player returns to audio only.
    readonly property bool videoShown: playerState.showingVideo && playerState.videoPreferred
    readonly property real videoWidth: Math.max(160, Math.min(width - 48, (height - metadata.height - 116) * 16 / 9, 1280))
    Component.onCompleted: playerState.setVideoSurface(true)
    Component.onDestruction: playerState.setVideoSurface(false)
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
        Row {
            id: modeSwitch
            objectName: "videoModeSwitch"
            anchors.horizontalCenter: parent.horizontalCenter
            visible: playerState.videoAvailable
            spacing: 4
            Repeater {
                model: [{ label: "Song", video: false }, { label: "Video", video: true }]
                delegate: Button {
                    id: mode
                    required property var modelData
                    readonly property bool selected: playerState.videoPreferred === modelData.video
                    text: modelData.label; height: 32; leftPadding: 18; rightPadding: 18
                    Accessible.name: "Play " + modelData.label.toLowerCase()
                    palette.buttonText: selected ? themeState.onAccent : themeState.foreground
                    background: Rectangle { radius: height / 2; color: mode.selected ? themeState.accent : mode.hovered ? themeState.hover : themeState.surface; border.width: mode.visualFocus ? 2 : 0; border.color: themeState.foreground }
                    onClicked: playerState.setVideoPreferred(modelData.video)
                }
            }
        }
        Item {
            objectName: "videoStage"
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.videoShown
            width: root.videoWidth; height: width * 9 / 16
            Rectangle { anchors.fill: parent; radius: 12; color: "black" }
            VideoSurface {
                objectName: "videoSurface"
                anchors.fill: parent
                frames: root.videoShown ? playerState.videoFrames : null
                Accessible.role: Accessible.Graphic
                Accessible.name: "Video for " + (root.track.title || "current song")
            }
        }
        Cover {
            objectName: "immersiveArtwork"
            anchors.horizontalCenter: parent.horizontalCenter
            visible: !root.videoShown
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
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(implicitWidth, parent.width)
                padding: 4
                Accessible.name: (root.track.title || "Current song") + " options"
                enabled: playerState.hasTrack
                onClicked: appState.showMenu(root.track, {})
                contentItem: Text {
                    text: root.track.title || "Nothing Playing"
                    textFormat: Text.PlainText
                    color: themeState.foreground; font.family: Theme.headingFont
                    font.pixelSize: root.width < 600 ? 24 : 32; font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                }
                background: Rectangle { radius: 8; color: title.hovered ? themeState.hover : "transparent"; border.width: title.visualFocus ? 2 : 0; border.color: themeState.accent }
            }
            Item {
                id: artistLine
                width: parent.width
                height: 36
                clip: true
                Row {
                    id: artistRow
                    x: Math.max(0, (artistLine.width - width) / 2)
                    height: parent.height
                    Repeater {
                        model: root.artists
                        Row {
                            required property var modelData
                            required property int index
                            height: artistRow.height
                            Button {
                                id: artist
                                objectName: "immersiveArtist-" + index
                                height: parent.height
                                text: modelData.name || ""
                                flat: true
                                Accessible.role: Accessible.Link
                                onClicked: browseState.openArtist(modelData)
                                contentItem: Text { text: artist.text; textFormat: Text.PlainText; font.pixelSize: 16; color: themeState.foreground; font.underline: artist.hovered; verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter }
                                background: Rectangle { radius: 8; color: artist.hovered ? themeState.hover : "transparent"; border.width: artist.visualFocus ? 2 : 0; border.color: themeState.accent }
                            }
                            Text { visible: index < root.artists.length - 1; height: parent.height; text: "•"; color: themeState.secondary; font.pixelSize: 16; verticalAlignment: Text.AlignVCenter }
                        }
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
