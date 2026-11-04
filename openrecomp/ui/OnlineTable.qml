import QtQuick

// Standalone implementation avoids Qt inline-component incubation deadlocks.
Item {
    id: table
    objectName: "onlineTable"
    property var line: ({})
    property var columns: []
    signal selected(int index)
    signal activated(int index)
    height: line.kind === "thead" ? heading.implicitHeight + 16 : Math.max(44, body.implicitHeight + 20)
    Rectangle {
        anchors.fill: parent; radius: 4
        color: table.line.focused || !!(table.line.feedback || {}).text ? Theme.raised : "#1B1E23"
        border.width: table.line.focused ? Theme.focusWidth : !!(table.line.feedback || {}).text ? 2 : 0
        border.color: Theme.focus
    }
    Row {
        id: heading
        visible: table.line.kind === "thead"; x: 10; y: 8; width: Math.max(1, parent.width - 20)
        Repeater {
            model: table.line.kind === "thead" ? table.line.cols || [] : []
            OnlineHelp { required property var modelData; width: Math.max(1, heading.width * modelData.w); text: modelData.label || ""; font.weight: Font.DemiBold; rightPadding: 10 }
        }
    }
    Column {
        id: body
        visible: table.line.kind !== "thead"
        x: 10; y: 10; width: Math.max(1, parent.width - 20); spacing: 10
        Row {
            id: cells
            width: parent.width
            Repeater {
                model: table.line.kind !== "thead" ? table.line.cells || [] : []
                Item {
                    id: cell
                    required property var modelData
                    required property int index
                    width: Math.max(12, cells.width * ((table.columns[index] || {}).w || 0))
                    height: textColumn.implicitHeight
                    Column {
                        id: textColumn; width: Math.max(1, cell.width - 10); spacing: 2
                        Row {
                            visible: (cell.modelData.bars || 0) > 0; height: visible ? 20 : 0; spacing: 3
                            Repeater {
                                model: parent.visible ? 4 : 0
                                Rectangle {
                                    required property int index
                                    width: 4; height: 6 + index * 4; anchors.bottom: parent.bottom
                                    color: index < (cell.modelData.bars || 0) ? Theme.success : Theme.border
                                }
                            }
                        }
                        Image { visible: !!cell.modelData.plate; source: cell.modelData.plate || ""; width: Math.min(60, textColumn.width); height: visible ? 30 : 0; fillMode: Image.PreserveAspectFit; asynchronous: true }
                        Image { visible: !!cell.modelData.face; source: cell.modelData.face || ""; width: 28; height: visible ? 28 : 0; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                        Item {
                            visible: !!cell.modelData.locked; width: 20; height: visible ? 24 : 0
                            Rectangle { x: 5; y: 1; width: 10; height: 13; radius: 5; color: "transparent"; border.width: 2; border.color: Theme.value }
                            Rectangle { x: 2; y: 10; width: 16; height: 12; radius: 2; color: Theme.value }
                        }
                        OnlineLabel { width: parent.width; visible: !!text; text: cell.modelData.text || ""; font.weight: cell.modelData.bold ? Font.DemiBold : Font.Normal }
                        OnlineHelp { objectName: "onlineAreaLanguage"; width: parent.width; visible: !!cell.modelData.tags; text: cell.modelData.tags || "" }
                        OnlineHelp { width: parent.width; visible: !!cell.modelData.hint; text: cell.modelData.hint || "" }
                    }
                }
            }
        }
        ActionReceipt { width: parent.width; receipt: table.line.feedback || ({}) }
        OnlineHelp { width: parent.width; visible: !!table.line.focused && !!table.line.actionHint; text: table.line.actionHint || ""; color: Theme.value }
        Flow {
            id: actions
            visible: (table.line.buttons || []).length > 0
            width: parent.width; spacing: 8
            Repeater {
                model: table.line.buttons || []
                OnlineButton { required property var modelData; b: modelData; maxW: actions.width; onActivated: index => table.activated(index) }
            }
        }
    }
    TapHandler {
        id: rowTap
        enabled: table.line.index !== undefined
        onTapped: table.selected(table.line.index)
        onDoubleTapped: table.activated(table.line.index)
    }
    Interaction {
        handler: rowTap; selected: !!table.line.focused
        disabled: table.line.index === undefined
        role: Accessible.ListItem
        name: (table.line.cells || []).map(c => c.text || "").join(". ") + ". " + ((table.line.feedback || {}).text || "") + ". " + (table.line.actionHint || "")
        onActivated: table.activated(table.line.index)
    }
}
