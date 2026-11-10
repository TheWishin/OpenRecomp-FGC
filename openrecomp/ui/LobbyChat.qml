import QtQuick

Rectangle {
    id: pane
    required property var root
    property var chat: ({})
    readonly property bool expanded: chat.open !== false
    readonly property bool compact: height * Theme.viewportScale < 320
    readonly property bool compactTabs: compact && (chat.tabs || []).length > 0
    color: Theme.card; border.width: 1; border.color: Theme.border
    property var positions: ({})
    property string conversation: ""
    property int previousCount: 0
    property string previousTail: ""
    property int newCount: 0
    property bool following: true
    property int latestSerial: 0
    property string revealedMessage: ""
    function click(b) { if (b && b.index >= 0 && !b.disabled) root.backend.clickRow(b.index) }
    function updateHistory() {
        if (!visible) return
        var key = (chat.game || "") + "/" + (chat.conversation || "lobby")
        var changedConversation = key !== conversation
        var tail = (chat.lines || []).length ? chat.lines[chat.lines.length - 1].id : ""
        if (key !== conversation) {
            positions[conversation] = {y: history.contentY, following: following}
            conversation = key
            var saved = positions[key]
            following = !saved || saved.following
            history.contentY = saved ? saved.y : Math.max(0, history.contentHeight - history.height)
            previousCount = (chat.lines || []).length; previousTail = tail; newCount = 0
        } else if ((chat.lines || []).length > previousCount || tail !== previousTail) {
            if (!following) newCount += Math.max(1, (chat.lines || []).length - previousCount)
            previousCount = (chat.lines || []).length; previousTail = tail
        }
        if ((chat.latestSerial || 0) !== latestSerial) {
            latestSerial = chat.latestSerial || 0; following = true; newCount = 0
        }
        if (following) history.contentY = Math.max(0, history.contentHeight - history.height)
        for (var tabIndex = 0; tabIndex < chatTabs.count; ++tabIndex) {
            var tab = chatTabs.itemAt(tabIndex)
            if (tab && (tab.modelData.focused || tab.modelData.closeFocused || changedConversation && tab.modelData.active)) {
                if (tab.x < tabsScroll.contentX) tabsScroll.contentX = tab.x
                else if (tab.x + tab.width > tabsScroll.contentX + tabsScroll.width) tabsScroll.contentX = tab.x + tab.width - tabsScroll.width
                tabsScroll.contentX = Math.max(0, Math.min(tabsScroll.contentX, tabsScroll.contentWidth - tabsScroll.width))
            }
        }
        for (var j = 0; j < otherFields.count; ++j) {
            var field = otherFields.itemAt(j)
            if (field && field.modelData.focused) {
                if (field.y < otherViewport.contentY) otherViewport.contentY = field.y
                else if (field.y + field.height > otherViewport.contentY + otherViewport.height) otherViewport.contentY = field.y + field.height - otherViewport.height
            }
        }
        for (var i = 0; i < messages.count; ++i) {
            var row = messages.itemAt(i)
            if (row && row.modelData.focused && row.modelData.id !== revealedMessage) {
                revealedMessage = row.modelData.id
                following = false
                if (row.y < history.contentY) history.contentY = row.y
                else if (row.y + row.height > history.contentY + history.height) history.contentY = row.y + row.height - history.height
            }
        }
    }
    Connections { target: pane.root.backend; function onViewChanged() { Qt.callLater(pane.updateHistory) } }
    Text { id: title; objectName: "lobbyChatTitle"; visible: pane.expanded && !pane.compactTabs; x: 16; y: 12; width: parent.width - collapse.width - (pane.compact ? newAnchor.width + 52 : 40); text: (pane.chat.title || "") + (pane.chat.mentions ? " \u00b7 " + (pane.chat.mentionLabel || "") + " " + pane.chat.mentions : ""); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.text; font.family: pane.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.onlinePx(18) }
    ArcadeAction {
        id: collapse
        objectName: "chatDockCollapse"
        visible: pane.expanded
        root: pane.root; x: parent.width - width - 12; y: 8
        width: Theme.target(44); height: Theme.target(44)
        b: pane.chat.toggle || ({}); label: "\u203a"
        accessibleLabel: b.label || ""
        onActivated: pane.click(b)
    }
    Flickable {
        id: tabsScroll
        objectName: "chatTabsViewport"
        x: 12; y: pane.compactTabs ? 12 : title.y + Math.max(title.height, collapse.height, pane.compact ? newAnchor.height : 0) + 8; width: parent.width - (pane.compactTabs ? newAnchor.width + collapse.width + 44 : 24); height: tabs.height
        visible: pane.expanded && (pane.chat.tabs || []).length > 0; contentWidth: tabs.width; clip: true
        onContentWidthChanged: Qt.callLater(pane.updateHistory)
        onWidthChanged: Qt.callLater(pane.updateHistory)
        Row {
            id: tabs; spacing: 8
            Repeater {
                id: chatTabs; model: pane.chat.tabs || []
                Row {
                    required property var modelData
                    objectName: "chatConversationTab"
                    spacing: 4
                    ArcadeAction { root: pane.root; b: parent.modelData; label: (b.label || "") + (b.unread ? " (" + b.unread + ")" : ""); primary: !!b.active; onActivated: pane.click(b) }
                    ArcadeAction { visible: parent.modelData.closeIndex !== undefined && parent.modelData.closeIndex !== null; root: pane.root; width: Theme.target(44); label: "\u00d7"; b: ({index: parent.modelData.closeIndex, focused: parent.modelData.closeFocused}); onActivated: pane.click(b); accessibleLabel: (pane.chat.closeLabel || "") + ": " + (parent.modelData.label || "") }
                }
            }
        }
    }
    Flickable {
        id: history
        objectName: "lobbyChatHistory"
        visible: pane.expanded
        x: 12; y: tabsScroll.y + (tabsScroll.visible ? tabsScroll.height : 0) + 12
        width: parent.width - 24; height: Math.max(0, otherViewport.y - y - 8)
        clip: true; contentHeight: messageRows.height; boundsBehavior: Flickable.StopAtBounds
        onMovementStarted: pane.following = false
        onMovementEnded: { pane.following = contentY >= contentHeight - height - 8; if (pane.following) pane.newCount = 0 }
        onContentHeightChanged: Qt.callLater(pane.updateHistory)
        Column {
            id: messageRows; width: history.width; spacing: 8
            Repeater {
                id: messages; model: pane.chat.lines || []
                Rectangle {
                    id: message
                    required property var modelData
                    width: messageRows.width; height: messageText.height + 8
                    color: modelData.focused ? Theme.highlighted : "transparent"
                    border.width: modelData.focused ? Theme.focusWidth : 0; border.color: Theme.focus
                    Column {
                        id: messageText; x: 8; y: 4; width: parent.width - 16; spacing: 4
                        Text { width: parent.width; visible: !!message.modelData.name; text: message.modelData.name || ""; textFormat: Text.PlainText; color: message.modelData.own ? Theme.value : Theme.muted; font.family: pane.root.sans; font.weight: Font.DemiBold; font.pixelSize: Theme.onlinePx(14) }
                        // Plain text segments preserve arbitrary user input; no rich-text interpolation.
                        Flow {
                            width: parent.width; spacing: 0
                            Repeater {
                                model: message.modelData.segments || [{text: message.modelData.text || "", mention: false}]
                                Text { required property var modelData; width: Math.min(implicitWidth, messageText.width); wrapMode: Text.WrapAnywhere; text: modelData.text || ""; textFormat: Text.PlainText; color: modelData.mention ? Theme.value : message.modelData.system ? Theme.muted : Theme.text; font.family: pane.root.sans; font.weight: modelData.mention ? Font.Bold : Font.Normal; font.pixelSize: Theme.onlinePx(14) }
                            }
                        }
                    }
                    TapHandler { id: messageTap; onTapped: (message.modelData.selectable ? pane.root.backend.clickRow(message.modelData.index) : pane.root.backend.focusOnlineRow(message.modelData.index)) }
                    Interaction { handler: messageTap; selected: !!modelData.focused; role: Accessible.ListItem; name: [modelData.name || "", modelData.text || ""].join(". "); onActivated: (message.modelData.selectable ? pane.root.backend.clickRow(message.modelData.index) : pane.root.backend.focusOnlineRow(message.modelData.index)) }
                }
            }
        }
    }
    Flickable {
        id: otherViewport
        visible: pane.expanded && (pane.chat.other || []).length > 0
        x: 12; y: (pane.compact ? composer.y : newAnchor.y) - height - 8; width: parent.width - 24
        height: visible ? Math.min(otherRows.height, pane.height * 0.3) : 0
        contentHeight: otherRows.height; clip: true; boundsBehavior: Flickable.StopAtBounds
        Column {
            id: otherRows; width: otherViewport.width; spacing: 8
            Repeater {
                id: otherFields; model: pane.chat.other || []
                Item {
                    required property var modelData
                    width: otherRows.width; height: modelData.fieldId ? extraField.height : extraAction.height
                    EditableField { id: extraField; visible: !!parent.modelData.fieldId; root: pane.root; field: parent.modelData; width: parent.width }
                    ArcadeAction { id: extraAction; visible: !parent.modelData.fieldId; root: pane.root; b: parent.modelData; width: parent.width; onActivated: pane.click(b) }
                }
            }
        }
    }
    ArcadeAction {
        id: newAnchor
        objectName: "chatLatestAnchor"
        visible: pane.expanded
        root: pane.root; x: pane.compact ? parent.width - width - collapse.width - 20 : 12; y: pane.compact ? title.y : composer.y - height - 8; width: pane.compact ? Math.max(Theme.target(44), pane.newCount ? implicitWidth : 0) : parent.width - 24
        height: Theme.target(44); b: pane.chat.latest || ({})
        label: pane.compact ? "\u2193" + (pane.newCount ? " " + pane.newCount : "") : pane.newCount ? (pane.chat.newLabel || "") + " (" + pane.newCount + ")" : b.label || ""
        accessibleLabel: (b.label || pane.chat.newLabel || "") + (pane.newCount ? " (" + pane.newCount + ")" : "")
        onActivated: pane.click(b)
    }
    Item {
        id: composer
        objectName: "lobbyChatComposer"
        height: pane.compact ? Math.max(compose.height, send.height) : compose.height + 8 + send.height
        visible: pane.expanded
        x: 12; y: parent.height - height - 12; width: parent.width - 24
        EditableField {
            id: compose
            root: pane.root; field: pane.chat.compose || ({}); width: pane.compact ? parent.width - send.width - 8 : parent.width; showLabel: false
            placeholder: pane.chat.composePlaceholder || field.label || ""
            onCompleteRequested: (text, cursor) => {
                var prefix = text.substring(0, cursor)
                var match = /(?:^|\s)@([^@\s]*)$/.exec(prefix)
                if (!match) return
                var names = (pane.chat.completions || []).filter(name => name.toLocaleLowerCase().indexOf(match[1].toLocaleLowerCase()) === 0)
                if (!names.length) return
                var start = cursor - match[1].length
                compose.editor.remove(start, cursor)
                compose.editor.insert(start, names[0] + " ")
                pane.root.backend.editText(compose.fieldId, compose.editor.text)
            }
        }
        ArcadeAction { id: send; root: pane.root; x: pane.compact ? parent.width - width : 0; y: pane.compact ? 0 : compose.height + 8; width: pane.compact ? implicitWidth : parent.width; b: pane.chat.send || ({}); label: pane.compact ? pane.chat.sendShort || b.label || "" : b.label || ""; accessibleLabel: b.label || ""; primary: !Theme.quiet; onActivated: pane.click(b) }
    }
    ArcadeAction {
        visible: !pane.expanded
        root: pane.root; x: 8; y: 12; width: parent.width - 16; height: Theme.target(44)
        b: pane.chat.toggle || ({})
        label: String(pane.chat.unread || 0) + (pane.chat.mentions ? " @" + pane.chat.mentions : "")
        accessibleLabel: [pane.chat.title || "", pane.chat.unread || 0, pane.chat.mentionLabel || "", pane.chat.mentions || 0].join(". ")
        onActivated: pane.click(b)
    }
    Component.onCompleted: Qt.callLater(updateHistory)
    onVisibleChanged: if (visible) Qt.callLater(updateHistory)
}
