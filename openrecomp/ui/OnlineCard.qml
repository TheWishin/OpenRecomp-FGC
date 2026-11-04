import QtQuick

// Search, match and result states use the same hierarchy as the Online chapters.
Item {
    id: page
    required property var root
    readonly property var o: root.v.online || ({})
    readonly property var d: o.detail || ({})
    readonly property var vs: root.v.matchVersus || ({})
    readonly property bool versus: ["matched", "starting"].indexOf(o.phase) >= 0 && !!vs.left
    readonly property bool accepted: o.phase === "starting"
    readonly property bool starting: !!vs.starting
    readonly property bool resultPhase: o.phase === "result" || o.phase === "result_sent"
    readonly property var decline: (o.lines || []).filter(r => r.id === "cancel_match")[0] || ({})
    QtObject {
        id: backdropRoot
        readonly property var v: Object.assign({}, page.root.v, {online: page.o.backdrop || ({})})
        readonly property var backend: page.root.backend
        readonly property string sans: page.root.sans
        readonly property string display: page.root.display
        readonly property string mono: page.root.mono
        readonly property bool reducedMotion: page.root.reducedMotion
        readonly property color bone: page.root.bone
        readonly property color line: page.root.line
        readonly property color muted: page.root.muted
        readonly property color textC: page.root.textC
        function ok(a, i) { return page.root.ok(a, i) }
    }
    PageLoader {
        pageName: "matchLobbyBackdrop"
        anchors.fill: parent; active: page.versus && !!page.o.backdrop
        page: "OnlineHub.qml"; root: backdropRoot; enabled: false
    }
    Rectangle {
        objectName: "matchLobbyDimmer"
        visible: page.versus
        anchors.fill: parent; color: "#B5000000"
        TapHandler {}
    }
    component FighterSide: Rectangle {
        id: fighter
        property var person: ({})
        property bool mirror: false
        objectName: "versusFighterHalf"
        color: Theme.raised; clip: true
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(Theme.gameAccent.r, Theme.gameAccent.g, Theme.gameAccent.b, .24) }
            GradientStop { position: 1; color: Theme.raised }
        }
        FighterPortrait {
            id: portrait
            objectName: "versusPortrait"
            anchors.fill: parent
            source: fighter.person.render || fighter.person.art || ""; mirrored: !fighter.person.render && fighter.mirror
            showcase: true
            color: "transparent"
        }
        Rectangle {
            objectName: "versusIdentityGradient"
            anchors.bottom: parent.bottom; width: parent.width; height: Math.min(parent.height, identity.height + 100)
            gradient: Gradient {
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: .45; color: "#D908090C" }
                GradientStop { position: 1; color: "#FA08090C" }
            }
        }
        Column {
            id: identity; x: 18; anchors.bottom: parent.bottom; anchors.bottomMargin: 16; width: parent.width - 36; spacing: 3
            OnlineStyle.SectionHeader { objectName: "versusPlayerName"; width: parent.width; text: fighter.person.name || ""; font.family: page.root.display; font.weight: Font.Black; font.pixelSize: Theme.onlinePx(40); maximumLineCount: 1; elide: Text.ElideRight; Accessible.name: text }
            Image { objectName: "versusRankPlate"; visible: !!fighter.person.plate; source: fighter.person.plate || ""; width: Math.min(parent.width, 180); height: visible ? 30 : 0; fillMode: Image.PreserveAspectFit; horizontalAlignment: Image.AlignLeft }
            OnlineStyle.Value { objectName: "versusPlayerRank"; width: parent.width; text: [fighter.person.rank || "", fighter.person.rating || ""].filter(s => s).join(" \u00b7 "); font.pixelSize: Theme.onlinePx(30); maximumLineCount: 1; elide: Text.ElideRight }
            OnlineStyle.HelpText { width: parent.width; text: [fighter.person.fighter || "", fighter.person.region || ""].filter(s => s).join(" \u00b7 "); maximumLineCount: 1; elide: Text.ElideRight }
            OnlineStyle.HelpText { objectName: "versusMain"; width: parent.width; visible: !!fighter.person.picked && !!fighter.person.main; text: visible ? (fighter.person.mainLabel || "") + ": " + fighter.person.main : ""; maximumLineCount: 1; elide: Text.ElideRight }
        }
    }
    Item {
        id: matchPresentation
        objectName: "matchPresentation"
        visible: page.versus
        width: parent.width * .64; height: matchCard.height + versusFooter.height + 10
        anchors.centerIn: parent
        property real entryOffset: 0
        transform: Translate { y: matchPresentation.entryOffset }
        function reveal() {
            if (visible && !page.root.reducedMotion) { matchEntry.restart(); versusFlash.restart() }
        }
        onVisibleChanged: reveal()
        Component.onCompleted: reveal()
        ParallelAnimation {
            id: matchEntry
            NumberAnimation { target: matchPresentation; property: "entryOffset"; from: 24; to: 0; duration: 160; easing.type: Easing.OutCubic }
            NumberAnimation { target: matchPresentation; property: "opacity"; from: .55; to: 1; duration: 160; easing.type: Easing.OutCubic }
        }
        Connections {
            target: page.root
            function onReducedMotionChanged() {
                if (page.root.reducedMotion) {
                    matchEntry.stop(); versusFlash.stop()
                    matchPresentation.entryOffset = 0; matchPresentation.opacity = 1; flash.opacity = 0
                }
            }
        }
        OnlineStyle.SectionCard {
            id: matchCard
            objectName: "matchVersusCard"
            width: parent.width; height: page.height * .55
            clip: true; radius: 4
            Row {
                objectName: "versusFighters"
                anchors.fill: parent; anchors.margins: 1; spacing: 2
                FighterSide { width: (parent.width - 2) / 2; height: parent.height; person: page.vs.left || ({}) }
                FighterSide { width: (parent.width - 2) / 2; height: parent.height; person: page.vs.right || ({}); mirror: true }
            }
            Rectangle {
                width: parent.width; height: versusHeading.height + 32
                gradient: Gradient {
                    GradientStop { position: 0; color: "#ED08090C" }
                    GradientStop { position: 1; color: "transparent" }
                }
            }
            OnlineStyle.PageTitle {
                id: versusHeading; objectName: "versusTitle"
                x: 18; y: 10; width: parent.width - 36
                text: (page.vs.game || "") + " \u00b7 " + (page.o.title || "")
                font.pixelSize: Theme.onlinePx(28); horizontalAlignment: Text.AlignHCenter
                maximumLineCount: 1; elide: Text.ElideRight
            }
            Rectangle {
                id: versusCentre; objectName: "versusCountdownRing"
                width: 122; height: width; radius: width / 2
                anchors.centerIn: parent; anchors.verticalCenterOffset: -70
                color: "#EE0B0C10"; border.width: 4; border.color: Theme.border
                CountdownRing { anchors.fill: parent; seconds: page.vs.seconds; paused: page.accepted; reducedMotion: page.root.reducedMotion }
                Rectangle {
                    id: flash; objectName: "versusFlash"
                    anchors.fill: parent; radius: parent.radius; color: Theme.selected; opacity: 0
                    NumberAnimation { id: versusFlash; target: flash; property: "opacity"; from: .22; to: 0; duration: 160; easing.type: Easing.OutCubic }
                }
                Column {
                    anchors.centerIn: parent; width: parent.width - 16; spacing: 0
                    OnlineStyle.PageTitle { width: parent.width; text: page.vs.versus || ""; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.onlinePx(46) }
                    OnlineStyle.Value { objectName: "versusCountdown"; width: parent.width; text: page.accepted ? "\u2026" : page.vs.seconds === null || page.vs.seconds === undefined ? "\u2014" : page.vs.countdown || ""; horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.onlinePx(24) }
                }
            }
            Rectangle {
                objectName: "versusStatusPlate"
                visible: !!versusStatus.text
                x: (parent.width - width) / 2; y: versusCentre.y + versusCentre.height + 10
                width: Math.min(parent.width - 32, Math.max(160, versusStatus.implicitWidth + 24)); height: versusStatus.implicitHeight + 12; radius: 4
                color: "#ED0B0C10"
                OnlineStyle.HelpText { id: versusStatus; objectName: "versusStatus"; anchors.centerIn: parent; width: parent.width - 24; text: page.vs.status || (page.starting ? page.vs.startingLabel || page.o.title || "" : page.vs.opponentStatus || (page.vs.seconds === null || page.vs.seconds === undefined ? page.vs.countdown || "" : "")); horizontalAlignment: Text.AlignHCenter; maximumLineCount: 2; elide: Text.ElideRight }
            }
        }
        Column {
            id: versusFooter; objectName: "versusFooter"
            y: matchCard.height + 10; width: parent.width; spacing: 10
            OnlineStyle.HelpText {
                objectName: "versusInfoLine"
                width: parent.width
                text: page.vs.infoLine || (page.vs.details || []).map(r => r.k + ": " + r.v).concat([(page.vs.connection || {}).text || "", (page.vs.connection || {}).path || ""]).filter(s => s).join(" \u00b7 ")
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.NoWrap; elide: Text.ElideRight
            }
            Row {
                width: parent.width; spacing: 12
                OnlineStyle.PrimaryButton {
                    objectName: "versusReady"; width: (parent.width - 12) * .7; maxW: width; height: Math.max(Theme.target(72), captionHeight + 20) + feedbackHeight
                    fontSize: 22
                    b: Object.assign({}, page.o.primary || {}, {label: page.starting ? (page.vs.startingLabel || page.o.title || "") : page.vs.readyLabel || "", disabled: page.accepted || !!page.vs.disabled || !!(page.o.primary || {}).disabled})
                    glyph: page.root.v.confirmInk || ({})
                    accent: Theme.gameAccent; onActivated: i => page.root.backend.clickRow(i)
                }
                OnlineStyle.SecondaryButton {
                    objectName: "versusDecline"; width: (parent.width - 12) * .3; maxW: width; height: Math.max(Theme.target(56), captionHeight + 20) + feedbackHeight
                    anchors.verticalCenter: parent.verticalCenter
                    b: Object.assign({}, page.decline, {label: page.decline.label || page.vs.declineLabel || "", disabled: page.accepted || !!page.vs.disabled || !!page.decline.disabled})
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
            Rectangle {
                id: resultBanner; objectName: "resultBanner"
                visible: page.resultPhase
                width: parent.width; height: visible ? resultLabel.height + 24 : 0
                radius: 4; color: Theme.raised
                property real entryOffset: 0
                transform: Translate { x: resultBanner.entryOffset }
                Rectangle { width: 5; height: parent.height; color: Theme.rankGold }
                OnlineStyle.PageTitle { id: resultLabel; x: 18; y: 12; width: parent.width - 36; text: page.o.title || ""; color: Theme.rankGold }
                onVisibleChanged: if (visible && !page.root.reducedMotion) resultEntry.restart()
                Component.onCompleted: if (visible && !page.root.reducedMotion) resultEntry.restart()
                ParallelAnimation {
                    id: resultEntry
                    NumberAnimation { target: resultBanner; property: "entryOffset"; from: -20; to: 0; duration: 160; easing.type: Easing.OutCubic }
                    NumberAnimation { target: resultBanner; property: "opacity"; from: .6; to: 1; duration: 160; easing.type: Easing.OutCubic }
                }
                Connections {
                    target: page.root
                    function onReducedMotionChanged() {
                        if (page.root.reducedMotion) { resultEntry.stop(); resultBanner.entryOffset = 0; resultBanner.opacity = 1 }
                    }
                }
            }
            OnlineStyle.PageTitle { objectName: "onlineCardTitle"; visible: !page.resultPhase; width: parent.width; text: page.o.title || "" }
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
