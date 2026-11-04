import QtQuick

// Search, match and result states use the same hierarchy as the Online chapters.
Item {
    id: page
    required property var root
    readonly property var o: root.v.online || ({})
    readonly property var d: o.detail || ({})
    function sections() {
        var out = []
        for (var line of o.lines || []) {
            if (o.primary && line.index === o.primary.index) continue
            if (line.kind === "heading") out.push({title: line.label, lines: []})
            else {
                if (!out.length) out.push({title: "", lines: []})
                var row = Object.assign({}, line, {kind: "row", hint: line.focused && line.hint !== o.message ? line.hint || "" : ""})
                out[out.length - 1].lines.push(row)
            }
        }
        return out.filter(section => section.lines.length)
    }
    OnlineStyle.SectionCard {
        id: card
        objectName: "onlineCard"
        x: 24; y: 18; width: (parent.width - 68) * 0.62; height: parent.height - y - 16
        border.color: page.o.statusFocused ? Theme.readableAccent(page.root.v.accent) : page.root.line
        Column {
            id: header
            x: 28; y: 20; width: parent.width - 56; spacing: 8
            OnlineStyle.PageTitle { objectName: "onlineCardTitle"; width: parent.width; text: page.o.title || "" }
            OnlineStyle.HelpText { visible: !!text && text !== page.o.title; width: parent.width; text: page.o.message || ""; color: page.o.error ? Theme.error : page.root.muted }
            PeerPing { visible: !!page.o.connection; connection: page.o.connection || ({}); ink: page.root.textC; dim: page.root.muted }
        }
        OnlineSections {
            objectName: "onlineCardRows"
            root: page.root; x: 12; y: header.y + header.height + 16
            width: parent.width - 24; height: (primary.visible ? primary.y - 16 : parent.height - 12) - y
            sections: page.sections()
        }
        OnlineStyle.PrimaryButton {
            id: primary
            objectName: "onlinePhasePrimary"
            visible: !!page.o.primary
            x: 28; y: parent.height - height - 24; width: parent.width - 56; maxW: width
            b: page.o.primary || ({})
            accent: Theme.readableAccent(page.root.v.accent)
            onActivated: i => page.root.backend.clickRow(i)
        }
    }
    OnlineStyle.SectionCard {
        objectName: "onlineCardDetail"
        x: card.x + card.width + 20; y: card.y; width: page.width - 24 - x; height: card.height
        Flickable {
            anchors.fill: parent; anchors.margins: 28; clip: true; contentHeight: detail.height
            Column {
                id: detail; width: parent.width; spacing: 12
                OnlineStyle.SectionHeader { visible: !!text && text !== page.o.title; width: parent.width; text: page.d.title || "" }
                OnlineStyle.HelpText { width: parent.width; text: page.d.lead || ""; visible: !!text && text !== page.o.message && text !== page.o.title }
                Repeater {
                    model: page.d.rows || []
                    Column {
                        required property var modelData; width: detail.width; spacing: 4
                        OnlineStyle.FieldLabel { width: parent.width; text: parent.modelData.k || "" }
                        OnlineStyle.Value { width: parent.width; text: parent.modelData.v || "" }
                    }
                }
            }
        }
    }
}
