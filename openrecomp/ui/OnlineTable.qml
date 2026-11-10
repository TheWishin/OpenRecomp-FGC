import QtQuick

// Standalone implementation avoids Qt inline-component incubation deadlocks.
Item {
    id: table
    objectName: "onlineTable"
    property var line: ({})
    property var columns: []
    signal selected(int index)
    signal activated(int index)
    height: line.kind === "thead" ? heading.implicitHeight + 12 : Math.max(44, body.implicitHeight + 16)
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
        x: 8; y: 8; width: Math.max(1, parent.width - 16); spacing: 4
        Row {
            id: cells
            width: parent.width
            Repeater {
                model: table.line.kind !== "thead" ? table.line.cells || [] : []
                Item {
                    id: cell
                    objectName: "onlineTableCell"
                    required property var modelData
                    required property int index
                    width: Math.max(12, cells.width * ((table.columns[index] || {}).w || 0))
                    height: Math.max(1, textColumn.implicitHeight, visuals.implicitHeight)
                    Row {
                        id: visuals; spacing: 4
                        Row {
                            visible: (cell.modelData.bars || 0) > 0; width: visible ? 24 : 0; height: visible ? 20 : 0; spacing: 2
                            Repeater {
                                model: parent.visible ? 4 : 0
                                Rectangle {
                                    required property int index
                                    width: 4; height: 6 + index * 4; anchors.bottom: parent.bottom
                                    color: index < (cell.modelData.bars || 0) ? (Theme.quiet ? Theme.mark : Theme.success) : Theme.border
                                }
                            }
                        }
                        Image { visible: !!cell.modelData.plate; source: cell.modelData.plate || ""; width: visible ? Math.min(48, cell.width * .35) : 0; height: visible ? 24 : 0; fillMode: Image.PreserveAspectFit; asynchronous: true }
                        FighterPortrait { objectName: "onlineTableFighter"; visible: !!cell.modelData.character || !!cell.modelData.playerPortrait; source: cell.modelData.face || ""; name: ""; width: visible ? 24 : 0; height: visible ? 24 : 0 }
                        Image { visible: !!cell.modelData.face && !cell.modelData.character && !cell.modelData.playerPortrait; source: cell.modelData.face || ""; width: visible ? 24 : 0; height: visible ? 24 : 0; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                        Item {
                            visible: !!cell.modelData.locked; width: visible ? 20 : 0; height: visible ? 24 : 0
                            Rectangle { x: 5; y: 1; width: 10; height: 13; radius: 5; color: "transparent"; border.width: 2; border.color: Theme.value }
                            Rectangle { x: 2; y: 10; width: 16; height: 12; radius: 2; color: Theme.value }
                        }
                    }
                    Column {
                        id: textColumn; x: visuals.width ? visuals.width + 4 : 0; width: Math.max(1, cell.width - x - 8); spacing: 2
                        OnlineLabel { width: parent.width; visible: !!text; text: cell.modelData.text || ""; font.weight: cell.modelData.bold ? Font.DemiBold : Font.Normal; wrapMode: cell.modelData.character ? Text.NoWrap : Text.Wrap; elide: cell.modelData.character ? Text.ElideRight : Text.ElideNone }
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
