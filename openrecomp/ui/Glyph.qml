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
    color: ink ? Theme.ground : Theme.text
    Text {
        id: label
        anchors.centerIn: parent
        text: glyph.g.symbol ? "" : (glyph.g.text || "")
        color: glyph.ink ? Theme.selected : Theme.ground
        font.family: glyph.g.symbol ? "Segoe UI Symbol" : "IBM Plex Sans"
        font.weight: Font.DemiBold
        font.pixelSize: Theme.px(glyph.size * 0.5)
    }
    // PlayStation symbols are drawn, not typed: no font has to carry them (the offscreen shots showed boxes)
    Canvas {
        id: symbol
        anchors.centerIn: parent
        width: glyph.size * 0.5; height: width
        visible: !!glyph.g.symbol
        property string shape: glyph.g.text || ""
        property color ink: glyph.ink ? Theme.selected : Theme.ground
        onShapeChanged: requestPaint()
        onInkChanged: requestPaint()
        onWidthChanged: requestPaint()
        onPaint: {
            var c = getContext("2d"), w = width, h = height, m = w * 0.14
            c.reset()
            c.clearRect(0, 0, w, h)
            c.strokeStyle = ink
            c.lineWidth = Math.max(2, w * 0.14)
            c.lineJoin = "round"; c.lineCap = "round"
            c.beginPath()
            if (shape === "✕") { c.moveTo(m, m); c.lineTo(w - m, h - m); c.moveTo(w - m, m); c.lineTo(m, h - m) }
            else if (shape === "○") { c.arc(w / 2, h / 2, w / 2 - m, 0, Math.PI * 2) }
            else if (shape === "□") { c.rect(m, m, w - 2 * m, h - 2 * m) }
            else if (shape === "△") { c.moveTo(w / 2, m); c.lineTo(w - m, h - m * 1.2); c.lineTo(m, h - m * 1.2); c.closePath() }
            c.stroke()
        }
        Component.onCompleted: requestPaint()
    }
}
