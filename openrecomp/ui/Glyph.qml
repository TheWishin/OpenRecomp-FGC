import QtQuick

// A button prompt: round pad button, pill for LB/Start, keycap on the keyboard.
Rectangle {
    id: glyph
    property var g: ({})
    property int size: 44
    readonly property bool ink: !!g.ink
    width: Math.max(size, label.implicitWidth + (g.round ? 0 : 24))
    height: size
    radius: g.key ? 6 : size / 2
    color: ink ? "#0E0F11" : "#ECE9E1"
    Text {
        id: label
        anchors.centerIn: parent
        text: glyph.g.text || ""
        color: glyph.ink ? "#F2EFE6" : "#0E0F11"
        font.family: glyph.g.symbol ? "Segoe UI Symbol" : "IBM Plex Sans"
        font.weight: Font.DemiBold
        font.pixelSize: glyph.size * 0.5
    }
}
