import QtQuick

// One set's result. Won and lost differ in fill, not only in colour.
Rectangle {
    id: cell
    property var c: ({})
    property color accent: Theme.text
    property var root
    width: 48; height: 48
    color: c.win ? accent : "transparent"
    border.width: 2
    border.color: c.win ? accent : Theme.muted
    Text {
        anchors.centerIn: parent
        text: cell.c.text || ""
        color: cell.c.win ? Theme.ground : Theme.text
        font.family: cell.root ? cell.root.mono : "IBM Plex Mono"
        font.weight: Font.DemiBold
        font.pixelSize: Theme.px(24)
    }
}
