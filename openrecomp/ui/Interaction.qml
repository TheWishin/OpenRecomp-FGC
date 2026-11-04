import QtQuick

// Pointer and assistive-technology feedback shares the semantic pad selection.
Item {
    id: interaction
    objectName: "interactionFeedback"
    width: 0; height: 0
    z: 20
    property var handler: null
    property bool selected: false
    property bool disabled: false
    property string name: labels(parent)
    property int role: Accessible.Button
    signal activated()
    function labels(item) {
        var parts = []
        for (var i = 0; i < item.children.length; i++) {
            var child = item.children[i]
            if (child === interaction || !child.visible) continue
            if (child.text !== undefined && child.text) parts.push(child.text)
            else if (child.children) {
                var caption = labels(child)
                if (caption) parts.push(caption)
            }
        }
        return parts.join(". ")
    }
    Item {
        objectName: "accessibleTarget"
        x: -interaction.x; y: -interaction.y
        width: interaction.parent.width; height: interaction.parent.height
        Accessible.role: interaction.role
        Accessible.name: interaction.name
        Accessible.focused: interaction.selected
        Accessible.ignored: interaction.disabled || !visible
        Accessible.onPressAction: if (!interaction.disabled) interaction.activated()
        HoverHandler { id: hover; enabled: !interaction.disabled }
        Rectangle {
            objectName: "focusRing"
            anchors.fill: parent
            radius: 4
            visible: interaction.selected || hover.hovered || !!(interaction.handler && interaction.handler.pressed)
            color: "transparent"
            border.color: Theme.focus
            border.width: interaction.handler && interaction.handler.pressed ? Theme.focusWidth + 2 : interaction.selected ? Theme.focusWidth : 2
        }
    }
}
