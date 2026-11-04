import QtQuick

// The Online login page (nav_online_login): one centred card. The game on top, the name field, Account and Play as
// guest side by side, the server as a small line at the bottom. "Forgot password?" swaps the card to the recovery rows.
Item {
    id: page
    required property var root
    readonly property var o: root.v.online || ({})
    readonly property var acc: root.v.accent
    readonly property color card: "#16181C"
    readonly property color ink: "#0E0F11"
    readonly property color red: "#FF5A5F"
    function list(a) { return a || [] }
    function click(b) { if (b && b.index !== undefined && b.index >= 0) root.backend.clickRow(b.index) }

    // ---------------------------------------------------------------- a text field: name above, value in a box, error below
    component Field: Item {
        id: field
        property var f: null
        property bool secret: false
        visible: !!f
        width: parent ? parent.width : 400
        height: f ? (f.error ? 92 : 70) : 0
        Text { textFormat: Text.PlainText; text: field.f ? field.f.label : ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 16 }
        Rectangle {
            y: 22; width: parent.width; height: 44
            color: field.f && field.f.focused ? page.root.bone : "#0E0F11"
            border.width: field.f && field.f.error ? 2 : 1
            border.color: field.f && field.f.error ? page.red : (field.f && field.f.focused ? page.acc : page.root.line)
            Text {
                x: 14; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 28 - (verbText.visible ? verbText.width + 12 : 0)
                elide: Text.ElideLeft; textFormat: Text.PlainText
                text: field.f ? (field.f.value || "") : ""
                color: field.f && field.f.focused ? page.ink : page.root.textC; font.family: page.root.mono; font.pixelSize: 20
            }
            Text { id: verbText; visible: !!(field.f && field.f.verb); anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: field.f ? (field.f.verb || "") : ""; color: page.ink; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 17 }
            TapHandler { onTapped: page.click(field.f) }
        }
        Text { visible: !!(field.f && field.f.error); y: 70; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: field.f ? (field.f.error || "") : ""; color: page.red; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: 16 }
    }
    // ---------------------------------------------------------------- a button: primary filled, secondary outlined
    component Button: Rectangle {
        id: button
        property var b: null
        property bool primary: false
        visible: !!b
        height: 50
        color: b && b.focused ? page.root.bone : (primary ? page.acc : "#24272C")
        border.width: primary || (b && b.focused) ? 0 : 1; border.color: page.root.line
        opacity: b && b.disabled ? 0.45 : 1
        Text {
            anchors.centerIn: parent; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
            textFormat: Text.PlainText; text: button.b ? button.b.label : ""
            color: (button.b && button.b.focused) || button.primary ? page.ink : page.root.textC
            font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 28
        }
        TapHandler { onTapped: page.click(button.b) }
    }
    // ---------------------------------------------------------------- a small link or toggle
    component Link: Rectangle {
        id: link
        property var b: null
        property bool check: false
        property bool on: false
        visible: !!b
        height: 34; width: linkRow.implicitWidth + 20; radius: 3
        color: b && b.focused ? page.root.bone : "transparent"
        Row {
            id: linkRow
            x: 10; anchors.verticalCenter: parent.verticalCenter; spacing: 8
            Rectangle {
                visible: link.check; width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter
                color: link.on ? page.acc : "transparent"; border.width: 2; border.color: link.on ? page.acc : "#6B6E75"
                Text { visible: link.on; anchors.centerIn: parent; textFormat: Text.PlainText; text: "✓"; color: page.ink; font.pixelSize: 13; font.weight: Font.Bold }
            }
            Text {
                textFormat: Text.PlainText; text: link.b ? link.b.label : ""; anchors.verticalCenter: parent.verticalCenter
                color: link.b && link.b.focused ? page.ink : (link.check ? page.root.textC : page.acc)
                font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: 17; font.underline: !link.check
            }
            Text {
                visible: !!(link.b && link.b.value) && !link.check; anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText; text: link.b ? (link.b.value || "") : ""; width: Math.min(implicitWidth, 300); elide: Text.ElideMiddle
                color: link.b && link.b.focused ? page.ink : page.root.muted; font.family: page.root.mono; font.pixelSize: 16
            }
        }
        TapHandler { onTapped: page.click(link.b) }
    }

    Rectangle {
        id: card
        objectName: "loginCard"
        width: 920; height: band.height + 18 + content.implicitHeight + 26
        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.max(12, (parent.height - height) / 2)
        color: page.card; border.width: 1; border.color: page.root.line
        clip: true
        // the game on top: its name, and the player's own fighter render faded at the right
        Rectangle {
            id: band
            width: parent.width; height: 112; color: "#101114"; clip: true
            Image { visible: !!page.o.art; source: page.o.art || ""; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectCrop; width: 420; height: 420; x: parent.width - 380; y: -60; opacity: 0.35 }
            Rectangle { width: 8; height: parent.height; color: page.acc }
            Column {
                x: 36; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                Text { textFormat: Text.PlainText; text: page.o.game || ""; color: page.acc; font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: 19 }
                Text { objectName: "loginTitle"; textFormat: Text.PlainText; text: page.o.title || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 44 }
            }
        }
        Column {
            id: content
            x: 36; y: band.height + 18; width: card.width - 72; spacing: 12
            // a general error or status (field errors sit under their field)
            Text {
                visible: text !== ""; width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText
                text: page.o.error ? (page.o.errorText || "") : (page.o.message || "")
                color: page.o.error ? page.red : page.root.muted; font.family: page.root.sans; font.weight: page.o.error ? Font.DemiBold : Font.Normal; font.pixelSize: 18
            }
            // ---------------------------------------------------------------- login
            Button { visible: page.o.page === "main" && !!page.o.saved; b: page.o.saved; width: parent.width; height: 46 }
            Field { visible: !!page.o.name; f: page.o.name; width: parent.width }
            Row {
                visible: page.o.page === "main"
                spacing: 28; width: parent.width
                Column {
                    id: accountColumn
                    width: (parent.width - 28) * 0.62; spacing: 10
                    Text { textFormat: Text.PlainText; text: page.o.accountTitle || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: 26 }
                    Field { f: page.o.password; width: parent.width }
                    Row {
                        spacing: 8
                        Link { b: page.o.remember; check: true; on: !!(page.o.remember && page.o.remember.on) }
                        Link { b: page.o.show; check: true; on: !!(page.o.show && page.o.show.on) }
                    }
                    Button { b: page.o.login; primary: true; width: parent.width }
                    Row {
                        spacing: 4
                        Link { b: page.o.register }
                        Link { b: page.o.forgot }
                    }
                }
                Rectangle { width: 1; height: accountColumn.height; color: page.root.line }
                Column {
                    width: (parent.width - 28) * 0.38 - 29; spacing: 10
                    Text { textFormat: Text.PlainText; text: page.o.guestTitle || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: 26 }
                    Text { width: parent.width; wrapMode: Text.Wrap; textFormat: Text.PlainText; text: page.o.guestNote || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: 17 }
                    Item { width: 1; height: 8 }
                    Button { b: page.o.guest; width: parent.width }
                }
            }
            // ---------------------------------------------------------------- forgot password: the recovery rows
            Column {
                visible: page.o.page === "recover"
                width: parent.width; spacing: 8
                Repeater {
                    model: page.o.page === "recover" ? page.list(page.o.recover).length : 0
                    Item {
                        id: recoverRow
                        required property int index
                        readonly property var r: page.root.ok(page.o.recover, index)
                        readonly property bool last: index === page.list(page.o.recover).length - 1
                        width: parent.width; height: last ? 58 : 70
                        Field { visible: !recoverRow.last; f: recoverRow.r; width: parent.width }
                        Button { visible: recoverRow.last; b: recoverRow.r; primary: true; width: parent.width; y: 6 }
                    }
                }
                Link { b: page.o.back }
            }
            // extra rows of a game, then the server line
            Flow {
                visible: page.list(page.o.extra).length > 0; width: parent.width; spacing: 6
                Repeater { model: page.list(page.o.extra).length; Link { required property int index; b: page.root.ok(page.o.extra, index) } }
            }
            Rectangle { width: parent.width; height: 1; color: page.root.line }
            Flow {
                width: parent.width; spacing: 6
                Repeater { model: page.list(page.o.footer).length; Link { required property int index; b: page.root.ok(page.o.footer, index) } }
            }
        }
    }
}
