import QtQuick

// Overlays leave the focused hint and prompt bar visible below them.
Item {
    id: ov
    required property var root
    readonly property var v: root.v
    visible: v.overlay !== ""

    Rectangle { objectName: "overlayMask"; x: 0; y: 0; width: 1920; height: 1080 - 60 - 48; color: "#C2000000"; TapHandler {} }

    // ---------------------------------------------------------------- dialog: the safe answer has the focus
    Rectangle {
        visible: ov.v.overlay === "dialog"
        width: 860; height: dialogColumn.implicitHeight + 112
        x: (1920 - width) / 2; y: (972 - height) / 2
        color: ov.root.panel
        Column {
            id: dialogColumn
            x: 64; y: 56; width: 732; spacing: 16
            Text { textFormat: Text.PlainText; width: parent.width; text: ov.v.dialog.title; wrapMode: Text.Wrap; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 88; lineHeight: 0.95 }
            Text { width: parent.width; text: ov.v.dialog.text; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: ov.root.textC; font.family: ov.root.sans; font.pixelSize: 30; bottomPadding: 24 }
            Row {
                spacing: 12
                Repeater {
                    model: ov.v.dialog.options.length
                    Rectangle {
                        required property int index
                        readonly property var o: ov.root.ok(ov.v.dialog.options, index)
                        // Two answers 360 each; three (e.g. Cancel / Copy commands / Install) share the same width.
                        width: (732 - 12 * (ov.v.dialog.options.length - 1)) / Math.max(1, ov.v.dialog.options.length); height: 104
                        color: o.focused ? ov.root.bone : "#24272C"
                        Text { textFormat: Text.PlainText; anchors.centerIn: parent; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter; text: parent.o.label || ""; elide: Text.ElideRight; fontSizeMode: Text.Fit; minimumPixelSize: 24; color: parent.o.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 56 }
                        TapHandler { onTapped: ov.root.backend.clickEntry(parent.index) }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- the quick drawer keeps your place
    Rectangle {
        visible: ov.v.overlay === "drawer"
        objectName: "drawerPanel"
        x: 1920 - 780; y: 0; width: 780; height: 972
        color: ov.root.panel
        Item {
            y: 40; width: parent.width; height: parent.height - 40
            Text { textFormat: Text.PlainText; x: 48; width: parent.width - 96; elide: Text.ElideRight; text: ov.v.quickAccess; bottomPadding: 20; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 72 }
            Item {
                objectName: "drawerViewport"
                y: 112; width: parent.width; height: parent.height - y; clip: true
                Column {
                    width: parent.width
                    y: -Math.max(0, ov.v.drawer.rows.findIndex(r => r.focused) - 8) * 76
                    Repeater {
                        model: ov.v.drawer.rows.length
                        Rectangle {
                            objectName: "drawerRow"
                            required property int index
                            readonly property var r: ov.root.ok(ov.v.drawer.rows, index)
                            width: 780; height: r.focused ? 92 : 76
                            color: r.focused ? ov.root.bone : "transparent"
                            Text { textFormat: Text.PlainText; x: 48; width: 330; height: parent.height - 12; elide: Text.ElideRight; fontSizeMode: Text.Fit; minimumPixelSize: 28; verticalAlignment: Text.AlignVCenter; anchors.verticalCenter: parent.verticalCenter; text: parent.r.label || ""; color: parent.r.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: parent.r.focused ? 44 : 36 }
                            Text { textFormat: Text.PlainText; width: 310; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight; anchors.right: parent.right; anchors.rightMargin: 48; anchors.verticalCenter: parent.verticalCenter; text: parent.r.value || ""; color: parent.r.focused ? "#0E0F11" : ov.root.muted; font.family: ov.root.sans; font.pixelSize: 26 }
                            TapHandler { onTapped: ov.root.backend.clickEntry(parent.index) }
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
        color: ov.root.panel
        Row {
            x: 32; y: 24; spacing: 28
            Text { textFormat: Text.PlainText; text: ov.v.fighterTitle; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 56 }
            Text { textFormat: Text.PlainText; visible: !!ov.v.grid.main; text: ov.v.fighterMain + (ov.v.grid.main || ""); color: ov.root.muted; font.family: ov.root.sans; font.pixelSize: 26; anchors.baseline: parent.children[0].baseline }
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
                    color: c.focused ? ov.root.bone : (c.chosen ? ov.v.accent : "#1B1D21")
                    Image {
                        visible: !!cell.c.image
                        anchors.horizontalCenter: parent.horizontalCenter; y: 6; width: 142; height: 142
                        source: cell.c.image || ""; asynchronous: true; mipmap: true; fillMode: Image.PreserveAspectFit
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
                        color: cell.c.focused || cell.c.chosen ? "#0E0F11" : ov.root.textC
                        font.family: ov.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: 26
                    }
                    Rectangle {
                        visible: !!cell.c.main
                        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 6
                        width: mainTag.implicitWidth + 12; height: mainTag.implicitHeight + 4
                        color: "#0E0F11"
                        Text { textFormat: Text.PlainText; id: mainTag; anchors.centerIn: parent; text: ov.v.mainLabel; color: ov.root.bone; font.family: ov.root.mono; font.weight: Font.DemiBold; font.pixelSize: 16 }
                    }
                    TapHandler { onTapped: ov.root.backend.clickCell(cell.index) }
                }
            }
        }
    }

    // ---------------------------------------------------------------- on-screen keyboard
    Rectangle {
        visible: ov.v.overlay === "osk"
        width: 1240; height: oskColumn.implicitHeight + 96
        x: (1920 - width) / 2; y: (972 - height) / 2
        color: ov.root.panel
        Column {
            id: oskColumn
            x: 64; y: 48; width: 1112; spacing: 8
            Text { objectName: "oskTitle"; width: parent.width; height: 84; fontSizeMode: Text.Fit; minimumPixelSize: 32; textFormat: Text.PlainText; text: ov.v.osk.title; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 64 }
            Rectangle {
                id: oskField
                objectName: "oskField"
                z: 2                              // its menu opens over the key rows below
                width: parent.width; height: 88; color: ov.root.bar
                // Ctrl+A: the whole text is marked; the next letter, paste or Delete replaces it.
                Rectangle { visible: !!ov.v.osk.selected; x: 20; width: Math.min(oskText.contentWidth, oskText.width) + 16; height: 64; anchors.verticalCenter: parent.verticalCenter; color: ov.v.accent; opacity: 0.45 }
                Text { id: oskText; x: 28; width: parent.width - 56; elide: Text.ElideLeft; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: ov.v.osk.text; color: ov.root.textC; font.family: ov.root.mono; font.weight: Font.Medium; font.pixelSize: 48 }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 4; color: ov.v.accent }
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
                                width: oskMenuColumn.width; height: 64
                                color: menuHover.hovered ? ov.root.bone : "transparent"
                                Text { x: 24; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText; text: parent.modelData === "paste" ? ov.v.osk.paste : ov.v.osk.copy; color: menuHover.hovered ? "#0E0F11" : ov.root.textC; font.family: ov.root.sans; font.weight: Font.DemiBold; font.pixelSize: 30 }
                                HoverHandler { id: menuHover }
                                TapHandler { onTapped: { oskMenu.visible = false; ov.root.backend.oskEdit(parent.modelData) } }
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
                            Text { objectName: "oskKeyLabel"; anchors.centerIn: parent; width: parent.width - 16; height: parent.height - 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; fontSizeMode: Text.Fit; minimumPixelSize: 20; textFormat: Text.PlainText; text: parent.k.label || ""; color: parent.k.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.mono; font.weight: Font.DemiBold; font.pixelSize: 30 }
                            TapHandler { onTapped: ov.root.backend.clickKey(parent.k.row, parent.k.col) }
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
        color: ov.root.panel
        Column {
            x: 48; y: 32; width: 1304
            Text { textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight; text: ov.v.picker.title; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 64 }
            Text { textFormat: Text.PlainText; width: parent.width; bottomPadding: 16; text: ov.v.picker.path; elide: Text.ElideMiddle; color: ov.root.muted; font.family: ov.root.mono; font.pixelSize: 24 }
            Text { textFormat: Text.PlainText; objectName: "pickerMessage"; width: parent.width; height: 64; text: ov.v.picker.message || ""; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; color: ov.root.textC; font.family: ov.root.sans; font.pixelSize: 26 }
            Repeater {
                model: ov.v.picker.rows.length
                Rectangle {
                    required property int index
                    readonly property var r: ov.root.ok(ov.v.picker.rows, index)
                    width: 1304; height: 60
                    color: r.focused ? ov.root.bone : "transparent"
                    Text { textFormat: Text.PlainText; x: 20; width: 160; elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter; text: parent.r.kind === "dir" ? ov.v.folder : (parent.r.kind === "pick" ? ov.v.pick : ov.v.file); color: parent.r.focused ? "#0E0F11" : ov.root.muted; font.family: ov.root.mono; font.pixelSize: 22 }
                    Text { textFormat: Text.PlainText; x: 200; width: 1080; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideMiddle; text: parent.r.name || ""; color: parent.r.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.sans; font.weight: parent.r.kind === "file" ? Font.DemiBold : Font.Normal; font.pixelSize: 30 }
                    TapHandler { onTapped: ov.root.backend.clickEntry(parent.r.index) }
                }
            }
        }
        Text { textFormat: Text.PlainText; visible: ov.v.picker.up; x: 1360; y: 130; text: "▲"; color: ov.root.muted; font.pixelSize: 18 }
        Text { textFormat: Text.PlainText; visible: ov.v.picker.down; x: 1360; y: 890; text: "▼"; color: ov.root.muted; font.pixelSize: 18 }
    }

    // ---------------------------------------------------------------- Pad bindings: "Press a button" and a conflict
    Rectangle {
        objectName: "bindCapture"
        readonly property var c: ov.v.bindCapture || ({})
        visible: ov.v.overlay === "bindcapture"
        width: 980; height: captureColumn.implicitHeight + 96
        x: (1920 - width) / 2; y: (972 - height) / 2
        color: ov.root.panel
        Rectangle { width: parent.width; height: 6; color: ov.v.accent }
        Column {
            id: captureColumn
            x: 56; y: 48; width: 868; spacing: 18
            Text { textFormat: Text.PlainText; width: parent.width; text: parent.parent.c.title || ""; wrapMode: Text.Wrap; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 72; lineHeight: 0.95 }
            Row {
                spacing: 18
                Rectangle {
                    width: Math.max(72, captureNotation.implicitWidth + 24); height: 56; radius: 6; color: ov.v.accent
                    Text { id: captureNotation; anchors.centerIn: parent; textFormat: Text.PlainText; text: ({ UP: "↑", DOWN: "↓", LEFT: "←", RIGHT: "→" })[captureColumn.parent.c.notation || ""] || captureColumn.parent.c.notation || ""; color: "#0E0F11"; font.family: ov.root.mono; font.weight: Font.Black; font.pixelSize: 30 }
                }
                Text { anchors.verticalCenter: parent.verticalCenter; width: 700; elide: Text.ElideRight; textFormat: Text.PlainText; text: captureColumn.parent.c.action || ""; color: ov.root.textC; font.family: ov.root.sans; font.weight: Font.DemiBold; font.pixelSize: 34 }
            }
            Text { width: parent.width; textFormat: Text.PlainText; text: captureColumn.parent.c.text || ""; wrapMode: Text.Wrap; color: ov.root.textC; font.family: ov.root.sans; font.pixelSize: 28 }
            // the countdown: seconds left and a bar running out
            Item {
                visible: !!captureColumn.parent.c.waiting
                width: parent.width; height: 120
                Text { objectName: "captureCountdown"; textFormat: Text.PlainText; text: captureColumn.parent.c.holding ? "…" : String(captureColumn.parent.c.left || 0); color: ov.v.accent; font.family: ov.root.display; font.weight: Font.Black; font.pixelSize: 110; anchors.verticalCenter: parent.verticalCenter }
                Rectangle {
                    x: 140; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 140; height: 14; color: "#24272C"
                    Rectangle { height: parent.height; width: parent.width * (captureColumn.parent.c.progress || 0); color: ov.v.accent }
                }
            }
            Text { visible: !!captureColumn.parent.c.waiting; width: parent.width; textFormat: Text.PlainText; text: captureColumn.parent.c.cancel || ""; wrapMode: Text.Wrap; color: captureColumn.parent.c.holding ? ov.v.accent : ov.root.muted; font.family: ov.root.sans; font.pixelSize: 24 }
            Row {
                visible: (captureColumn.parent.c.options || []).length > 0
                spacing: 12
                Repeater {
                    model: (captureColumn.parent.c.options || []).length
                    Rectangle {
                        required property int index
                        readonly property var o: ov.root.ok(captureColumn.parent.c.options, index)
                        width: (868 - 12) / 2; height: 96
                        color: o.focused ? ov.root.bone : "#24272C"
                        Text { textFormat: Text.PlainText; anchors.centerIn: parent; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter; text: parent.o.label || ""; elide: Text.ElideRight; fontSizeMode: Text.Fit; minimumPixelSize: 24; color: parent.o.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 52 }
                        TapHandler { onTapped: ov.root.backend.clickEntry(parent.index) }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- Pad bindings: choose a preset
    Rectangle {
        objectName: "ctlPreset"
        readonly property var p: ov.v.ctlPreset || ({})
        visible: ov.v.overlay === "ctlpreset"
        width: 1100; height: presetColumn.implicitHeight + 96
        x: (1920 - width) / 2; y: (972 - height) / 2
        color: ov.root.panel
        Rectangle { width: parent.width; height: 6; color: ov.v.accent }
        Column {
            id: presetColumn
            x: 48; y: 44; width: 1004; spacing: 8
            Text { textFormat: Text.PlainText; width: parent.width; bottomPadding: 10; text: presetColumn.parent.p.title || ""; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 64 }
            Repeater {
                model: (presetColumn.parent.p.rows || []).length
                Rectangle {
                    required property int index
                    readonly property var r: ov.root.ok(presetColumn.parent.p.rows, index)
                    width: presetColumn.width; height: presetText.implicitHeight + 28
                    color: r.focused ? ov.root.bone : "#1C1E23"
                    Rectangle { visible: !!parent.r.focused; width: 6; height: parent.height; color: ov.v.accent }
                    Column {
                        id: presetText
                        x: 24; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 48; spacing: 2
                        Text { width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.parent.r.label || ""; color: parent.parent.r.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.sans; font.weight: Font.DemiBold; font.pixelSize: 28 }
                        Text { width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight; textFormat: Text.PlainText; text: parent.parent.r.hint || ""; color: parent.parent.r.focused ? "#3A3D44" : ov.root.muted; font.family: ov.root.sans; font.pixelSize: 20 }
                    }
                    TapHandler { onTapped: ov.root.backend.clickEntry(parent.index) }
                }
            }
        }
    }
}
