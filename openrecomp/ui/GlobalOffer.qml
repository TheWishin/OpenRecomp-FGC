import QtQuick

// A passive, shell-owned notification. Only explicit review owns controller input.
Item {
    id: popup
    required property var root
    readonly property var offers: root.v.globalOffers || []
    readonly property var offer: offers.filter(row => row.focused)[0] || (offers.length ? offers[0] : ({}))
    readonly property color accent: Theme.readableAccent(offer.accent || root.v.accent)
    readonly property bool fullMatchVisible: offer.kind === "match" && root.v.screen === "hub"
        && (root.v.online || {}).phase === "matched" && (root.v.matchVersus || {}).gameId === offer.game
        && !root.v.overlay && !(root.v.mainMenu || {}).show && !offer.focused
    visible: offers.length > 0 && !fullMatchVisible
    width: Math.min(1080, parent.width - 64)
    height: content.height + 32
    anchors.horizontalCenter: parent.horizontalCenter
    y: 16
    Repeater {
        model: Math.min(2, Math.max(0, popup.offers.length - 1))
        Rectangle {
            required property int index
            x: 8 * (index + 1); y: -6 * (index + 1)
            width: popup.width - x * 2; height: popup.height
            color: Theme.raised; border.color: Theme.border; radius: 6
        }
    }
    Rectangle { anchors.fill: parent; color: Theme.card; radius: 6; border.width: popup.offer.focused ? Theme.focusWidth : 2; border.color: popup.offer.focused ? Theme.focus : popup.accent }
    Rectangle { x: 0; y: 0; width: 6; height: parent.height; color: popup.accent }
    Column {
        id: content; x: 24; y: 16; width: parent.width - 48; spacing: 8
        Row {
            width: parent.width; spacing: 12
            OnlineStyle.SectionHeader { width: parent.width * .72; text: (popup.offer.gameShort || "") + " · " + (popup.offer.title || "") }
            OnlineStyle.Value { width: parent.width * .28 - 12; horizontalAlignment: Text.AlignRight; text: popup.offer.countdown || ""; Accessible.role: Accessible.StaticText }
        }
        Row {
            width: parent.width; spacing: 12
            Column {
                visible: popup.offer.kind === "match"; width: visible ? (parent.width - 80) / 2 : 0; spacing: 4
                FighterPortrait { objectName: "offerOwnPortrait"; width: 64; height: 64; source: popup.offer.selfArt || "" }
                OnlineStyle.FieldLabel { width: parent.width; text: popup.offer.selfName || "" }
                OnlineStyle.Value { width: parent.width; text: popup.offer.selfRank || "" }
            }
            OnlineStyle.PageTitle { visible: popup.offer.kind === "match"; width: visible ? 56 : 0; text: popup.offer.versus || ""; horizontalAlignment: Text.AlignHCenter }
            Column {
                width: popup.offer.kind === "match" ? (parent.width - 80) / 2 : parent.width; spacing: 4
                FighterPortrait { objectName: "offerPeerPortrait"; width: 64; height: 64; source: popup.offer.art || ""; mirrored: true }
                OnlineStyle.FieldLabel { width: parent.width; text: popup.offer.name || ""; Accessible.name: text }
                Row {
                    width: parent.width; spacing: 8
                    Image { visible: !!popup.offer.plate; source: popup.offer.plate || ""; width: visible ? 100 : 0; height: 26; fillMode: Image.PreserveAspectFit }
                    OnlineStyle.Value { width: parent.width - (popup.offer.plate ? 108 : 0); text: [popup.offer.rank || "", popup.offer.rating || ""].filter(t => t).join(" · ") }
                }
            }
        }
        PeerPing { objectName: "globalOfferPing"; connection: popup.offer.connection || ({}); ink: Theme.text; dim: Theme.border }
        OnlineStyle.HelpText { width: parent.width; text: (popup.offer.details || []).map(r => r.k + ": " + r.v).join(" · "); visible: !!text; maximumLineCount: 3; elide: Text.ElideRight }
        OnlineStyle.HelpText { width: parent.width; text: popup.offer.status || popup.offer.hint || ""; maximumLineCount: 2; elide: Text.ElideRight }
        Row {
            width: parent.width; spacing: 12
            OnlineStyle.PrimaryButton {
                objectName: "globalOfferAccept"; width: (parent.width - 24) * .45; maxW: width; height: Math.max(Theme.target(64), captionHeight + 20)
                b: ({label: popup.offer.acceptLabel || "", disabled: !!popup.offer.disabled, focused: !!popup.offer.focused})
                glyph: popup.root.v.confirmInk || ({})
                accent: popup.accent; onActivated: popup.root.backend.respondOffer(popup.offer.identity, true)
            }
            OnlineStyle.SecondaryButton {
                objectName: "globalOfferDecline"; width: (parent.width - 24) * .30; maxW: width; height: Math.max(Theme.target(64), captionHeight + 20)
                b: ({label: popup.offer.declineLabel || "", disabled: !!popup.offer.disabled})
                glyph: popup.root.v.backG || ({})
                onActivated: popup.root.backend.respondOffer(popup.offer.identity, false)
            }
            OnlineStyle.SecondaryButton {
                objectName: "globalOfferReview"; width: (parent.width - 24) * .25; maxW: width; height: Math.max(Theme.target(64), captionHeight + 20)
                b: ({label: popup.offer.reviewLabel || ""}); onActivated: popup.root.backend.press("offers")
            }
        }
    }
}
