import QtQuick

// One button row inside a Build card: label left, its value (a file name, Missing, On/Off) right; the focused row is
// bone with the confirm prompt, a hold row fills while held.
Rectangle {
    id: action
    objectName: "buildAction"
    required property var root
    property var a: ({})
    property color accent: "#ECE9E1"
    property bool compact: false
    height: compact ? 58 : 66
    color: a.focused ? root.bone : (compact ? "transparent" : "#1E2024")
    clip: true
    Rectangle { height: parent.height; width: parent.width * (action.a.holdPct || 0); color: action.accent }
    Text {
        objectName: "buildActionLabel"
        x: 24; width: actionRight.x - x - 16; height: parent.height - 8; anchors.verticalCenter: parent.verticalCenter
        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; fontSizeMode: Text.Fit; minimumPixelSize: 18
        textFormat: Text.PlainText; text: action.a.label || ""
        color: action.a.focused ? "#0E0F11" : (action.a.disabled ? "#6B6E75" : (action.a.hold ? action.accent : action.root.textC))
        font.family: action.root.sans; font.weight: Font.DemiBold; font.pixelSize: action.compact ? 26 : 28
    }
    Row {
        id: actionRight
        anchors.right: parent.right; anchors.rightMargin: 20; anchors.verticalCenter: parent.verticalCenter; spacing: 14
        Text {
            visible: !!action.a.value; anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, 420); elide: Text.ElideMiddle
            textFormat: Text.PlainText; text: action.a.value || ""
            color: action.a.focused ? "#0E0F11" : (action.a.missing ? action.accent : (action.a.ok ? "#6CC287" : action.root.muted))
            font.family: action.root.mono; font.weight: Font.Medium; font.pixelSize: 24
        }
        Text { textFormat: Text.PlainText; visible: !!action.a.verb; width: Math.min(implicitWidth, 220); elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter; text: action.a.verb || ""; color: "#0E0F11"; font.family: action.root.sans; font.weight: Font.DemiBold; font.pixelSize: 24 }
        Glyph { visible: !!action.a.verb; g: action.root.v.confirmInk; size: 40; anchors.verticalCenter: parent.verticalCenter }
    }
    TapHandler { onTapped: action.root.backend.clickRow(action.a.index) }
}
