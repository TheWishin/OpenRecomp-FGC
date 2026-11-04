import QtQuick

Rectangle {
    id: button
    objectName: "onlineSecondaryButton"
    property var b: ({})
    property color accent: "#BE7449"
    property int maxW: 420
    property int fontSize: 16
    property bool strong: false
    property bool primary: false
    readonly property real captionHeight: caption.implicitHeight
    readonly property real feedbackHeight: buttonFeedback.visible ? buttonFeedback.implicitHeight + 8 : 0
    readonly property bool failed: (b.feedback || {}).kind === "error"
    signal activated(int index)
    width: Math.min(maxW, Math.max(100, caption.implicitWidth + 32))
    height: Math.max(Theme.target(44), caption.implicitHeight + 20) + feedbackHeight
    radius: 5
    color: failed ? "#321B22" : b.focused ? Theme.selected : primary ? Theme.readableAccent(accent) : strong ? "#272B31" : "#1C1F24"
    border.width: b.focused ? Theme.focusWidth : 1; border.color: b.focused ? Theme.focus : Theme.border
    opacity: b.disabled ? 0.45 : 1
    OnlineLabel {
        id: caption
        x: (button.width - width) / 2; y: 10; width: Math.min(implicitWidth, button.width - 28)
        horizontalAlignment: Text.AlignHCenter
        font.pixelSize: Theme.onlinePx(button.fontSize)
        text: (button.b.label || "") + (button.b.value ? ": " + button.b.value : "")
        color: button.failed ? Theme.text : button.b.focused || button.primary ? Theme.ground : Theme.text
    }
    ActionReceipt { id: buttonFeedback; x: 14; y: caption.y + caption.implicitHeight + 6; width: parent.width - 28; receipt: button.b.feedback || ({}); color: button.failed ? Theme.error : button.b.focused || button.primary ? Theme.ground : Theme.text }
    TapHandler { id: buttonTap; onTapped: if (!button.b.disabled) button.activated(button.b.index === undefined ? -1 : button.b.index) }
    Rectangle { visible: button.primary; x: 12; y: parent.height - 5; width: parent.width - 24; height: 2; color: Theme.ground }
    Interaction { handler: buttonTap; selected: !!button.b.focused; disabled: !!button.b.disabled; name: (button.b.label || "") + ". " + (button.b.value || "") + ". " + (button.b.hint || "") + ". " + ((button.b.feedback || {}).text || ""); onActivated: if (!button.b.disabled) button.activated(button.b.index === undefined ? -1 : button.b.index) }

}
