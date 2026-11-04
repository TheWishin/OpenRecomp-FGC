import QtQuick

// The non-online sections use the same compact cards and focused action as Online.
Item {
    id: page
    required property var root
    readonly property var p: root.v.sessionPage || ({})
    readonly property var d: root.v.detail || ({})
    readonly property color card: Theme.card
    readonly property color ink: Theme.ground
    readonly property bool replays: p.section === "replays"
    readonly property bool support: p.section === "support"
    readonly property bool play: p.section === "play"
    readonly property var lines: p.rows || []
    readonly property int listWidth: support ? 1100 : (replays ? 1340 : 1120)
    function list(a) { return a || [] }
    function cell(r, i) { return (r.cells || [])[i] || "\u2014" }

    Rectangle {
        objectName: "sessionCard"
        x: 24; y: 24; width: page.support ? 1872 : page.listWidth; height: parent.height - 48
        color: page.card; border.width: 1; border.color: page.root.line
        Rectangle { width: 5; height: 92; color: Theme.readableAccent(page.root.v.accent) }
        Column {
            x: 28; y: 24; width: page.listWidth - 56; spacing: 6
            Text { objectName: "sessionTitle"; width: parent.width; height: 48; textFormat: Text.PlainText; text: page.p.title || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(40); fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(26); elide: Text.ElideRight }
            Text { width: parent.width; height: 50; textFormat: Text.PlainText; text: page.p.lead || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: Theme.px(21); wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
        }
        Flow {
            id: replayControls
            x: 28; y: 140; width: page.listWidth - 56; spacing: 8
            visible: page.replays && (page.p.controls || []).length > 0
            Repeater {
                model: page.p.controls || []
                OnlineStyle.SecondaryButton {
                    required property var modelData; b: modelData; maxW: replayControls.width / 2 - 8
                    onActivated: i => page.root.backend.clickRow(i)
                }
            }
        }
        // A replay is one dense table row; headings stay outside the controller target.
        Row {
            id: replayHeader
            objectName: "replayTableHeader"
            visible: page.replays && !page.p.empty
            x: 44; y: replayControls.visible ? replayControls.y + replayControls.height + 12 : 142; width: page.listWidth - 88; spacing: 16
            Repeater {
                model: page.list(page.p.replayColumns).length
                Text {
                    required property int index
                    width: (parent.width - 64) * [0.18, 0.19, 0.32, 0.19, 0.12][index]
                    height: implicitHeight; wrapMode: Text.Wrap; textFormat: Text.PlainText; text: (page.p.replayColumns || [])[index] || ""
                    color: page.root.muted; font.family: page.root.mono; font.weight: Font.DemiBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(17)
                }
            }
        }
        Flickable {
            id: rowViewport
            objectName: "sessionViewport"
            x: 28; y: page.replays && !page.p.empty ? replayHeader.y + replayHeader.height + 12 : 140
            width: page.listWidth - 56; height: parent.height - y - 24
            contentHeight: rows.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            function reveal() {
                for (var child of rows.children) {
                    if (child.r && child.r.focused) {
                        if (child.y < contentY) contentY = child.y
                        else if (child.y + child.height > contentY + height) contentY = child.y + child.height - height
                        return
                    }
                }
            }
            Connections { target: page.root.backend; function onViewChanged() { Qt.callLater(rowViewport.reveal) } }
            onHeightChanged: Qt.callLater(reveal)
        Column {
            id: rows
            objectName: "sessionRows"
            x: 0; y: 0; width: rowViewport.width
            spacing: page.play ? 10 : 4
            Repeater {
                model: page.lines.length
                Rectangle {
                    id: row
                    required property int index
                    readonly property var r: page.root.ok(page.lines, index)
                    objectName: "sessionRow"
                    width: rows.width
                    height: r.heading ? headingLabel.implicitHeight + 12 : Math.max(Theme.listRowHeight, Theme.target(page.play && r.primary ? 98 : page.play ? 72 : 54), Theme.px(23) * 2 + 20, rowLabel.implicitHeight + 24, rowValue.implicitHeight + 24)
                    color: r.heading ? "transparent" : (r.focused ? page.root.bone : (r.primary ? Theme.readableAccent(page.root.v.accent) : "#1C1E23"))
                    border.width: r.heading ? 0 : 1; border.color: r.focused ? Theme.readableAccent(page.root.v.accent) : (r.primary ? page.root.line : "transparent")
                    opacity: r.disabled ? 0.5 : 1
                    EditableField { id: nativeField; visible: !!row.r.fieldId; x: 8; y: 8; width: parent.width - 16; root: page.root; field: row.r }
                    Rectangle { visible: !row.r.heading && !!row.r.focused; width: 5; height: parent.height; color: Theme.readableAccent(page.root.v.accent) }
                    Text {
                        id: headingLabel; objectName: "sessionHeadingLabel"
                        visible: !!row.r.heading
                        x: 4; width: parent.width - 8; height: implicitHeight; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                        textFormat: Text.PlainText; text: row.r.label || ""; color: page.root.muted; font.family: page.root.mono; font.weight: Font.DemiBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(17)
                    }
                    Row {
                        visible: page.replays && !page.p.empty && !row.r.heading
                        x: 16; width: parent.width - 32; anchors.verticalCenter: parent.verticalCenter; spacing: 16
                        Repeater {
                            model: 5
                            Text {
                                required property int index
                                objectName: "replayTableCell"
                                width: (parent.width - 64) * [0.18, 0.19, 0.32, 0.19, 0.12][index]
                                height: implicitHeight; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.cell(row.r, index)
                                color: row.r.focused ? page.ink : (index === 3 ? Theme.readableAccent(page.root.v.accent) : page.root.textC); font.family: index === 0 || index === 4 ? page.root.mono : page.root.sans; font.pixelSize: Theme.px(20)
                            }
                        }
                    }
                    Text {
                        id: rowLabel
                        objectName: "sessionRowLabel"
                        visible: !row.r.fieldId && !row.r.heading && (!page.replays || !!page.p.empty)
                        x: 18; width: rowValue.x - x - 16; height: implicitHeight; anchors.verticalCenter: parent.verticalCenter
                        verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap
                        textFormat: Text.PlainText; text: row.r.label || ""; color: row.r.focused || row.r.primary ? page.ink : page.root.textC
                        font.family: row.r.primary ? page.root.display : page.root.sans; font.weight: row.r.primary ? Font.Black : Font.Medium; font.capitalization: row.r.primary ? Font.AllUppercase : Font.MixedCase; font.pixelSize: Theme.px(row.r.primary ? 38 : 23)
                    }
                    Text {
                        id: rowValue
                        visible: !row.r.fieldId && !row.r.heading && !page.replays
                        anchors.right: rowVerb.left; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter
                        width: row.r.value ? parent.width * 0.34 : 0; height: implicitHeight; verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignRight; wrapMode: Text.Wrap
                        textFormat: Text.PlainText; text: row.r.value || ""; color: row.r.focused ? page.ink : Theme.readableAccent(page.root.v.accent); font.family: page.root.mono; font.pixelSize: Theme.px(21)
                    }
                    Text {
                        id: rowVerb
                        visible: !row.r.fieldId && !row.r.heading && !page.replays
                        anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter
                        width: row.r.focused && row.r.verb ? 140 : 0; elide: Text.ElideRight; horizontalAlignment: Text.AlignRight
                        textFormat: Text.PlainText; text: row.r.focused ? (row.r.verb || "") : ""; color: row.r.focused ? page.ink : page.root.muted; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(20)
                    }
                    TapHandler { id: uiTap0; enabled: !row.r.fieldId && !row.r.heading; onTapped: page.root.backend.clickRow(row.r.index) }
                    Interaction { visible: !row.r.fieldId; handler: uiTap0; selected: !!row.r.focused; onActivated: page.root.backend.clickRow(row.r.index) }
                }
            }
        }
        }
        Text { visible: !!page.p.up; x: page.listWidth - 25; y: 120; textFormat: Text.PlainText; text: "\u25B2"; color: page.root.muted; font.pixelSize: Theme.px(15)}
        Text { visible: !!page.p.down; x: page.listWidth - 25; anchors.bottom: parent.bottom; anchors.bottomMargin: 7; textFormat: Text.PlainText; text: "\u25BC"; color: page.root.muted; font.pixelSize: Theme.px(15)}
    }
    Rectangle {
        id: detail
        objectName: "sessionDetail"
        x: page.listWidth + 44; y: page.support ? 164 : 24; width: 1920 - x - 24; height: parent.height - y - 24
        color: page.support ? "transparent" : page.card; border.width: page.support ? 0 : 1; border.color: page.root.line
        Flickable {
            id: detailArea
            objectName: "detailContent"
            x: 28; y: 28; width: parent.width - 56
            height: Math.max(0, primary.visible ? primary.y - y - 16 : parent.height - y - 28)
            contentWidth: width; contentHeight: detailColumn.implicitHeight
            clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: detailColumn
                width: parent.width; spacing: 14
                Text { width: parent.width; textFormat: Text.PlainText; text: page.d.kicker || page.p.title || ""; elide: Text.ElideRight; color: Theme.readableAccent(page.root.v.accent); font.family: page.root.mono; font.weight: Font.DemiBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(18)}
                Text { objectName: "sessionDetailTitle"; width: parent.width; textFormat: Text.PlainText; text: page.d.title || ""; wrapMode: Text.Wrap; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(40)}
                Text { width: parent.width; textFormat: Text.PlainText; text: page.support && page.p.notice ? page.p.notice : (page.d.lead || ""); wrapMode: Text.Wrap; color: page.root.muted; font.family: page.root.sans; font.pixelSize: Theme.px(22); lineHeight: 1.1 }
                Text { objectName: "sessionError"; visible: !!page.p.error; width: parent.width; textFormat: Text.PlainText; text: page.p.error || ""; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight; color: Theme.error; font.family: page.root.sans; font.pixelSize: Theme.px(21)}
                Text { visible: !!page.p.busy; width: parent.width; textFormat: Text.PlainText; text: page.root.v.hint || ""; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; color: Theme.readableAccent(page.root.v.accent); font.family: page.root.sans; font.pixelSize: Theme.px(21)}
                Rectangle {
                    objectName: "sessionBusy"
                    visible: !!page.p.busy
                    width: parent.width; height: 4; color: page.root.line
                    Rectangle { width: parent.width * 0.35; height: parent.height; color: Theme.readableAccent(page.root.v.accent) }
                }
                Repeater {
                    model: page.list(page.d.rows).length
                    Rectangle {
                        required property int index
                        readonly property var r: page.root.ok(page.d.rows, index)
                        width: parent.width; height: 62; color: "transparent"
                        Rectangle { width: parent.width; height: 1; color: page.root.line }
                        Text { x: 0; y: 9; width: parent.width; textFormat: Text.PlainText; text: parent.r.k || ""; elide: Text.ElideRight; color: page.root.muted; font.family: page.root.sans; font.pixelSize: Theme.px(18)}
                        Text { x: 0; y: 32; width: parent.width; textFormat: Text.PlainText; text: parent.r.v || ""; elide: Text.ElideMiddle; color: parent.r.accent ? Theme.readableAccent(page.root.v.accent) : page.root.textC; font.family: page.root.mono; font.pixelSize: Theme.px(21)}
                    }
                }
                Row {
                    visible: page.list(page.d.results).length > 0; spacing: 8
                    Repeater { model: page.list(page.d.results).length; ResultCell { required property int index; c: page.root.ok(page.d.results, index); accent: Theme.readableAccent(page.root.v.accent); root: page.root } }
                }
            }
        }
        Rectangle {
            id: primary
            objectName: "primaryAction"
            visible: !!page.d.primary && !page.play && !page.support
            x: 28; y: parent.height - 96; width: parent.width - 56; height: 68
            color: page.root.bone
            Rectangle { width: 5; height: parent.height; color: Theme.readableAccent(page.root.v.accent) }
            Text { x: 22; width: parent.width - 90; height: parent.height - 16; anchors.verticalCenter: parent.verticalCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(21); textFormat: Text.PlainText; text: page.d.primary || ""; color: page.ink; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(34)}
            Glyph { anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter; size: 36; g: page.d.primaryG || ({}) }
            TapHandler { id: uiTap1; onTapped: page.root.backend.clickPrimary() }
            Interaction { handler: uiTap1; selected: !!page.d.focused; onActivated: page.root.backend.clickPrimary() }
        }
    }
}
