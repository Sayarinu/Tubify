import QtQuick
import QtQuick.Shapes
import "Theme.js" as Theme

Item {
    id: root
    property string name: "music"
    property color color: Theme.foreground
    implicitWidth: 24
    implicitHeight: 24
    Shape {
        preferredRendererType: Shape.CurveRenderer
        width: 24
        height: 24
        transform: Scale { xScale: root.width / 24; yScale: root.height / 24 }
        ShapePath {
            strokeColor: root.color
            strokeWidth: Theme.filled[root.name] ? 0 : 1.8
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            fillColor: Theme.filled[root.name] ? root.color : "transparent"
            PathSvg { path: Theme.paths[root.name] || Theme.paths.music }
        }
    }
}
