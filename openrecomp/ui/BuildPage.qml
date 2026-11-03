import QtQuick

// The Build section as cards: what is done, what is next, one big button. Every action is a row of the hub (same
// focus order, clickRow); this page only arranges them (nav_build.py).
Item {
    id: page
    required property var root
    readonly property var v: root.v
    readonly property var b: v.build || ({})
    readonly property var m: b.main || ({})
    readonly property var btn: m.button || ({})

    function statusColor(s) {
        if (s === "done") return "#6CC287"
        if (s === "work") return "#E6B450"
        if (s === "error") return "#F0605D"
        if (s === "wait") return page.root.muted
        return page.v.accent
    }

    // ---------------------------------------------------------------- left: the steps
    Item {
        id: steps
        objectName: "buildSteps"
        x: 48; y: 24; width: 1024; height: parent.height - 48
        clip: true
        Column {
            id: stepColumn
            width: parent.width; spacing: 16
            transformOrigin: Item.TopLeft
            scale: Math.min(1, steps.height / Math.max(1, implicitHeight))
            Repeater {
                model: (page.b.cards || []).length
                Rectangle {
                    id: card
                    objectName: "buildCard"
                    required property int index
                    readonly property var c: page.root.ok(page.b.cards, index)
                    width: stepColumn.width; height: cardColumn.implicitHeight + 48
                    color: c.focused ? "#191B1F" : page.root.panel
                    border.width: c.focused ? 2 : 1
                    border.color: c.focused ? page.v.accent : page.root.line
                    Rectangle { width: 6; height: parent.height; color: page.statusColor(card.c.status) }
                    Column {
                        id: cardColumn
                        x: 40; y: 24; width: parent.width - 72; spacing: 10
                        Item {
                            width: parent.width; height: 48
                            Rectangle {
                                id: num
                                width: 44; height: 44; anchors.verticalCenter: parent.verticalCenter
                                color: card.c.status === "done" ? page.statusColor("done") : "transparent"
                                border.width: 2; border.color: page.statusColor(card.c.status)
                                Text { visible: card.c.status !== "done"; anchors.centerIn: parent; textFormat: Text.PlainText; text: String(card.c.num || ""); color: page.root.textC; font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: 24 }
                                // a drawn check mark: no font needed
                                Item {
                                    visible: card.c.status === "done"; anchors.fill: parent
                                    Rectangle { x: 9; y: 22; width: 12; height: 5; rotation: 45; color: "#0E0F11"; antialiasing: true }
                                    Rectangle { x: 15; y: 18; width: 22; height: 5; rotation: -50; color: "#0E0F11"; antialiasing: true }
                                }
                            }
                            Text {
                                objectName: "buildCardTitle"
                                anchors.left: num.right; anchors.leftMargin: 20; anchors.right: chip.left; anchors.rightMargin: 20; anchors.verticalCenter: parent.verticalCenter
                                height: 48; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; fontSizeMode: Text.Fit; minimumPixelSize: 26
                                textFormat: Text.PlainText; text: card.c.title || ""; color: page.root.textC
                                font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: 40
                            }
                            Rectangle {
                                id: chip
                                objectName: "buildChip"
                                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                width: chipText.implicitWidth + 24; height: 34; color: "transparent"
                                border.width: 2; border.color: page.statusColor(card.c.status)
                                Text { id: chipText; anchors.centerIn: parent; textFormat: Text.PlainText; text: card.c.chip || ""; color: page.statusColor(card.c.status); font.family: page.root.mono; font.weight: Font.DemiBold; font.capitalization: Font.AllUppercase; font.pixelSize: 18 }
                            }
                        }
                        Text {
                            objectName: "buildCardText"
                            width: parent.width; visible: !!card.c.text
                            textFormat: Text.PlainText; text: card.c.text || ""; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                            color: card.c.status === "error" ? page.statusColor("error") : page.root.textC
                            font.family: page.root.sans; font.pixelSize: 24; lineHeight: 1.1
                        }
                        Text {
                            width: parent.width; visible: !!card.c.note
                            textFormat: Text.PlainText; text: card.c.note || ""; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                            color: page.root.muted; font.family: page.root.sans; font.pixelSize: 22
                        }
                        Repeater {
                            model: (card.c.actions || []).length
                            BuildAction { required property int index; a: page.root.ok(card.c.actions, index); root: page.root; accent: page.v.accent; width: cardColumn.width }
                        }
                    }
                }
            }
            // ------------------------------------------------------------ more: options and the rarely used rows
            Rectangle {
                visible: (page.b.more || []).length > 0
                width: stepColumn.width; height: moreColumn.implicitHeight + 40
                color: "transparent"; border.width: 1; border.color: page.root.line
                Column {
                    id: moreColumn
                    x: 40; y: 20; width: parent.width - 72; spacing: 8
                    Text { textFormat: Text.PlainText; text: page.b.moreTitle || ""; color: page.root.muted; font.family: page.root.mono; font.capitalization: Font.AllUppercase; font.pixelSize: 20 }
                    Repeater {
                        model: (page.b.more || []).length
                        BuildAction { required property int index; a: page.root.ok(page.b.more, index); root: page.root; accent: page.v.accent; width: moreColumn.width; compact: true }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- right: the build itself, one big button
    Rectangle {
        id: mainCard
        objectName: "buildMain"
        x: 1112; y: 24; width: 760; height: parent.height - 48
        color: page.root.panel
        clip: true
        Text { textFormat: Text.PlainText; x: parent.width - implicitWidth + 40; y: -120; text: page.v.numeral || ""; color: "#17191C"; font.family: page.root.display; font.weight: Font.Black; font.pixelSize: 900 }
        Image {
            visible: !!page.v.hero
            source: page.v.hero || ""
            width: 520; height: 520; x: parent.width - 420; y: parent.height - 640
            opacity: 0.16; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectFit
        }
        Rectangle { width: parent.width; height: 6; color: page.statusColor(page.m.tone) }
        Item {
            id: mainArea
            x: 48; y: 40; width: parent.width - 96; height: parent.height - 40 - 112 - 64
            clip: true
            Column {
                id: mainColumn
                width: parent.width; spacing: 14
                transformOrigin: Item.TopLeft
                scale: Math.min(1, mainArea.height / Math.max(1, implicitHeight))
                Text { textFormat: Text.PlainText; width: parent.width; visible: !!page.m.kicker; text: page.m.kicker || ""; elide: Text.ElideRight; color: page.statusColor(page.m.tone); font.family: page.root.mono; font.weight: Font.Medium; font.capitalization: Font.AllUppercase; font.pixelSize: 24 }
                Text { objectName: "buildMainTitle"; width: parent.width; textFormat: Text.PlainText; text: page.m.title || ""; wrapMode: Text.Wrap; maximumLineCount: 2; lineHeight: 0.95; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 68 }
                Text { objectName: "buildMainLead"; width: parent.width; visible: !!page.m.lead && !page.m.logOpen; textFormat: Text.PlainText; text: page.m.lead || ""; wrapMode: Text.Wrap; maximumLineCount: page.m.logOpen ? 2 : 5; elide: Text.ElideRight; lineHeight: 1.1; color: page.root.textC; font.family: page.root.sans; font.pixelSize: 28 }
                // progress: the step's name, a bar, how long so far and about how long still
                Column {
                    objectName: "buildProgressBlock"
                    width: parent.width; spacing: 10; topPadding: 8
                    visible: page.m.progress >= 0 || !!page.m.stepLine
                    Text { objectName: "buildStepLine"; width: parent.width; visible: !!page.m.stepLine; textFormat: Text.PlainText; text: page.m.stepLine || ""; elide: Text.ElideRight; color: page.root.textC; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 30 }
                    Rectangle {
                        objectName: "buildProgress"
                        width: parent.width; height: 18; color: "#24272C"; clip: true
                        Rectangle { visible: page.m.progress >= 0; height: parent.height; width: parent.width * Math.max(0, Math.min(1, page.m.progress)); color: page.statusColor(page.m.tone === "done" ? "done" : "work") }
                        Rectangle {
                            id: sweep
                            visible: page.m.progress < 0
                            height: parent.height; width: parent.width * 0.28; color: page.statusColor("work")
                            NumberAnimation on x { running: sweep.visible && !page.root.reducedMotion; loops: Animation.Infinite; from: -sweep.width; to: sweep.parent.width; duration: 1600 }
                        }
                    }
                    Item {
                        width: parent.width; height: 30
                        Text { objectName: "buildElapsed"; anchors.left: parent.left; width: parent.width * 0.45; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.m.elapsed || ""; color: page.root.muted; font.family: page.root.mono; font.pixelSize: 22 }
                        Text { objectName: "buildEta"; anchors.right: parent.right; width: parent.width * 0.53; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.m.eta || ""; color: page.root.textC; font.family: page.root.mono; font.weight: Font.Medium; font.pixelSize: 22 }
                    }
                }
                Text { objectName: "buildQuiet"; width: parent.width; visible: !!page.m.quiet; textFormat: Text.PlainText; text: page.m.quiet || ""; wrapMode: Text.Wrap; maximumLineCount: 3; color: page.statusColor("work"); font.family: page.root.sans; font.pixelSize: 24 }
                Rectangle {
                    objectName: "buildError"
                    visible: !!page.m.error
                    width: parent.width; height: errorText.implicitHeight + 32
                    color: "#2A1617"; border.width: 2; border.color: page.statusColor("error")
                    Text { id: errorText; x: 20; y: 16; width: parent.width - 40; textFormat: Text.PlainText; text: page.m.error || ""; wrapMode: Text.Wrap; maximumLineCount: 6; elide: Text.ElideRight; color: page.root.textC; font.family: page.root.sans; font.pixelSize: 24 }
                }
                // the log: closed by default, X (or a click) opens it
                Item {
                    objectName: "buildLogToggle"
                    visible: !!page.m.canLog
                    width: parent.width; height: 44
                    Row {
                        spacing: 14; anchors.verticalCenter: parent.verticalCenter
                        Glyph { g: page.b.xG || ({}); size: 36; anchors.verticalCenter: parent.verticalCenter }
                        Text { textFormat: Text.PlainText; anchors.verticalCenter: parent.verticalCenter; text: page.m.logOpen ? "-" : "+"; color: page.root.muted; font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: 26 }
                        Text { textFormat: Text.PlainText; anchors.verticalCenter: parent.verticalCenter; text: page.b.logTitle || ""; color: page.root.muted; font.family: page.root.mono; font.capitalization: Font.AllUppercase; font.pixelSize: 22 }
                    }
                    TapHandler { onTapped: page.root.backend.press("x") }
                }
                Rectangle {
                    objectName: "buildLog"
                    visible: !!page.m.logOpen
                    width: parent.width; height: logColumn.implicitHeight + 24
                    color: page.root.bar
                    Column {
                        id: logColumn
                        x: 16; y: 12; width: parent.width - 32
                        Repeater {
                            model: (page.m.logLines || []).length
                            Text { required property int index; width: logColumn.width; textFormat: Text.PlainText; text: (page.m.logLines || [])[index] || ""; elide: Text.ElideMiddle; color: page.root.muted; font.family: page.root.mono; font.pixelSize: 18 }
                        }
                    }
                }
            }
        }
        // ------------------------------------------------------------ the one big button
        Rectangle {
            objectName: "buildButton"
            visible: page.btn.index !== undefined && page.btn.index >= 0
            x: 48; y: parent.height - 112 - 40
            width: parent.width - 96; height: 112
            readonly property bool off: !!page.btn.disabled || !!page.btn.blocked
            color: off ? "#24272C" : page.root.bone
            border.width: page.btn.focused ? 4 : 0
            border.color: page.v.accent
            Rectangle { visible: !parent.off; width: 8; height: parent.height; color: page.v.accent }
            Text { objectName: "buildButtonLabel"; x: 44; width: parent.width - 160; height: parent.height - 24; anchors.verticalCenter: parent.verticalCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; minimumPixelSize: 32; fontSizeMode: Text.Fit; textFormat: Text.PlainText; text: page.btn.label || ""; color: parent.off ? page.root.muted : "#0E0F11"; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 60 }
            Glyph { visible: !!page.btn.focused && !parent.off; anchors.right: parent.right; anchors.rightMargin: 36; anchors.verticalCenter: parent.verticalCenter; size: 56; g: page.btn.g || ({}) }
            TapHandler { onTapped: page.root.backend.clickRow(page.btn.index) }
        }
        // the frame last, over the big numeral
        Rectangle { anchors.fill: parent; color: "transparent"; border.width: page.btn.focused ? 2 : 1; border.color: page.btn.focused ? page.v.accent : page.root.line }
    }
}
