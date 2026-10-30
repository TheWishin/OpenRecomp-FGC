import QtQuick

// One set's result. Won and lost differ in fill, not only in colour.
Rectangle {
    id: cell
    property var c: ({})
    property color accent: "#ECE9E1"
    property var root
    width: 48; height: 48
    color: c.win ? accent : "transparent"
    border.width: 2
    border.color: c.win ? accent : "#6B6E75"
    Text {
        anchors.centerIn: parent
        text: cell.c.text || ""
        color: cell.c.win ? "#0E0F11" : "#ECE9E1"
        font.family: cell.root ? cell.root.mono : "IBM Plex Mono"
        font.weight: Font.DemiBold
        font.pixelSize: 24
    }
}
