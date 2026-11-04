import QtQuick

Rectangle {
    id: action
    required property var root
    property var b: ({})
    property string label: b.label || ""
    property string accessibleLabel: label
    property string icon: ""
    property var glyph: ({})
    property bool primary: false
    property bool compact: false
    property bool iconOnly: false
    signal activated()
    implicitWidth: Math.max(compact ? 60 : 100, caption.implicitWidth + 24 + (icon ? 36 : glyph.text ? buttonGlyph.width + 16 : 0))
    implicitHeight: compact ? Math.max(30, caption.implicitHeight + 8) : Math.max(Theme.target(48), caption.implicitHeight + 20)
    width: implicitWidth; height: implicitHeight
    radius: 7
    color: primary ? Theme.readableAccent(root.v.accent) : Theme.raised
    border.width: b.focused ? Theme.focusWidth : 1
    border.color: b.focused ? Theme.focus : Theme.border
    opacity: b.disabled ? 0.45 : 1
    property real selectionScale: !compact && (b.focused || hover.hovered) ? 1.025 : 1
    scale: root.reducedMotion ? 1 : selectionScale
    Behavior on selectionScale { enabled: !action.root.reducedMotion; NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
    readonly property color ink: primary ? Theme.ground : Theme.text
    ArcadeIcon { visible: !!action.icon; x: action.iconOnly ? (parent.width - width) / 2 : 12; anchors.verticalCenter: parent.verticalCenter; width: 24; height: 24; kind: action.icon; ink: action.ink }
    Glyph { id: buttonGlyph; objectName: "arcadeActionGlyph"; visible: !!action.glyph.text && !action.icon; x: 10; anchors.verticalCenter: parent.verticalCenter; g: action.glyph; size: 28 }
    Text {
        id: caption
        visible: !action.iconOnly
        objectName: "arcadeActionLabel"
        x: action.icon ? 46 : action.glyph.text ? buttonGlyph.x + buttonGlyph.width + 8 : 12; width: parent.width - x - 12
        anchors.verticalCenter: parent.verticalCenter
        height: parent.height - (action.compact ? 4 : 12); verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText; text: action.label; elide: Text.ElideRight
        color: action.ink; font.family: action.root.sans; font.weight: Font.DemiBold; font.pixelSize: action.compact ? Theme.onlinePx(14) : Theme.px(20)
    }
    HoverHandler { id: hover; enabled: !action.b.disabled }
    TapHandler { id: tap; enabled: !action.b.disabled; onTapped: action.activated() }
    Interaction { handler: tap; selected: !!action.b.focused; disabled: !!action.b.disabled; name: action.accessibleLabel; onActivated: action.activated() }
}
