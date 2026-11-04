import QtQuick

// Original line icons share one stroke and work without an icon font.
Canvas {
    id: icon
    property string kind: "cabinet"
    property color ink: Theme.text
    width: 32; height: 32
    onKindChanged: requestPaint()
    onInkChanged: requestPaint()
    onPaint: {
        var c = getContext("2d")
        c.reset(); c.scale(width / 32, height / 32)
        c.strokeStyle = ink; c.lineWidth = 2; c.lineJoin = "round"; c.lineCap = "round"
        if (kind === "quick") {
            c.beginPath(); c.moveTo(19, 3); c.lineTo(7, 18); c.lineTo(15, 18)
            c.lineTo(12, 29); c.lineTo(26, 13); c.lineTo(18, 13); c.closePath(); c.stroke()
        } else if (kind === "ranked") {
            c.strokeRect(9, 4, 14, 13); c.beginPath(); c.moveTo(9, 7); c.lineTo(4, 7)
            c.lineTo(4, 14); c.lineTo(10, 17); c.moveTo(23, 7); c.lineTo(28, 7)
            c.lineTo(28, 14); c.lineTo(22, 17); c.moveTo(16, 18); c.lineTo(16, 26)
            c.moveTo(10, 28); c.lineTo(22, 28); c.stroke()
        } else if (kind === "options") {
            for (var y = 8; y <= 24; y += 8) {
                c.beginPath(); c.moveTo(4, y); c.lineTo(28, y); c.stroke()
                c.strokeRect(y === 16 ? 19 : 9, y - 3, 4, 6)
            }
        } else if (kind === "more") {
            for (var x = 7; x <= 25; x += 9) { c.beginPath(); c.arc(x, 16, 2, 0, Math.PI * 2); c.stroke() }
        } else if (kind === "watch") {
            c.beginPath(); c.moveTo(3, 16); c.quadraticCurveTo(16, -1, 29, 16)
            c.quadraticCurveTo(16, 33, 3, 16); c.stroke()
            c.beginPath(); c.arc(16, 16, 4, 0, Math.PI * 2); c.stroke()
        } else {
            c.beginPath(); c.moveTo(8, 3); c.lineTo(24, 3); c.lineTo(26, 18)
            c.lineTo(29, 23); c.lineTo(27, 29); c.lineTo(5, 29); c.lineTo(3, 23)
            c.lineTo(6, 18); c.closePath(); c.stroke(); c.strokeRect(10, 7, 12, 9)
            c.beginPath(); c.moveTo(9, 23); c.lineTo(14, 23); c.moveTo(21, 22); c.lineTo(23, 22); c.stroke()
        }
    }
}
