import QtQuick

// The Online login page (nav_online_login): one centred card. The game on top, the name field, Account and Play as
// guest side by side, the server as a small line at the bottom. "Forgot password?" swaps the card to the recovery rows.
Item {
    id: page
    required property var root
    readonly property var o: root.v.online || ({})
    readonly property var acc: Theme.readableAccent(root.v.accent)
    readonly property color card: Theme.card
    readonly property color ink: Theme.ground
    readonly property color red: Theme.error
    function list(a) { return a || [] }
    function click(b) { if (b && b.index !== undefined && b.index >= 0) root.backend.clickRow(b.index) }

    // ---------------------------------------------------------------- a text field: name above, value in a box, error below
    component Field: Item {
        id: field
        property var f: null
        property bool secret: false
        visible: !!f
        width: parent ? parent.width : 400
        height: f ? nativeField.height + (f.error ? 24 : 0) : 0
        EditableField {
            id: nativeField
            root: page.root; field: parent.f || ({}); width: parent.width
        }
        Text { visible: !!(field.f && field.f.error); y: nativeField.height + 4; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: field.f ? (field.f.error || "") : ""; color: page.red; font.family: page.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(16)}
    }
    // ---------------------------------------------------------------- a button: primary filled, secondary outlined
    component Button: Rectangle {
        id: button
        property var b: null
        property bool primary: false
        visible: !!b
        objectName: "loginButton"
        height: Math.max(Theme.target(50), buttonLabel.implicitHeight + 20)
        color: b && b.focused ? page.root.bone : (primary ? page.acc : "#24272C")
        border.width: primary || (b && b.focused) ? 0 : 1; border.color: page.root.line
        opacity: b && b.disabled ? 0.45 : 1
        Text {
            id: buttonLabel; objectName: "loginButtonLabel"
            anchors.centerIn: parent; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
            textFormat: Text.PlainText; text: button.b ? button.b.label : ""
            color: (button.b && button.b.focused) || button.primary ? page.ink : page.root.textC
            font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(28)
        }
        TapHandler { id: uiTap1; onTapped: page.click(button.b) }
        Interaction { handler: uiTap1; selected: !!(button.b && button.b.focused); name: (button.b || {}).label || ""; onActivated: page.click(button.b) }
    }
    // ---------------------------------------------------------------- a small link or toggle
    component Link: Rectangle {
        id: link
        property var b: null
        property bool check: false
        property bool on: false
        readonly property bool editable: !!(b && b.fieldId)
        readonly property real naturalWidth: linkLabel.implicitWidth + (check ? 26 : 0) + (linkValue.visible ? Math.min(linkValue.implicitWidth, 300) + 8 : 0) + 20
        visible: !!b
        height: editable ? linkField.height : Math.max(Theme.target(44), linkRow.implicitHeight + 12)
        width: editable ? parent.width : Math.min(naturalWidth, parent.width); radius: 3
        color: b && b.focused ? page.root.bone : "transparent"
        EditableField { id: linkField; visible: link.editable; width: parent.width; root: page.root; field: link.b || ({}) }
        Row {
            id: linkRow
            visible: !link.editable
            x: 10; width: parent.width - 20; anchors.verticalCenter: parent.verticalCenter; spacing: 8
            Rectangle {
                visible: link.check; width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter
                color: link.on ? page.acc : "transparent"; border.width: 2; border.color: link.on ? page.acc : Theme.muted
                Text { visible: link.on; anchors.centerIn: parent; textFormat: Text.PlainText; text: "✓"; color: page.ink; font.pixelSize: Theme.px(13); font.weight: Font.Bold }
            }
            Text {
                id: linkLabel; objectName: "loginLinkLabel"
                width: Math.min(implicitWidth, Math.max(0, link.width - 20 - (link.check ? 26 : 0) - (linkValue.visible ? linkValue.width + 8 : 0)))
                wrapMode: Text.Wrap
                textFormat: Text.PlainText; text: link.b ? link.b.label : ""; anchors.verticalCenter: parent.verticalCenter
                color: link.b && link.b.focused ? page.ink : (link.check ? page.root.textC : page.acc)
                font.family: page.root.sans; font.weight: Font.Medium; font.pixelSize: Theme.px(17); font.underline: !link.check
            }
            Text {
                id: linkValue
                visible: !!(link.b && link.b.value) && !link.check; anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText; text: link.b ? (link.b.value || "") : ""; width: visible ? Math.min(implicitWidth, 300, link.width * 0.4) : 0; elide: Text.ElideMiddle
                color: link.b && link.b.focused ? page.ink : page.root.muted; font.family: page.root.mono; font.pixelSize: Theme.px(16)
            }
        }
        TapHandler { id: uiTap2; enabled: !link.editable; onTapped: page.click(link.b) }
        Interaction { visible: !link.editable; handler: uiTap2; selected: !!(link.b && link.b.focused); name: (link.b || {}).label || ""; onActivated: page.click(link.b) }
    }

    Rectangle {
        id: card
        objectName: "loginCard"
        width: 920; height: Math.min(page.height - 24, band.height + 18 + content.implicitHeight + 26)
        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.max(12, (parent.height - height) / 2)
        color: page.card; border.width: 1; border.color: page.root.line
        clip: true
        // the game on top: its name, and the player's own fighter render faded at the right
        Rectangle {
            id: band
            width: parent.width; height: Math.max(112, bandText.implicitHeight + 32); color: "#101114"; clip: true
            Image { visible: !!page.o.art; source: page.o.art || ""; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectCrop; width: 420; height: 420; x: parent.width - 380; y: -60; opacity: 0.35 }
            Rectangle { width: 8; height: parent.height; color: page.acc }
            Column {
                id: bandText; x: 36; width: parent.width - 72; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                Text { textFormat: Text.PlainText; text: page.o.game || ""; color: page.acc; font.family: page.root.mono; font.weight: Font.DemiBold; font.pixelSize: Theme.px(19)}
                Text { objectName: "loginTitle"; width: parent.width; wrapMode: Text.Wrap; textFormat: Text.PlainText; text: page.o.title || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(44)}
            }
        }
        Flickable {
            id: loginViewport; objectName: "loginViewport"
            x: 36; y: band.height + 18; width: card.width - 72; height: card.height - y - 26
            contentHeight: content.implicitHeight; clip: true; boundsBehavior: Flickable.StopAtBounds
            function revealFocused(item) {
                for (var child of item.children) {
                    if ((child.f && child.f.focused) || (child.b && child.b.focused)) {
                        var point = child.mapToItem(content, 0, 0)
                        if (point.y < contentY) contentY = point.y
                        else if (point.y + child.height > contentY + height) contentY = point.y + child.height - height
                        return true
                    }
                    if (child.children && revealFocused(child)) return true
                }
                return false
            }
            Connections { target: page.root.backend; function onViewChanged() { Qt.callLater(() => loginViewport.revealFocused(content)) } }
        }
        Column {
            id: content
            parent: loginViewport.contentItem
            width: loginViewport.width; spacing: 12
            // a general error or status (field errors sit under their field)
            Text {
                visible: text !== ""; width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText
                text: page.o.error ? (page.o.errorText || "") : (page.o.message || "")
                color: page.o.error ? page.red : page.root.muted; font.family: page.root.sans; font.weight: page.o.error ? Font.DemiBold : Font.Normal; font.pixelSize: Theme.px(18)
            }
            // another launcher of this game is open: one sentence and Use OpenRecomp here / Keep the other one
            Rectangle {
                objectName: "otherLauncherNote"
                visible: !!(page.o.notice && page.o.notice.text)
                width: parent.width; height: visible ? noticeColumn.implicitHeight + 24 : 0
                color: "#24272C"; border.width: 1; border.color: page.acc
                Column {
                    id: noticeColumn
                    x: 16; y: 12; width: parent.width - 32; spacing: 10
                    Text { width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight; textFormat: Text.PlainText; text: page.o.notice ? (page.o.notice.text || "") : ""; color: page.root.textC; font.family: page.root.sans; font.pixelSize: Theme.px(18)}
                    Row {
                        spacing: 12
                        Repeater {
                            model: page.o.notice ? page.list(page.o.notice.buttons).length : 0
                            Button { required property int index; b: page.root.ok(page.o.notice.buttons, index); primary: index === 0; width: 340 }
                        }
                    }
                }
            }
            // ---------------------------------------------------------------- login
            Button { visible: page.o.page === "main" && !!page.o.saved; b: page.o.saved; width: parent.width }
            Field { visible: !!page.o.name; f: page.o.name; width: parent.width }
            Row {
                visible: page.o.page === "main"
                spacing: 28; width: parent.width
                Column {
                    id: accountColumn
                    width: (parent.width - 28) * 0.62; spacing: 10
                    Text { textFormat: Text.PlainText; text: page.o.accountTitle || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(26)}
                    Field { f: page.o.password; width: parent.width }
                    Flow {
                        width: parent.width; spacing: 8
                        Link { b: page.o.remember; check: true; on: !!(page.o.remember && page.o.remember.on) }
                        Link { b: page.o.show; check: true; on: !!(page.o.show && page.o.show.on) }
                    }
                    Button { b: page.o.login; primary: true; width: parent.width }
                    Flow {
                        width: parent.width; spacing: 4
                        Link { b: page.o.register }
                        Link { b: page.o.forgot }
                    }
                }
                Rectangle { width: 1; height: accountColumn.height; color: page.root.line }
                Column {
                    width: (parent.width - 28) * 0.38 - 29; spacing: 10
                    Text { objectName: "loginGuestTitle"; width: parent.width; wrapMode: Text.Wrap; textFormat: Text.PlainText; text: page.o.guestTitle || ""; color: page.root.textC; font.family: page.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(26)}
                    Text { width: parent.width; wrapMode: Text.Wrap; textFormat: Text.PlainText; text: page.o.guestNote || ""; color: page.root.muted; font.family: page.root.sans; font.pixelSize: Theme.px(17)}
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
                        width: parent.width; height: last ? recoveryButton.height + 6 : recoveryField.height
                        Field { id: recoveryField; visible: !recoverRow.last; f: recoverRow.r; width: parent.width }
                        Button { id: recoveryButton; visible: recoverRow.last; b: recoverRow.r; primary: true; width: parent.width; y: 6 }
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
