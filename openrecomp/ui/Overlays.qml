import QtQuick

// Everything that opens over a screen. The prompt bar stays visible underneath (76 px at the bottom).
Item {
    id: ov
    required property var root
    readonly property var v: root.v
    visible: v.overlay !== ""

    Rectangle { x: 0; y: 0; width: 1920; height: 1080 - 76; color: "#C2000000"; TapHandler {} }

    // ---------------------------------------------------------------- dialog: the safe answer has the focus
    Rectangle {
        visible: ov.v.overlay === "dialog"
        width: 860; height: dialogColumn.implicitHeight + 112
        x: (1920 - width) / 2; y: (1004 - height) / 2
        color: ov.root.panel
        Column {
            id: dialogColumn
            x: 64; y: 56; width: 732; spacing: 16
            Text { width: parent.width; text: ov.v.dialog.title; wrapMode: Text.Wrap; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 88; lineHeight: 0.95 }
            Text { width: parent.width; text: ov.v.dialog.text; wrapMode: Text.Wrap; color: ov.root.textC; font.family: ov.root.sans; font.pixelSize: 30; bottomPadding: 24 }
            Row {
                spacing: 12
                Repeater {
                    model: ov.v.dialog.options.length
                    Rectangle {
                        required property int index
                        readonly property var o: ov.root.ok(ov.v.dialog.options, index)
                        width: 360; height: 104; color: o.focused ? ov.root.bone : "#24272C"
                        Text { anchors.centerIn: parent; text: parent.o.label || ""; color: parent.o.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 56 }
                        TapHandler { onTapped: ov.root.backend.clickEntry(parent.index) }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- the quick drawer keeps your place
    Rectangle {
        visible: ov.v.overlay === "drawer"
        x: 1920 - 780; y: 0; width: 780; height: 1004
        color: ov.root.panel
        Column {
            y: 40; width: parent.width
            Text { x: 48; text: ov.v.quickAccess; bottomPadding: 20; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 72 }
            Repeater {
                model: ov.v.drawer.rows.length
                Rectangle {
                    required property int index
                    readonly property var r: ov.root.ok(ov.v.drawer.rows, index)
                    width: 780; height: r.focused ? 92 : 76
                    color: r.focused ? ov.root.bone : "transparent"
                    Text { x: 48; anchors.verticalCenter: parent.verticalCenter; text: parent.r.label || ""; color: parent.r.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.display; font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.pixelSize: parent.r.focused ? 44 : 36 }
                    Text { anchors.right: parent.right; anchors.rightMargin: 48; anchors.verticalCenter: parent.verticalCenter; text: parent.r.value || ""; color: parent.r.focused ? "#0E0F11" : ov.root.muted; font.family: ov.root.sans; font.pixelSize: 26 }
                    TapHandler { onTapped: ov.root.backend.clickEntry(parent.index) }
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
            Text { text: ov.v.fighterTitle; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 56 }
            Text { visible: !!ov.v.grid.main; text: ov.v.fighterMain + (ov.v.grid.main || ""); color: ov.root.muted; font.family: ov.root.sans; font.pixelSize: 26; anchors.baseline: parent.children[0].baseline }
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
                    Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
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
                    Text {
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
                        Text { id: mainTag; anchors.centerIn: parent; text: ov.v.mainLabel; color: ov.root.bone; font.family: ov.root.mono; font.weight: Font.DemiBold; font.pixelSize: 16 }
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
        x: (1920 - width) / 2; y: (1004 - height) / 2
        color: ov.root.panel
        Column {
            id: oskColumn
            x: 64; y: 48; width: 1112; spacing: 8
            Text { text: ov.v.osk.title; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 64 }
            Rectangle {
                width: parent.width; height: 88; color: ov.root.bar
                Text { x: 28; anchors.verticalCenter: parent.verticalCenter; text: ov.v.osk.text; color: ov.root.textC; font.family: ov.root.mono; font.weight: Font.Medium; font.pixelSize: 48 }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 4; color: ov.v.accent }
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
                            Text { anchors.centerIn: parent; text: parent.k.label || ""; color: parent.k.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.mono; font.weight: Font.DemiBold; font.pixelSize: 30 }
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
        x: 260; y: 40; width: 1400; height: 924
        color: ov.root.panel
        Column {
            x: 48; y: 32; width: 1304
            Text { text: ov.v.picker.title; color: ov.root.textC; font.family: ov.root.display; font.weight: Font.Black; font.capitalization: Font.AllUppercase; font.pixelSize: 64 }
            Text { width: parent.width; bottomPadding: 16; text: ov.v.picker.path; elide: Text.ElideMiddle; color: ov.root.muted; font.family: ov.root.mono; font.pixelSize: 24 }
            Repeater {
                model: ov.v.picker.rows.length
                Rectangle {
                    required property int index
                    readonly property var r: ov.root.ok(ov.v.picker.rows, index)
                    width: 1304; height: 66
                    color: r.focused ? ov.root.bone : "transparent"
                    Text { x: 20; width: 110; anchors.verticalCenter: parent.verticalCenter; text: parent.r.kind === "dir" ? ov.v.folder : (parent.r.kind === "pick" ? ov.v.pick : ov.v.file); color: parent.r.focused ? "#0E0F11" : ov.root.muted; font.family: ov.root.mono; font.pixelSize: 22 }
                    Text { x: 140; width: 1140; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideMiddle; text: parent.r.name || ""; color: parent.r.focused ? "#0E0F11" : ov.root.textC; font.family: ov.root.sans; font.weight: parent.r.kind === "file" ? Font.DemiBold : Font.Normal; font.pixelSize: 30 }
                    TapHandler { onTapped: ov.root.backend.clickEntry(parent.r.index) }
                }
            }
        }
        Text { visible: ov.v.picker.up; x: 1360; y: 130; text: "▲"; color: ov.root.muted; font.pixelSize: 18 }
        Text { visible: ov.v.picker.down; x: 1360; y: 890; text: "▼"; color: ov.root.muted; font.pixelSize: 18 }
    }
}
