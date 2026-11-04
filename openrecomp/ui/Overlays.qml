import QtQuick

// Overlays leave the focused hint and prompt bar visible below them.
Item {
    id: ov
    required property var root
    readonly property var v: root.v
    readonly property real drawerRowHeight: Theme.target(64)
    visible: v.overlay !== "" || (v.globalOffers || []).length > 0

    Rectangle { objectName: "overlayMask"; visible: ov.v.overlay !== ""; x: 0; y: 0; width: 1920; height: 1080 - ov.root.promptHeight - ov.root.hintHeight; color: "#C2000000"; TapHandler {} }
    GlobalOffer { objectName: "globalOffer"; root: ov.root; z: 1000 }

    Rectangle {
        objectName: "nativeTextDialog"
        visible: ov.v.overlay === "native"
        width: 1000; height: nativeContent.height + 48
        x: (1920 - width) / 2; y: (972 - height) / 2
        color: Theme.card; border.width: 1; border.color: Theme.focus
        Column {
            id: nativeContent; x: 24; y: 24; width: parent.width - 48; spacing: 24
            EditableField { root: ov.root; field: ov.v.nativeField || ({}); width: parent.width }
            Row {
                width: parent.width; spacing: 16
                OnlineStyle.SecondaryButton {
                    width: (parent.width - 16) / 2; maxW: width
                    b: ({index: 0, label: ov.v.nativeCancel || ""})
                    onActivated: { ov.root.backend.finishEdit(ov.v.nativeEdit, false); ov.root.focusStage() }
                }
                OnlineStyle.PrimaryButton {
                    width: (parent.width - 16) / 2; maxW: width
                    b: ({index: 1, label: ov.v.nativeDone || ""})
                    onActivated: { ov.root.backend.finishEdit(ov.v.nativeEdit, true); ov.root.focusStage() }
                }
            }
        }
    }

    // ---------------------------------------------------------------- dialog: the safe answer has the focus
    Rectangle {
        visible: ov.v.overlay === "dialog"
        objectName: "dialogCard"
        width: 980; height: Math.min(856, dialogColumn.implicitHeight + 64)
        x: (1920 - width) / 2; y: (972 - height) / 2
        color: Theme.card; border.width: 1; border.color: ov.root.line
        Rectangle { width: 5; height: parent.height; color: Theme.readableAccent(ov.v.accent) }
        Column {
            id: dialogColumn
            x: 36; y: 32; width: parent.width - 72; spacing: 20
            Text { textFormat: Text.PlainText; width: parent.width; text: ov.v.dialog.title; wrapMode: Text.Wrap; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(44); lineHeight: 1.05; maximumLineCount: 3; elide: Text.ElideRight }
            Text { width: parent.width; text: ov.v.dialog.text; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: ov.root.textC; font.family: ov.root.sans; font.pixelSize: Theme.px(23); maximumLineCount: 18; elide: Text.ElideRight; bottomPadding: 8 }
            Row {
                spacing: 12
                Repeater {
                    model: ov.v.dialog.options.length
                    Rectangle {
                        required property int index
                        readonly property var o: ov.root.ok(ov.v.dialog.options, index)
                        // Answers share one line; the safe answer keeps the controller focus.
                        objectName: "dialogOption"
                        width: (dialogColumn.width - 12 * (ov.v.dialog.options.length - 1)) / Math.max(1, ov.v.dialog.options.length); height: Theme.target(64)
                        border.width: 1; border.color: o.focused ? Theme.readableAccent(ov.v.accent) : ov.root.line
                        color: o.focused ? ov.root.bone : "#24272C"
                        Text { textFormat: Text.PlainText; anchors.centerIn: parent; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter; text: parent.o.label || ""; elide: Text.ElideRight; fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(19); color: parent.o.focused ? Theme.ground : ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(30)}
                        TapHandler { id: uiTap0; onTapped: ov.root.backend.clickEntry(parent.index) }
                        Interaction { handler: uiTap0; selected: !!parent.o.focused; onActivated: ov.root.backend.clickEntry(parent.index) }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- the quick drawer keeps your place
    Rectangle {
        visible: ov.v.overlay === "drawer"
        objectName: "drawerPanel"
        x: 1920 - 824; y: 24; width: 800; height: 924
        color: Theme.card; border.width: 1; border.color: ov.root.line
        Item {
            y: 28; width: parent.width; height: parent.height - 28
            Text { textFormat: Text.PlainText; x: 28; width: parent.width - 56; elide: Text.ElideRight; text: ov.v.quickAccess; bottomPadding: 16; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(40)}
            Item {
                objectName: "drawerViewport"
                x: 20; y: 76; width: parent.width - 40; height: parent.height - y - 20; clip: true
                Column {
                    width: parent.width
                    y: -Math.max(0, ov.v.drawer.rows.findIndex(r => r.focused) - Math.floor(parent.height / ov.drawerRowHeight) + 1) * ov.drawerRowHeight
                    Repeater {
                        model: ov.v.drawer.rows.length
                        Rectangle {
                            objectName: "drawerRow"
                            required property int index
                            readonly property var r: ov.root.ok(ov.v.drawer.rows, index)
                            width: parent.width; height: ov.drawerRowHeight
                            border.width: 1; border.color: r.focused ? Theme.readableAccent(ov.v.accent) : "transparent"
                            color: r.focused ? ov.root.bone : "transparent"
                            Text { textFormat: Text.PlainText; x: 18; width: parent.r.value ? parent.width * 0.50 - 26 : parent.width - 36; height: parent.height - 12; elide: Text.ElideRight; fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(19); verticalAlignment: Text.AlignVCenter; anchors.verticalCenter: parent.verticalCenter; text: parent.r.label || ""; color: parent.r.focused ? Theme.ground : ov.root.textC; font.family: ov.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(28)}
                            Text { textFormat: Text.PlainText; width: parent.width * 0.46 - 18; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight; anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter; text: parent.r.value || ""; color: parent.r.focused ? Theme.ground : ov.root.muted; font.family: ov.root.mono; font.pixelSize: Theme.px(21)}
                            TapHandler { id: uiTap1; onTapped: ov.root.backend.clickEntry(parent.index) }
                            Interaction { handler: uiTap1; selected: !!parent.r.focused; onActivated: ov.root.backend.clickEntry(parent.index) }
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- character grid, as in T5DR's launcher
    Rectangle {
        visible: ov.v.overlay === "fighters"
        x: 60; y: 62; width: 1800; height: 880
        color: Theme.card; border.width: 1; border.color: ov.root.line
        Row {
            x: 32; y: 24; spacing: 28
            Text { textFormat: Text.PlainText; text: ov.v.fighterTitle; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(56)}
            Text { textFormat: Text.PlainText; visible: !!ov.v.grid.main; text: ov.v.fighterMain + (ov.v.grid.main || ""); color: ov.root.muted; font.family: ov.root.sans; font.pixelSize: Theme.px(26); anchors.baseline: parent.children[0].baseline }
        }
        Grid {
            x: 32; y: 96; columns: 9; spacing: 6
            Repeater {
                model: (ov.v.grid.cells || []).length
                Rectangle {
                    id: cell
                    required property int index
                    readonly property var c: ov.root.ok(ov.v.grid.cells, index)
                    width: (1800 - 64 - 48) / 9; height: 186
                    z: c.focused ? 2 : 1
                    scale: c.focused ? 1.05 : 1
                    Behavior on scale { enabled: !ov.root.reducedMotion; NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
                    color: c.focused ? ov.root.bone : (c.chosen ? Theme.readableAccent(ov.v.accent) : "#1B1D21")
                    FighterPortrait {
                        objectName: "fighterSelectPortrait"
                        visible: !cell.c.random
                        anchors.horizontalCenter: parent.horizontalCenter; y: 6; width: 142; height: 142
                        source: cell.c.image || ""
                    }
                    Grid {
                        visible: !!cell.c.random
                        anchors.horizontalCenter: parent.horizontalCenter; y: 6; columns: 2; spacing: 2
                        Repeater {
                            model: cell.c.random ? (ov.v.grid.mosaic || []).length : 0
                            Image { required property int index; width: 70; height: 70; source: (ov.v.grid.mosaic || [])[index] || ""; asynchronous: true; mipmap: true }
                        }
                    }
                    Text { textFormat: Text.PlainText;
                        anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 8
                        width: parent.width - 8; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                        text: cell.c.name || ""
                        color: cell.c.focused || cell.c.chosen ? Theme.ground : ov.root.textC
                        font.family: ov.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(26)
                    }
                    Rectangle {
                        visible: !!cell.c.main
                        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 6
                        width: mainTag.implicitWidth + 12; height: mainTag.implicitHeight + 4
                        color: Theme.ground
                        Text { textFormat: Text.PlainText; id: mainTag; anchors.centerIn: parent; text: ov.v.mainLabel; color: ov.root.bone; font.family: ov.root.mono; font.weight: Font.DemiBold; font.pixelSize: Theme.px(16)}
                    }
                    TapHandler { id: uiTap2; onTapped: ov.root.backend.clickCell(cell.index) }
                    Interaction { handler: uiTap2; selected: !!cell.c.focused; onActivated: ov.root.backend.clickCell(cell.index) }
                }
            }
        }
    }

    // ---------------------------------------------------------------- on-screen keyboard
    Rectangle {
        visible: ov.v.overlay === "osk"
        width: 1240; height: oskColumn.implicitHeight + 96
        x: (1920 - width) / 2; y: (972 - height) / 2
        color: Theme.card; border.width: 1; border.color: ov.root.line
        Column {
            id: oskColumn
            x: 64; y: 48; width: 1112; spacing: 8
            Text { objectName: "oskTitle"; width: parent.width; height: 84; fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(32); textFormat: Text.PlainText; text: ov.v.osk.title; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(44)}
            Rectangle {
                id: oskField
                objectName: "oskField"
                z: 2                              // its menu opens over the key rows below
                width: parent.width; height: 88; color: ov.root.bar
                // Ctrl+A: the whole text is marked; the next letter, paste or Delete replaces it.
                Rectangle { visible: !!ov.v.osk.selected; x: 20; width: Math.min(oskText.contentWidth, oskText.width) + 16; height: 64; anchors.verticalCenter: parent.verticalCenter; color: Theme.readableAccent(ov.v.accent); opacity: 0.45 }
                Text { id: oskText; x: 28; width: parent.width - 56; elide: Text.ElideLeft; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: ov.v.osk.text; color: ov.root.textC; font.family: ov.root.mono; font.weight: Font.Medium; font.pixelSize: Theme.px(48)}
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 4; color: Theme.readableAccent(ov.v.accent) }
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: (point) => { oskMenu.x = Math.min(point.position.x, oskField.width - oskMenu.width); oskMenu.visible = true }
                }
                TapHandler { acceptedButtons: Qt.LeftButton; onTapped: oskMenu.visible = false }
                // The right-click menu: Paste, and Copy where the text may leave (never a password).
                Rectangle {
                    id: oskMenu
                    objectName: "oskMenu"
                    visible: false
                    y: parent.height - 4; z: 5
                    width: 280; height: oskMenuColumn.implicitHeight
                    color: "#24272C"; border.color: ov.root.line; border.width: 2
                    Connections { target: ov; function onVChanged() { if (ov.v.overlay !== "osk") oskMenu.visible = false } }
                    Column {
                        id: oskMenuColumn
                        width: parent.width
                        Repeater {
                            model: ov.v.osk.canCopy ? ["paste", "copy"] : ["paste"]
                            Rectangle {
                                required property string modelData
                                objectName: "oskMenu_" + modelData
                                width: oskMenuColumn.width; height: Theme.target(64)
                                color: menuHover.hovered ? ov.root.bone : "transparent"
                                Text { x: 24; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: parent.modelData === "paste" ? ov.v.osk.paste : ov.v.osk.copy; color: menuHover.hovered ? Theme.ground : ov.root.textC; font.family: ov.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.px(30)}
                                HoverHandler { id: menuHover }
                                TapHandler { id: uiTap3; onTapped: { oskMenu.visible = false; ov.root.backend.oskEdit(parent.modelData) } }
                                Interaction { handler: uiTap3; selected: false; onActivated: { oskMenu.visible = false; ov.root.backend.oskEdit(parent.modelData) } }
                            }
                        }
                    }
                }
            }
            Item { width: 1; height: 10 }
            Repeater {
                model: ov.v.osk.rows.length
                Row {
                    id: keyRow
                    required property int index
                    readonly property var keys: ov.v.osk.rows[index] || []
                    spacing: 8
                    Repeater {
                        model: keyRow.keys.length
                        Rectangle {
                            required property int index
                            readonly property var k: ov.root.ok(keyRow.keys, index)
                            width: (1112 - 8 * (keyRow.keys.length - 1)) / keyRow.keys.length; height: 72
                            color: k.focused ? ov.root.bone : "#24272C"
                            Text { objectName: "oskKeyLabel"; anchors.centerIn: parent; width: parent.width - 16; height: parent.height - 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; fontSizeMode: Text.Fit; minimumPixelSize: Theme.px(20); textFormat: Text.PlainText; text: parent.k.label || ""; color: parent.k.focused ? Theme.ground : ov.root.textC; font.family: ov.root.mono; font.weight: Font.DemiBold; font.pixelSize: Theme.px(30)}
                            TapHandler { id: uiTap4; onTapped: ov.root.backend.clickKey(parent.k.row, parent.k.col) }
                            Interaction { handler: uiTap4; selected: !!parent.k.focused; onActivated: ov.root.backend.clickKey(parent.k.row, parent.k.col) }
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- a file or folder, by pad
    Rectangle {
        visible: ov.v.overlay === "picker"
        objectName: "pickerPanel"
        x: 260; y: 20; width: 1400; height: 904
        color: Theme.card; border.width: 1; border.color: ov.root.line
        Column {
            id: pickerHeader
            x: 48; y: 32; width: 1304
            Text { textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight; text: ov.v.picker.title; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: Theme.px(64)}
            Text { textFormat: Text.PlainText; width: parent.width; bottomPadding: 16; text: ov.v.picker.path; elide: Text.ElideMiddle; color: ov.root.muted; font.family: ov.root.mono; font.pixelSize: Theme.px(24)}
            Text { textFormat: Text.PlainText; objectName: "pickerMessage"; width: parent.width; height: 64; text: ov.v.picker.message || ""; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; color: ov.root.textC; font.family: ov.root.sans; font.pixelSize: Theme.px(26)}
        }
        Flickable {
            id: pickerScroll
            objectName: "pickerViewport"
            x: 48; y: pickerHeader.y + pickerHeader.height + 12; width: 1304; height: parent.height - y - 20
            contentHeight: pickerRows.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            function reveal() {
                for (var n = 0; n < pickerRepeater.count; ++n) {
                    var row = pickerRepeater.itemAt(n)
                    if (!row || !row.r.focused) continue
                    if (row.y < contentY) contentY = row.y
                    else if (row.y + row.height > contentY + height) contentY = row.y + row.height - height
                    contentY = Math.max(0, Math.min(contentY, Math.max(0, contentHeight - height)))
                }
            }
            onHeightChanged: Qt.callLater(reveal)
            onContentHeightChanged: Qt.callLater(reveal)
            Connections { target: ov.root.backend; function onViewChanged() { Qt.callLater(pickerScroll.reveal) } }
            Column {
                id: pickerRows; width: parent.width
                onPositioningComplete: Qt.callLater(pickerScroll.reveal)
                Repeater {
                    id: pickerRepeater
                    model: ov.v.picker.rows.length
                    Rectangle {
                        objectName: "pickerRow"
                        required property int index
                        readonly property var r: ov.root.ok(ov.v.picker.rows, index)
                        width: pickerRows.width; height: Theme.target(60)
                        color: r.focused ? ov.root.bone : "transparent"
                        Text { textFormat: Text.PlainText; x: 20; width: 160; elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter; text: parent.r.kind === "dir" ? ov.v.folder : (parent.r.kind === "pick" ? ov.v.pick : ov.v.file); color: parent.r.focused ? Theme.ground : ov.root.muted; font.family: ov.root.mono; font.pixelSize: Theme.px(22)}
                        Text { textFormat: Text.PlainText; x: 200; width: 1080; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideMiddle; text: parent.r.name || ""; color: parent.r.focused ? Theme.ground : ov.root.textC; font.family: ov.root.sans; font.weight: parent.r.kind === "file" ? Font.DemiBold : Font.Normal; font.pixelSize: Theme.px(30)}
                        TapHandler { id: uiTap5; onTapped: ov.root.backend.clickEntry(parent.r.index) }
                        Interaction { handler: uiTap5; selected: !!parent.r.focused; onActivated: ov.root.backend.clickEntry(parent.r.index) }
                    }
                }
            }
        }
        Text { textFormat: Text.PlainText; visible: ov.v.picker.up; x: 1360; y: 130; text: "▲"; color: ov.root.muted; font.pixelSize: Theme.px(18)}
        Text { textFormat: Text.PlainText; visible: ov.v.picker.down; x: 1360; y: 890; text: "▼"; color: ov.root.muted; font.pixelSize: Theme.px(18)}
    }
}
