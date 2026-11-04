import QtQuick

// The native editor owns its caret, selection, clipboard and IME. Nav owns committed drafts and submission.
Item {
    id: control
    required property var root
    property var field: ({})
    property bool showLabel: true
    property string placeholder: ""
    property color labelColor: Theme.muted
    readonly property string fieldId: field.fieldId || ""
    readonly property bool editing: !!root && root.v.nativeEdit === fieldId && fieldId !== "" && (!root.v.overlay || root.v.overlay === "native")
    readonly property bool secret: !!field.secret
    property alias editor: input
    signal submitted()
    signal cancelled()
    signal completeRequested(string text, int cursor)
    objectName: "editableField"
    height: (showLabel ? caption.implicitHeight + 8 : 0) + Math.max(44 / Math.max(0.5, Theme.viewportScale), input.implicitHeight + 20)
    function syncFocus() {
        if (editing && visible) input.forceActiveFocus()
        else if (input.activeFocus) root.focusStage()
    }
    onEditingChanged: Qt.callLater(syncFocus)
    onVisibleChanged: Qt.callLater(syncFocus)
    Component.onCompleted: Qt.callLater(syncFocus)
    Text {
        id: caption; visible: control.showLabel
        width: parent.width; text: control.field.label || ""; textFormat: Text.PlainText
        wrapMode: Text.Wrap; color: control.labelColor; font.family: "IBM Plex Sans"; font.pixelSize: Theme.px(16)
    }
    Rectangle {
        id: box
        y: control.showLabel ? caption.implicitHeight + 8 : 0
        width: parent.width; height: parent.height - y; radius: 4
        color: Theme.ground; border.width: control.editing || control.field.focused ? Theme.focusWidth : 1
        border.color: control.field.error ? Theme.error : control.editing || control.field.focused ? Theme.focus : Theme.border
        TextInput {
            id: input
            objectName: "nativeTextInput"
            x: 12; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter
            text: control.field.draft || ""
            color: Theme.text; selectionColor: Theme.selected; selectedTextColor: Theme.ground
            font.family: "IBM Plex Sans"; font.pixelSize: Theme.px(20)
            maximumLength: control.field.limit || 256
            echoMode: control.secret ? TextInput.Password : TextInput.Normal
            inputMethodHints: control.secret ? Qt.ImhHiddenText | Qt.ImhSensitiveData | Qt.ImhNoPredictiveText : Qt.ImhNone
            selectByMouse: true; activeFocusOnPress: true; clip: true
            enabled: !control.field.disabled && control.fieldId !== ""
            Accessible.role: Accessible.EditableText
            Accessible.name: control.field.label || control.placeholder
            Accessible.description: control.field.disabled ? (control.field.hint || control.field.error || "") : ""
            Accessible.passwordEdit: control.secret
            onActiveFocusChanged: {
                if (activeFocus && !control.editing) control.root.backend.beginEdit(control.fieldId)
                else if (!activeFocus && control.editing) control.root.backend.finishEdit(control.fieldId, false)
            }
            onTextEdited: if (!inputMethodComposing) control.root.backend.editText(control.fieldId, text)
            onInputMethodComposingChanged: if (!inputMethodComposing && control.editing) control.root.backend.editText(control.fieldId, text)
            Keys.priority: Keys.BeforeItem
            Keys.onPressed: event => {
                // Composition Enter belongs to the input method. Never send or leave while preedit is active.
                if (inputMethodComposing) { event.accepted = false; return }
                if (event.key === Qt.Key_Escape) {
                    control.root.backend.finishEdit(control.fieldId, false)
                    control.root.focusStage(); control.cancelled(); event.accepted = true
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    if (!event.isAutoRepeat) {
                        control.root.backend.editText(control.fieldId, text)
                        control.root.backend.finishEdit(control.fieldId, !!control.field.submitId)
                        control.root.focusStage(); control.submitted()
                    }
                    event.accepted = true
                } else if (event.key === Qt.Key_Tab && !event.modifiers) {
                    control.completeRequested(text, cursorPosition); event.accepted = true
                } else event.accepted = false
            }
            Keys.onReleased: event => { event.accepted = true }
        }
        Text {
            visible: !input.text && !input.preeditText
            x: 12; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter
            text: control.placeholder; textFormat: Text.PlainText; color: Theme.muted
            font: input.font; elide: Text.ElideRight
        }
    }
}
