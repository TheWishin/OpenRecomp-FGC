import QtQuick
import QtQuick.Shapes

// A controller's own button, drawn here from plain shapes (pad_glyphs.glyph): lettered face buttons, PlayStation
// symbols, bumpers, triggers, sticks, the d-pad and keyboard keys. No pictures from any pad maker.
Item {
    id: glyph
    property var g: ({})
    property int size: 44
    property bool dim: false
    readonly property string shape: g.shape || "num"
    readonly property color ink: "#0E0F11"
    readonly property color bone: "#ECE9E1"
    readonly property color body: "#2A2D33"
    readonly property color tone: ({ green: "#5DBB63", red: "#E0564B", blue: "#4C8DDC", yellow: "#E6C04A", pink: "#D77BBF" })[g.tone || ""] || bone
    readonly property int wide: shape === "bumper" ? size * 1.5 : shape === "trigger" ? size * 1.25
                               : shape === "touch" ? size * 1.9 : shape === "menu" ? Math.max(size, menuText.implicitWidth + size * 0.5)
                               : shape === "key" ? Math.max(size, keyText.implicitWidth + size * 0.45) : size
    width: wide
    height: size
    opacity: dim ? 0.45 : 1

    // round buttons: Xbox letters, numbered pads, PlayStation symbols, stick clicks
    Rectangle {
        visible: ["face", "num", "ps", "click", "stick"].indexOf(glyph.shape) >= 0
        anchors.centerIn: parent
        width: glyph.size; height: glyph.size; radius: glyph.size / 2
        color: glyph.shape === "face" ? glyph.tone : glyph.body
        border.width: glyph.shape === "face" ? 0 : Math.max(2, glyph.size / 16)
        border.color: glyph.shape === "ps" ? Qt.darker(glyph.tone, 1.6) : "#575B63"
        Rectangle {        // a stick press: a second ring
            visible: glyph.shape === "click"
            anchors.centerIn: parent
            width: parent.width * 0.62; height: width; radius: width / 2
            color: "transparent"; border.width: Math.max(2, glyph.size / 18); border.color: glyph.bone
        }
        Text {
            visible: ["face", "num", "click", "stick"].indexOf(glyph.shape) >= 0
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: glyph.g.text || ""
            color: glyph.shape === "face" ? glyph.ink : glyph.bone
            font.family: "IBM Plex Sans"; font.weight: Font.Bold
            font.pixelSize: glyph.size * ((glyph.g.text || "").length > 2 ? 0.3 : (glyph.shape === "click" ? 0.3 : 0.5))
        }
    }
    // stick direction: an arrow on the ring's edge
    Text {
        visible: glyph.shape === "stick"
        anchors.centerIn: parent
        textFormat: Text.PlainText; text: "▲"; color: glyph.bone
        font.pixelSize: glyph.size * 0.26
        rotation: ({ up: 0, right: 90, down: 180, left: 270 })[glyph.g.dir || "up"]
        transform: Translate {
            x: ({ left: -1, right: 1 })[glyph.g.dir || ""] * glyph.size * 0.36 || 0
            y: ({ up: -1, down: 1 })[glyph.g.dir || ""] * glyph.size * 0.36 || 0
        }
    }

    // PlayStation symbols
    Rectangle {
        visible: glyph.shape === "ps" && glyph.g.text === "square"
        anchors.centerIn: parent
        width: glyph.size * 0.42; height: width
        color: "transparent"; border.width: Math.max(2, glyph.size / 13); border.color: glyph.tone
    }
    Rectangle {
        visible: glyph.shape === "ps" && glyph.g.text === "circle"
        anchors.centerIn: parent
        width: glyph.size * 0.46; height: width; radius: width / 2
        color: "transparent"; border.width: Math.max(2, glyph.size / 13); border.color: glyph.tone
    }
    Repeater {
        model: glyph.shape === "ps" && glyph.g.text === "cross" ? 2 : 0
        Rectangle {
            required property int index
            anchors.centerIn: parent
            width: glyph.size * 0.56; height: Math.max(2, glyph.size / 13); radius: height / 2
            color: glyph.tone
            rotation: index === 0 ? 45 : -45
        }
    }
    Shape {
        visible: glyph.shape === "ps" && glyph.g.text === "triangle"
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: glyph.tone; strokeWidth: Math.max(2, glyph.size / 13); fillColor: "transparent"
            joinStyle: ShapePath.RoundJoin
            startX: glyph.size * 0.5; startY: glyph.size * 0.27
            PathLine { x: glyph.size * 0.75; y: glyph.size * 0.69 }
            PathLine { x: glyph.size * 0.25; y: glyph.size * 0.69 }
            PathLine { x: glyph.size * 0.5; y: glyph.size * 0.27 }
        }
    }

    // shoulder buttons and triggers, menu buttons, the touchpad
    Rectangle {
        visible: ["bumper", "trigger", "menu", "touch"].indexOf(glyph.shape) >= 0
        anchors.centerIn: parent
        width: glyph.wide
        height: glyph.shape === "bumper" ? glyph.size * 0.62 : glyph.shape === "trigger" ? glyph.size
                : glyph.size * 0.62
        radius: glyph.shape === "trigger" ? glyph.size * 0.28 : height / 2
        color: glyph.body; border.width: Math.max(2, glyph.size / 16); border.color: "#575B63"
        Rectangle {       // a trigger: a lighter band where the finger rests
            visible: glyph.shape === "trigger"
            anchors.top: parent.top; anchors.topMargin: parent.border.width * 2; anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width * 0.5; height: Math.max(2, glyph.size / 14); radius: height / 2; color: "#575B63"
        }
        Text {
            id: menuText
            anchors.centerIn: parent
            anchors.verticalCenterOffset: glyph.shape === "trigger" ? glyph.size * 0.06 : 0
            textFormat: Text.PlainText; text: glyph.g.text || ""; color: glyph.bone
            font.family: "IBM Plex Sans"; font.weight: Font.Bold
            font.pixelSize: glyph.size * (glyph.shape === "menu" || glyph.shape === "touch" ? 0.3 : 0.38)
        }
    }

    // the d-pad: a cross with the pressed arm lit
    Item {
        visible: glyph.shape === "dpad"
        anchors.centerIn: parent
        width: glyph.size; height: glyph.size
        Rectangle { anchors.centerIn: parent; width: parent.width * 0.34; height: parent.height * 0.94; radius: glyph.size / 14; color: glyph.body; border.width: Math.max(1, glyph.size / 22); border.color: "#575B63" }
        Rectangle { anchors.centerIn: parent; width: parent.width * 0.94; height: parent.height * 0.34; radius: glyph.size / 14; color: glyph.body; border.width: Math.max(1, glyph.size / 22); border.color: "#575B63" }
        Rectangle { anchors.centerIn: parent; width: parent.width * 0.3; height: width; color: glyph.body }
        Rectangle {
            readonly property string d: glyph.g.dir || "up"
            width: glyph.size * (d === "up" || d === "down" ? 0.26 : 0.36)
            height: glyph.size * (d === "up" || d === "down" ? 0.36 : 0.26)
            radius: glyph.size / 18
            color: glyph.bone
            x: d === "left" ? glyph.size * 0.06 : d === "right" ? glyph.size * 0.58 : glyph.size * 0.37
            y: d === "up" ? glyph.size * 0.06 : d === "down" ? glyph.size * 0.58 : glyph.size * 0.37
        }
    }

    // keyboard key
    Rectangle {
        visible: glyph.shape === "key"
        anchors.fill: parent
        radius: glyph.size / 7
        color: glyph.bone
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: glyph.size / 9; radius: parent.radius; color: "#B9B5AB" }
        Text {
            id: keyText
            anchors.centerIn: parent; anchors.verticalCenterOffset: -glyph.size / 20
            textFormat: Text.PlainText; text: glyph.g.text || ""; color: glyph.ink
            font.family: "IBM Plex Sans"; font.weight: Font.Bold
            font.pixelSize: glyph.size * ((glyph.g.text || "").length > 2 ? 0.34 : 0.48)
        }
    }
}
