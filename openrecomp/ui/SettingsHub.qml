import QtQuick

Item {
    id: page
    required property var root
    readonly property var s: root.v.settingsPage || ({})
    readonly property var d: s.detail || ({})
    Row {
        id: groupStrip
        objectName: "settingsGroups"
        x: 24; y: 8; width: page.width - 48; spacing: 8
        Repeater {
            model: page.s.tabs || []
            OnlineStyle.SecondaryButton {
                required property var modelData
                b: ({label: modelData.label, focused: modelData.active})
                maxW: (groupStrip.width - 32) / 5
                width: maxW
                onActivated: page.root.backend.selectSettingsTab(modelData.id)
            }
        }
    }
    Flickable {
        id: list
        objectName: "settingsList"
        x: 24; y: groupStrip.y + groupStrip.height + 12; width: (page.width - 72) * 0.64; height: page.height - y - 16
        contentHeight: lines.height; clip: true; boundsBehavior: Flickable.StopAtBounds
        function reveal() {
            for (var n = 0; n < rows.count; ++n) {
                var row = rows.itemAt(n)
                if (row && row.l.focused) {
                    if (row.y < contentY) contentY = row.y
                    else if (row.y + row.height > contentY + height) contentY = row.y + row.height - height
                    return
                }
            }
        }
        Connections { target: page.root.backend; function onViewChanged() { Qt.callLater(list.reveal) } }
        Column {
            id: lines; width: list.width - 8; spacing: 4
            Repeater {
                id: rows
                model: page.s.tabLines || []
                Item {
                    id: line
                    objectName: "settingsCompactRow"
                    required property var modelData
                    readonly property var l: modelData
                    width: lines.width
                    height: l.kind === "group" ? heading.height + 16 : Math.max(Theme.target(44), Math.max(label.implicitHeight, value.implicitHeight) + 16)
                    OnlineStyle.SectionHeader { id: heading; visible: line.l.kind === "group"; x: 12; y: 8; width: parent.width - 24; text: line.l.label || "" }
                    Rectangle {
                        visible: line.l.kind === "setting"
                        anchors.fill: parent; radius: 5
                        color: line.l.focused ? Theme.selected : Theme.card
                        Rectangle { visible: !!line.l.focused; width: 5; height: parent.height; color: Theme.readableAccent(page.root.v.accent) }
                        Text {
                            id: label; x: 16; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.62 - 32
                            text: line.l.label || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap
                            color: line.l.focused ? "#0E0F11" : Theme.text
                            font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.onlinePx(16)
                        }
                        Text {
                            id: value; x: parent.width * 0.64; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.36 - 16
                            text: line.l.cycler ? "\u2039  " + (line.l.value || "") + "  \u203a" : line.l.value || line.l.verb || ""
                            textFormat: Text.PlainText; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignRight
                            color: line.l.focused ? "#0E0F11" : Theme.value
                            font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: Theme.onlinePx(16)
                        }
                        TapHandler { id: tap; onTapped: page.root.backend.clickRow(line.l.index) }
                        Interaction { handler: tap; selected: !!line.l.focused; disabled: !!line.l.disabled; name: (line.l.label || "") + ". " + (line.l.value || "") + ". " + (line.l.hint || ""); onActivated: page.root.backend.clickRow(line.l.index) }
                    }
                }
            }
        }
    }
    OnlineStyle.SectionCard {
        objectName: "settingsDetail"
        x: list.x + list.width + 16; y: list.y; width: page.width - x - 24; height: list.height
        Flickable {
            anchors.fill: parent; anchors.margins: 24; contentHeight: detailContent.height; clip: true
            Column {
                id: detailContent
                objectName: "settingsDetailContent"
                width: parent.width; spacing: 12
                OnlineStyle.HelpText { width: parent.width; text: page.d.kicker || ""; color: Theme.value }
                OnlineStyle.PageTitle { width: parent.width; text: page.d.title || "" }
                OnlineStyle.HelpText { width: parent.width; text: page.d.lead || "" }
                OnlineStyle.HelpText { width: parent.width; visible: !!page.s.adapterEmptyHint; text: page.s.adapterEmptyHint || "" }
                Column {
                    width: parent.width; spacing: 8
                    visible: (page.d.options || []).length > 0
                    OnlineStyle.HelpText { width: parent.width; text: page.root.v.settingsPage.optionLabel || ""; color: Theme.value }
                    Repeater {
                        model: page.d.options || []
                        OnlineStyle.HelpText {
                            required property var modelData
                            width: parent.width
                            text: (modelData.current ? "\u2713  " : "\u2022  ") + (modelData.label || "")
                            color: modelData.current ? Theme.text : Theme.muted
                        }
                    }
                }
                Repeater {
                    model: page.d.rows || []
                    Column {
                        required property var modelData; width: detailContent.width; spacing: 6
                        OnlineStyle.FieldLabel { width: parent.width; text: parent.modelData.k || "" }
                        OnlineStyle.Value { width: parent.width; text: parent.modelData.v || "" }
                    }
                }
            }
        }
    }
}
