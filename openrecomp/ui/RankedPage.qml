import QtQuick

Item {
    id: page
    required property var root
    readonly property var ranked: root.v.online.ranked || ({})
    readonly property var labels: ranked.labels || ({})
    readonly property var profile: ranked.profile || ({})
    readonly property var find: ranked.find || ({})
    OnlineStyle.HelpText { id: season; width: parent.width; text: page.ranked.season || ""; font.weight: Font.DemiBold }
    OnlineStyle.PageTitle { id: title; y: season.height + 8; width: parent.width; text: page.labels.ranked || "" }
    OnlineStyle.SectionCard {
        visible: page.ranked.available === false
        x: 0; y: title.y + title.height + 22; width: parent.width; height: unavailable.height + 48
        OnlineStyle.FieldLabel { id: unavailable; x: 24; y: 24; width: parent.width - 48; text: page.labels.unavailable || "" }
    }
    Row {
        visible: page.ranked.available !== false
        x: 0; y: title.y + title.height + 22; width: parent.width; height: parent.height - y; spacing: 18
        OnlineStyle.SectionCard {
            width: (parent.width - 18) * 0.52; height: parent.height
            Flickable {
                anchors.fill: parent; anchors.margins: 26; clip: true; contentHeight: standing.height
                Column {
                    id: standing; width: parent.width; spacing: 18
                    OnlineStyle.HelpText { width: parent.width; text: page.labels.standing || "" }
                    Image { visible: !!page.profile.plate; source: page.profile.plate || ""; width: parent.width; height: 110; fillMode: Image.PreserveAspectFit; asynchronous: true }
                    OnlineStyle.PageTitle { width: parent.width; text: page.profile.rank || "—" }
                    OnlineStyle.FieldLabel { width: parent.width; text: page.profile.name || "" }
                    OnlineStyle.HelpText { width: parent.width; text: page.labels.rating || "" }
                    OnlineStyle.PageTitle { width: parent.width; text: page.ranked.rating || "—"; font.pixelSize: Theme.px(Theme.titleSize * 1.6) }
                    OnlineStyle.Value { width: parent.width; text: (page.profile.rows || []).slice(1).join(" · "); visible: !!text }
                    Column {
                        width: parent.width; spacing: 10; visible: (page.profile.progress === undefined ? -1 : page.profile.progress) >= 0
                        OnlineStyle.FieldLabel { width: parent.width; text: page.ranked.placement ? page.labels.placement || "" : page.labels.progress || "" }
                        Rectangle {
                            width: parent.width; height: 14; radius: 7; color: "#393F47"
                            Rectangle { width: parent.width * Math.max(0, Math.min(1, page.profile.progress || 0)); height: parent.height; radius: 7; color: Theme.readableAccent(page.root.v.accent) }
                        }
                        OnlineStyle.HelpText { width: parent.width; text: page.profile.progressText || "" }
                    }
                    OnlineStyle.HelpText { width: parent.width; text: (page.profile.conn || []).join(" · ") }
                }
            }
        }
        Flickable {
            id: optionsScroll
            width: (parent.width - 18) * 0.48; height: parent.height; contentHeight: actions.height; clip: true
            function revealFocus() {
                function focused(item) {
                    if (item.b && item.b.focused && item.visible) return item
                    for (var child of item.children || []) {
                        var found = focused(child)
                        if (found) return found
                    }
                    return null
                }
                var target = focused(actions)
                if (!target) return
                var top = target.mapToItem(actions, 0, 0).y
                if (top < contentY) contentY = top
                else if (top + target.height > contentY + height) contentY = top + target.height - height
            }
            Connections { target: page.root.backend; function onViewChanged() { Qt.callLater(optionsScroll.revealFocus) } }
            Column {
                id: actions; width: parent.width; spacing: 18
                OnlineStyle.SectionCard {
                    width: parent.width; height: searchContent.height + 40
                    Column {
                        id: searchContent; x: 20; y: 20; width: parent.width - 40; spacing: 12
                        OnlineStyle.PrimaryButton { width: parent.width; maxW: width; b: page.find.ranked || ({}); accent: Theme.readableAccent(page.root.v.accent); onActivated: i => page.root.backend.clickRow(i) }
                        OnlineStyle.HelpText { width: parent.width; text: page.find.ranked && page.find.ranked.disabled ? page.find.ranked.value || "" : page.find.rankedNote || "" }
                        OnlineStyle.SecondaryButton {
                            b: page.find.optionsToggle || ({}); maxW: parent.width
                            onActivated: i => page.root.backend.clickRow(i)
                        }
                        Repeater {
                            model: page.find.groups || []
                            Column {
                                required property var modelData; width: searchContent.width; spacing: 8
                                OnlineStyle.HelpText { width: parent.width; text: parent.modelData.label || "" }
                                Flow {
                                    width: parent.width; spacing: 8
                                    Repeater {
                                        model: parent.parent.modelData.options || []
                                        OnlineStyle.Chip {
                                            required property var modelData; b: modelData; maxW: searchContent.width
                                            onActivated: i => page.root.backend.clickRow(i)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                OnlineStyle.SectionCard {
                    width: parent.width; height: results.height + 40
                    Column {
                        id: results; x: 20; y: 20; width: parent.width - 40; spacing: 12
                        OnlineStyle.SectionHeader { width: parent.width; text: page.labels.recent || "" }
                        OnlineStyle.HelpText { width: parent.width; visible: !(page.ranked.recent || []).length; text: page.labels.no_recent || "" }
                        Repeater {
                            model: page.ranked.recent || []
                            Rectangle {
                                required property var modelData; width: results.width; height: resultText.height + 22; color: "#202328"; radius: 4
                                OnlineStyle.FieldLabel { id: resultText; x: 12; y: 11; width: parent.width - 24; text: parent.modelData.result + " · " + parent.modelData.opponent + (parent.modelData.score ? " · " + parent.modelData.score : "") }
                            }
                        }
                    }
                }
            }
        }
    }
}
