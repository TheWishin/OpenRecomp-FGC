import QtQuick

Flickable {
    id: page
    required property var root
    readonly property var board: root.v.online.leaderboard || ({})
    readonly property var labels: board.labels || ({})
    contentWidth: width; contentHeight: content.height; clip: true; boundsBehavior: Flickable.StopAtBounds
    function revealFocus() {
        var target = null
        for (var n = 0; n < rankingRows.count; ++n) {
            var row = rankingRows.itemAt(n)
            if (row && row.modelData.focused) target = row
        }
        for (var repeater of [filterControls, sortControls, boardButtons]) {
            for (var i = 0; i < repeater.count; ++i) {
                var control = repeater.itemAt(i)
                if (control && control.b.focused) target = control
            }
        }
        if (!target) return
        var top = target.mapToItem(content, 0, 0).y
        if (top < contentY) contentY = top
        else if (top + target.height > contentY + height) contentY = top + target.height - height
    }
    onBoardChanged: Qt.callLater(revealFocus)
    component RankingRow: Rectangle {
        id: row
        property var entry: ({})
        width: parent.width; height: values.implicitHeight + 24; radius: 5
        color: entry.focused ? Theme.highlighted : entry.own ? "#252C33" : "#1B1E23"
        border.width: entry.focused ? 4 : entry.own ? 2 : 1
        border.color: entry.focused ? "#F2EFE6" : entry.own ? "#D3B59D" : "#3A3D42"
        Accessible.role: Accessible.Button
        Accessible.name: [entry.place, entry.name, entry.rank, entry.rating, entry.record, entry.main].join(", ")
        Accessible.onPressAction: if (entry.index >= 0) page.root.backend.clickRow(entry.index)
        Row {
            id: values; x: 14; y: 12; width: parent.width - 28; spacing: 0
            OnlineStyle.Value { width: values.width * 0.07; text: row.entry.place || "" }
            OnlineStyle.FieldLabel { width: values.width * 0.24; rightPadding: 12; text: row.entry.name || ""; font.weight: Font.DemiBold }
            Column {
                width: values.width * 0.19; spacing: 3
                Image { visible: !!row.entry.plate; source: row.entry.plate || ""; width: Math.min(parent.width - 12, 100); height: 40; fillMode: Image.PreserveAspectFit; asynchronous: true }
                OnlineStyle.FieldLabel { width: parent.width - 12; text: row.entry.rank || "—" }
            }
            OnlineStyle.Value { width: values.width * 0.13; text: row.entry.rating || "—" }
            OnlineStyle.FieldLabel { width: values.width * 0.15; rightPadding: 10; text: row.entry.record || "—" }
            OnlineStyle.FieldLabel { width: values.width * 0.22; text: row.entry.main || "—" }
        }
        HoverHandler { id: hover }
        Rectangle { anchors.fill: parent; radius: parent.radius; color: "#FFFFFF"; opacity: tap.pressed ? 0.14 : hover.hovered ? 0.07 : 0 }
        TapHandler { id: tap; enabled: row.entry.index >= 0; onTapped: page.root.backend.focusOnlineRow(row.entry.index); onDoubleTapped: page.root.backend.clickRow(row.entry.index) }
    }
    Column {
        id: content; width: page.width; spacing: 16
        OnlineStyle.PageTitle { width: parent.width; text: page.root.v.online.body.title || page.labels.ranking || "" }
        OnlineStyle.HelpText { width: parent.width; text: page.board.updated || "" }
        Column {
            width: parent.width; spacing: 8; visible: !!page.board.own
            OnlineStyle.SectionHeader { width: parent.width; text: page.labels.your_position || "" }
            RankingRow { width: parent.width; entry: page.board.own || ({}) }
        }
        Row {
            width: parent.width; spacing: 12; visible: (page.board.podium || []).length > 0
            Repeater {
                model: page.board.podium || []
                OnlineStyle.SectionCard {
                    required property var modelData
                    width: (content.width - 24) / 3; height: podiumContent.height + 32
                    border.color: "#D3B59D"
                    Column {
                        id: podiumContent; x: 16; y: 16; width: parent.width - 32; spacing: 5
                        OnlineStyle.PageTitle { width: parent.width; text: "#" + parent.parent.modelData.place; font.pixelSize: Theme.px(32) }
                        OnlineStyle.FieldLabel { width: parent.width; text: parent.parent.modelData.name; font.weight: Font.Bold }
                        OnlineStyle.HelpText { width: parent.width; text: parent.parent.modelData.rank || "—" }
                        OnlineStyle.Value { width: parent.width; text: parent.parent.modelData.rating }
                    }
                    TapHandler { onTapped: if (parent.modelData.index >= 0) page.root.backend.focusOnlineRow(parent.modelData.index); onDoubleTapped: if (parent.modelData.index >= 0) page.root.backend.clickRow(parent.modelData.index) }
                }
            }
        }
        OnlineStyle.SectionCard {
            width: parent.width; height: filters.height + 32
            Column {
                id: filters; x: 16; y: 16; width: parent.width - 32; spacing: 10
                Flow {
                    width: parent.width; spacing: 8
                    Repeater { id: filterControls; model: page.board.controls || []; OnlineStyle.Chip { required property var modelData; b: modelData; strong: true; maxW: filters.width; onActivated: i => page.root.backend.clickRow(i) } }
                    Repeater { id: boardButtons; model: page.board.buttons || []; OnlineStyle.SecondaryButton { required property var modelData; b: modelData; maxW: filters.width; onActivated: i => page.root.backend.clickRow(i) } }
                }
                OnlineStyle.HelpText { width: parent.width; text: page.labels.page_filter || "" }
                Flow {
                    width: parent.width; spacing: 6
                    Repeater { id: sortControls; model: page.board.sorts || []; OnlineStyle.Chip { required property var modelData; b: modelData; maxW: filters.width; onActivated: i => page.root.backend.clickRow(i) } }
                }
            }
        }
        OnlineStyle.SectionHeader { width: parent.width; text: page.labels.ranking || "" }
        Row {
            width: parent.width - 28; x: 14
            OnlineStyle.HelpText { width: parent.width * 0.07; text: page.labels.rank || "" }
            OnlineStyle.HelpText { width: parent.width * 0.24; text: page.labels.player || "" }
            OnlineStyle.HelpText { width: parent.width * 0.19; text: page.labels.standing || "" }
            OnlineStyle.HelpText { width: parent.width * 0.13; text: page.labels.rating || "" }
            OnlineStyle.HelpText { width: parent.width * 0.15; text: page.labels.record || "" }
            OnlineStyle.HelpText { width: parent.width * 0.22; text: page.labels.main || "" }
        }
        OnlineStyle.HelpText { visible: !(page.board.rows || []).length; width: parent.width; text: page.labels.empty || "" }
        Repeater { id: rankingRows; model: page.board.rows || []; RankingRow { required property var modelData; width: content.width; entry: modelData } }
    }
}
