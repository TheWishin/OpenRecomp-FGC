import QtQuick

// Cards scroll to the focused controller row; all rows remain in the projection.
Flickable {
    id: view
    required property var root
    property var sections: []
    contentWidth: width
    contentHeight: cards.height
    clip: true; boundsBehavior: Flickable.StopAtBounds
    function focused(b) { return !!b.focused || (b.buttons || []).some(b => b.focused) }
    function revealFocus() {
        for (var c = 0; c < cardRepeater.count; ++c) {
            var card = cardRepeater.itemAt(c)
            if (!card) continue
            for (var r = 0; r < card.rows.count; ++r) {
                var row = card.rows.itemAt(r)
                if (row && focused(row.l)) {
                    var top = card.y + card.contentY + row.y
                    if (row.height > height || top < contentY) contentY = top
                    else if (top + row.height > contentY + height) contentY = top + row.height - height
                    contentY = Math.max(0, Math.min(contentY, Math.max(0, contentHeight - height)))
                    return
                }
            }
        }
    }
    onSectionsChanged: Qt.callLater(revealFocus)
    onHeightChanged: Qt.callLater(revealFocus)
    onContentHeightChanged: Qt.callLater(revealFocus)
    Column {
        id: cards
        width: view.width; spacing: 8
        onPositioningComplete: Qt.callLater(view.revealFocus)
        Repeater {
            id: cardRepeater
            model: view.sections
            OnlineStyle.SectionCard {
                id: card
                required property var modelData
                property alias rows: rowRepeater
                readonly property real contentY: rowsColumn.y
                width: cards.width; height: rowsColumn.y + rowsColumn.height + 12
                OnlineStyle.SectionHeader { id: header; visible: !!text; x: 12; y: 12; width: parent.width - 24; text: card.modelData.title || "" }
                Column {
                    id: rowsColumn
                    onPositioningComplete: Qt.callLater(view.revealFocus)
                    x: 8; y: header.visible ? header.y + header.height + 8 : 8; width: parent.width - 16; spacing: 4
                    Repeater {
                        id: rowRepeater
                        model: card.modelData.lines || []
                        Item {
                            id: row
                            required property var modelData
                            required property int index
                            readonly property var l: modelData
                            width: rowsColumn.width
                            height: l.kind === "note" ? note.implicitHeight + 12 : l.kind === "bar" ? buttons.implicitHeight : l.kind === "trow" || l.kind === "thead" ? table.height : field.height
                            OnlineStyle.HelpText {
                                id: note; visible: row.l.kind === "note"; x: 10; y: 6; width: parent.width - 20; text: row.l.label || ""
                            }
                            Flow {
                                id: buttons; visible: row.l.kind === "bar"; width: parent.width; spacing: 8
                                Repeater {
                                    model: row.l.buttons || []
                                    OnlineStyle.SecondaryButton { required property var modelData; b: modelData; maxW: buttons.width; onActivated: i => view.root.backend.clickRow(i) }
                                }
                            }
                            OnlineStyle.Table {
                                id: table; visible: row.l.kind === "thead" || row.l.kind === "trow"; width: parent.width; line: row.l
                                columns: {
                                    var lines = card.modelData.lines || []
                                    for (var n = row.index; n >= 0; --n) if (lines[n].kind === "thead") return lines[n].cols
                                    return []
                                }
                                onActivated: i => view.root.backend.clickRow(i)
                                onSelected: i => view.root.backend.focusOnlineRow(i)
                            }
                            OnlineStyle.FieldRow {
                                id: field; root: view.root; visible: row.l.kind === "row"; width: parent.width; b: row.l
                                onActivated: i => view.root.backend.clickRow(i)
                            }
                        }
                    }
                }
            }
        }
    }
}
