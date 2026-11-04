import QtQuick

// One type scale for every Online surface, in the launcher's 1920-wide stage.
QtObject {

    component BaseText: Text {
        textFormat: Text.PlainText
        color: Theme.text
        font.family: "IBM Plex Sans"
        wrapMode: Text.Wrap
    }
    component PageTitle: BaseText {
        objectName: "onlinePageTitle"
        Accessible.role: Accessible.Heading
        Accessible.name: text
        font.family: "Big Shoulders"; font.weight: Font.Black
        font.pixelSize: Theme.onlinePx(28)
    }
    component SectionHeader: BaseText {
        objectName: "onlineSectionHeader"
        Accessible.role: Accessible.Heading
        Accessible.name: text
        font.weight: Font.DemiBold; font.pixelSize: Math.max(Theme.onlinePx(20), Theme.onlinePx(14) * 1.14)
    }
    component FieldLabel: OnlineLabel {}
    component Value: BaseText {
        objectName: "onlineValue"
        font.weight: Font.DemiBold; font.pixelSize: Theme.onlinePx(16)
    }
    component HelpText: OnlineHelp {}
    component SecondaryButton: OnlineButton {}
    component PrimaryButton: SecondaryButton {
        objectName: "onlinePrimaryButton"
        primary: true; height: Math.max(Theme.target(52), captionHeight + 20) + feedbackHeight
    }
    component Chip: SecondaryButton {
        objectName: "onlineChip"
        fontSize: 14
        height: Math.max(Theme.target(44), captionHeight + 20) + feedbackHeight
        radius: 17
    }
    component SectionCard: Rectangle {
        color: Theme.card; radius: 8
        border.width: 1; border.color: Theme.border
    }
    component FieldRow: Rectangle {
        id: field
        property var root: null
        property var b: ({})
        readonly property bool editable: !!root && !!b.fieldId
        readonly property bool failed: (b.feedback || {}).kind === "error"
        signal activated(int index)
        width: parent ? parent.width : 400
        height: editable ? nativeField.height + 16 : Math.max(48, Math.max(label.implicitHeight, value.implicitHeight) + 22 + (help.visible ? help.implicitHeight + 5 : 0) + (fieldFeedback.visible ? fieldFeedback.implicitHeight + 10 : 0))
        radius: 4
        color: failed ? "#321B22" : b.focused ? Theme.selected : "#1B1E23"
        opacity: b.disabled ? 0.5 : 1
        EditableField { id: nativeField; visible: field.editable; x: 8; y: 8; width: parent.width - 16; root: field.root; field: parent.b; labelColor: field.b.focused && !field.failed ? Theme.inkHelp : Theme.muted }
        FieldLabel {
            id: label
            visible: !field.editable
            x: 14; y: 11; width: field.width * (field.b.value ? 0.54 : 0.94) - 20
            text: field.b.label || ""; color: field.b.focused && !field.failed ? Theme.ground : Theme.text
        }
        Value {
            id: value
            visible: !field.b.toggle && !field.editable
            x: field.width * 0.56; y: 9; width: field.width * 0.44 - 14
            horizontalAlignment: Text.AlignRight
            text: field.b.cycler ? "‹ " + (field.b.value || "") + " ›" : field.b.value || ""
            color: field.b.focused && !field.failed ? Theme.ground : Theme.value
        }
        Row {
            visible: !!field.b.toggle
            anchors.right: parent.right; anchors.rightMargin: 14; y: 10; spacing: 10
            Value { text: field.b.value || ""; color: field.b.focused && !field.failed ? Theme.ground : Theme.value }
            Rectangle {
                width: 48; height: 26; radius: 13; color: field.b.on ? Theme.value : "#555A62"
                Rectangle { x: field.b.on ? 25 : 3; y: 3; width: 20; height: 20; radius: 10; color: Theme.selected }
            }
        }
        HelpText {
            id: help
            x: 14; y: Math.max(label.implicitHeight + label.y, value.implicitHeight + value.y) + 5
            width: field.width - 28; visible: !!field.b.hint && !field.editable
            text: field.b.hint || ""; color: field.b.focused && !field.failed ? Theme.inkHelp : Theme.muted
        }
        Feedback {
            id: fieldFeedback; width: parent.width - 28; x: 14
            y: help.visible ? help.y + help.implicitHeight + 6 : Math.max(label.implicitHeight + label.y, value.implicitHeight + value.y) + 6
            receipt: field.b.feedback || ({})
            color: field.b.focused && !field.failed ? Theme.ground : statusColour
        }
        TapHandler { id: fieldTap; enabled: !field.editable; onTapped: field.activated(field.b.index === undefined ? -1 : field.b.index) }
        Interaction { visible: !field.editable; handler: fieldTap; selected: !!field.b.focused; disabled: !!field.b.disabled; name: (field.b.label || "") + ". " + (field.b.value || ""); onActivated: field.activated(field.b.index === undefined ? -1 : field.b.index) }
    }
    component Feedback: ActionReceipt {}
    component Table: OnlineTable {}

}
