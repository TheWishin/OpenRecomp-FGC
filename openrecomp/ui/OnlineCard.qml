import QtQuick

// Search, match and result states use the same hierarchy as the Online chapters.
Item {
    id: page
    required property var root
    readonly property var o: root.v.online || ({})
    readonly property var d: o.detail || ({})
    readonly property var vs: root.v.matchVersus || ({})
    readonly property bool versus: o.phase === "matched" && !!vs.left
    component FighterSide: Rectangle {
        id: fighter
        property var person: ({})
        property bool mirror: false
        color: Theme.raised; radius: 6; border.width: 1; border.color: Theme.border
        Rectangle {
            anchors.fill: parent; anchors.margins: 1; radius: 5
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.rgba(Theme.gameAccent.r, Theme.gameAccent.g, Theme.gameAccent.b, .12) }
                GradientStop { position: 1; color: "transparent" }
            }
        }
        FighterPortrait {
            id: portrait
            objectName: "versusPortrait"
            x: 16; y: 16; width: parent.width - 32; height: Math.max(80, parent.height - identity.height - 40)
            source: fighter.person.render || fighter.person.art || ""; mirrored: !fighter.person.render && fighter.mirror
            showcase: true
            color: "transparent"
        }
        Column {
            id: identity; x: 16; anchors.bottom: parent.bottom; anchors.bottomMargin: 16; width: parent.width - 32; spacing: 4
            OnlineStyle.SectionHeader { objectName: "versusPlayerName"; width: parent.width; text: parent.parent.person.name || ""; font.pixelSize: Theme.onlinePx(40); maximumLineCount: 2; elide: Text.ElideRight; Accessible.name: text }
            Image { visible: !!parent.parent.person.plate; source: parent.parent.person.plate || ""; width: parent.width; height: visible ? 32 : 0; fillMode: Image.PreserveAspectFit }
            OnlineStyle.Value { objectName: "versusPlayerRank"; width: parent.width; text: [parent.parent.person.rank || "", parent.parent.person.rating || "", parent.parent.person.region || ""].filter(s => s).join(" · "); font.pixelSize: Theme.onlinePx(30) }
            OnlineStyle.HelpText { width: parent.width; text: parent.parent.person.fighter || "" }
            OnlineStyle.HelpText { objectName: "versusMain"; width: parent.width; visible: !!parent.parent.person.picked && !!parent.parent.person.main; text: visible ? (parent.parent.person.mainLabel || "") + ": " + parent.parent.person.main : "" }
        }
    }
    OnlineStyle.SectionCard {
        objectName: "matchVersusCard"
        visible: page.versus
        x: 24; y: 16; width: parent.width - 48; height: parent.height - 32
        Column {
            id: versusHeading; x: 24; y: 16; width: parent.width - 48; spacing: 4
            OnlineStyle.PageTitle { width: parent.width; text: (page.vs.game || "") + " · " + (page.o.title || "") }
            OnlineStyle.HelpText { width: parent.width; text: (page.vs.details || []).map(r => r.k + ": " + r.v).join(" · "); visible: !!text }
        }
        Row {
            id: fighters; x: 24; y: versusHeading.y + versusHeading.height + 12; width: parent.width - 48
            height: Math.max(140, versusFooter.y - y - 16); spacing: 16
            FighterSide { width: (parent.width - versusCentre.width - 32) / 2; height: parent.height; person: page.vs.left || ({}) }
            Column {
                id: versusCentre; width: Math.max(180, parent.width * .18); anchors.verticalCenter: parent.verticalCenter; spacing: 12
                OnlineStyle.PageTitle { width: parent.width; text: page.vs.versus || ""; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.onlinePx(64) }
                Rectangle {
                    width: Math.min(112, parent.width); height: width; radius: width / 2; anchors.horizontalCenter: parent.horizontalCenter
                    color: "transparent"; border.width: 4; border.color: Theme.readableAccent(page.root.v.accent)
                    OnlineStyle.Value { anchors.centerIn: parent; width: parent.width - 12; text: page.vs.seconds === null || page.vs.seconds === undefined ? "—" : page.vs.countdown || ""; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.onlinePx(26) }
                }
                OnlineStyle.HelpText { width: parent.width; text: page.vs.seconds === null || page.vs.seconds === undefined ? page.vs.countdown || "" : ""; visible: !!text; horizontalAlignment: Text.AlignHCenter }
                OnlineStyle.HelpText { width: parent.width; text: page.vs.opponentStatus || ""; visible: !!text; horizontalAlignment: Text.AlignHCenter }
            }
            FighterSide { width: (parent.width - versusCentre.width - 32) / 2; height: parent.height; person: page.vs.right || ({}); mirror: true }
        }
        Column {
            id: versusFooter; x: 24; y: parent.height - height - 20; width: parent.width - 48; spacing: 12
            PeerPing { anchors.horizontalCenter: parent.horizontalCenter; connection: page.vs.connection || ({}); ink: Theme.text; dim: Theme.border }
            Row {
                width: parent.width; spacing: 16
                OnlineStyle.PrimaryButton {
                    objectName: "versusReady"; width: (parent.width - 16) * .7; maxW: width; height: Math.max(Theme.target(80), captionHeight + 20) + feedbackHeight
                    b: Object.assign({}, page.o.primary || {}, {label: page.vs.readyLabel || "", disabled: !!page.vs.disabled || !!(page.o.primary || {}).disabled})
                    glyph: page.root.v.confirmInk || ({})
                    accent: Theme.readableAccent(page.root.v.accent); onActivated: i => page.root.backend.clickRow(i)
                }
                OnlineStyle.SecondaryButton {
                    objectName: "versusDecline"; width: (parent.width - 16) * .3; maxW: width; height: Math.max(Theme.target(80), captionHeight + 20) + feedbackHeight
                    b: (page.o.lines || []).filter(r => r.id === "cancel_match")[0] || ({})
                    glyph: page.root.v.backG || ({})
                    onActivated: i => page.root.backend.clickRow(i)
                }
            }
        }
    }
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
        visible: !page.versus
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
        visible: !page.versus
        x: card.x + card.width + 20; y: card.y; width: page.width - 24 - x; height: card.height
        Flickable {
            anchors.fill: parent; anchors.margins: 28; clip: true; contentHeight: detail.height
            Column {
                id: detail; width: parent.width; spacing: 12
                Row {
                    objectName: "sessionFighterPortraits"
                    visible: !!page.vs.left && !page.versus
                    width: parent.width; height: visible ? 160 : 0; spacing: 8
                    FighterPortrait { objectName: "resultOwnPortrait"; width: (parent.width - 8) / 2; height: parent.height; source: (page.vs.left || {}).art || ""; name: (page.vs.left || {}).fighter || (page.vs.left || {}).name || "" }
                    FighterPortrait { objectName: "resultPeerPortrait"; width: (parent.width - 8) / 2; height: parent.height; source: (page.vs.right || {}).art || ""; name: (page.vs.right || {}).fighter || (page.vs.right || {}).name || ""; mirrored: true }
                }
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
