import QtQuick
import QtQuick.Shapes

// Runtime adapter pictures stay on the player's PC. Missing pictures get a quiet fighter outline.
Rectangle {
    id: portrait
    property url source: ""
    property string name: ""
    property bool mirrored: false
    color: Theme.raised; clip: true
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 4; color: Theme.gameAccent }
    Item {
        id: fallback
        objectName: "fighterFallback"
        visible: picture.status !== Image.Ready
        anchors.centerIn: parent
        width: Math.min(parent.width * .62, parent.height * .60, 160); height: width * 1.2
        opacity: .65
        Shape {
            width: 100; height: 120
            transform: Scale { xScale: (portrait.mirrored ? -1 : 1) * fallback.width / 100; yScale: fallback.height / 120; origin.x: 50; origin.y: 60 }
            anchors.centerIn: parent
            ShapePath {
                fillColor: "transparent"; strokeColor: Theme.gameAccent; strokeWidth: 1.5
                capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                PathSvg { path: "M 59 11 C 51 6 41 9 39 18 C 37 27 42 34 50 35 C 58 36 64 30 65 22 C 66 17 64 13 59 11 Z M 42 42 L 32 44 L 24 31 L 13 34 L 20 58 L 37 65 L 36 83 L 23 108 L 38 112 L 52 90 L 62 111 L 78 108 L 65 79 L 64 58 L 78 52 L 87 31 L 75 26 L 65 42 L 57 40 M 37 65 L 42 50 M 64 58 L 59 49 M 36 83 L 65 79" }
            }
        }
    }
    Image { id: picture; objectName: "fighterPicture"; anchors.centerIn: parent; width: Math.min(parent.width, implicitWidth); height: Math.min(parent.height, implicitHeight); source: portrait.source; fillMode: Image.PreserveAspectFit; mirror: portrait.mirrored; asynchronous: true; visible: status === Image.Ready }
    Rectangle { visible: !!portrait.name; anchors.bottom: parent.bottom; width: parent.width; height: caption.height + 12; color: Theme.ground; opacity: .94 }
    Text { id: caption; visible: !!portrait.name; x: 8; anchors.bottom: parent.bottom; anchors.bottomMargin: 6; width: parent.width - 16; text: portrait.name; textFormat: Text.PlainText; elide: Text.ElideRight; color: Theme.text; font.family: "IBM Plex Sans"; font.pixelSize: Theme.onlinePx(14); Accessible.name: text }
}
