import QtQuick

Rectangle {
    id: button
    objectName: "onlineSecondaryButton"
    property var b: ({})
    property color accent: Theme.gameAccent
    property int maxW: 420
    property int fontSize: 16
    property bool strong: false
    property bool primary: false
    property var glyph: ({})
    readonly property real glyphWidth: buttonGlyph.visible ? buttonGlyph.width + 10 : 0
    readonly property real captionHeight: Math.max(caption.implicitHeight, buttonGlyph.visible ? buttonGlyph.height : 0)
    readonly property real feedbackHeight: buttonFeedback.visible ? buttonFeedback.implicitHeight + 8 : 0
    readonly property bool failed: (b.feedback || {}).kind === "error"
    signal activated(int index)
    width: Math.min(maxW, Math.max(100, caption.implicitWidth + glyphWidth + 32))
    height: Math.max(Theme.target(44), captionHeight + 20) + feedbackHeight
    radius: 5
    color: failed ? "#321B22" : primary ? Theme.primaryFill : b.focused ? Theme.selected : strong ? Theme.raised : Theme.card
    border.width: b.focused ? Theme.focusWidth : 1; border.color: b.focused ? Theme.focus : Theme.border
    opacity: b.disabled ? 0.45 : 1
    Item {
        id: content
        x: (button.width - width) / 2; y: (button.height - button.feedbackHeight - height) / 2
        width: Math.min(caption.implicitWidth + button.glyphWidth, button.width - 28); height: button.captionHeight
        Glyph { id: buttonGlyph; objectName: "onlineButtonGlyph"; visible: !!button.glyph.text; anchors.verticalCenter: parent.verticalCenter; g: Object.assign({}, button.glyph, {ink: !!button.b.focused || button.primary}); size: 28 }
        OnlineLabel {
            id: caption
            x: button.glyphWidth; width: parent.width - x; anchors.verticalCenter: parent.verticalCenter
            horizontalAlignment: Text.AlignHCenter
            font.pixelSize: Theme.onlinePx(button.fontSize)
            text: (button.b.label || "") + (button.b.value ? ": " + button.b.value : "")
            color: button.failed ? Theme.text : button.primary ? Theme.primaryText : button.b.focused ? Theme.ground : Theme.text
        }
    }
    ActionReceipt { id: buttonFeedback; x: 14; y: button.height - button.feedbackHeight + 2; width: parent.width - 28; receipt: button.b.feedback || ({}); color: button.failed ? Theme.error : button.primary ? Theme.primaryText : button.b.focused ? Theme.ground : Theme.text }
    TapHandler { id: buttonTap; onTapped: if (!button.b.disabled) button.activated(button.b.index === undefined ? -1 : button.b.index) }
    Interaction { handler: buttonTap; selected: !!button.b.focused; disabled: !!button.b.disabled; name: (button.b.label || "") + ". " + (button.b.value || "") + ". " + (button.b.hint || "") + ". " + ((button.b.feedback || {}).text || ""); onActivated: if (!button.b.disabled) button.activated(button.b.index === undefined ? -1 : button.b.index) }

}
