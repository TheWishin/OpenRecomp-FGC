pragma Singleton
import QtQuick

QtObject {
    readonly property int titleSize: 40
    readonly property int sectionSize: 28
    readonly property int labelSize: 20
    readonly property int dataSize: 22
    readonly property int helpSize: 16
    property real textScale: 1
    property real viewportScale: 1
    readonly property int space: 8
    readonly property int inset: 24
    readonly property int gap: 16
    property bool highContrast: false
    // Calm (default): neutral greys for every game, the game's colour only as the one accent (focus, primary
    // action, active tab), no warm gradients, neutral ranks and values. Vivid = the 0.1.6 per-game palette.
    property bool calm: true
    readonly property bool quiet: calm && !highContrast
    property bool reducedMotion: false
    property string gameKind: ""
    readonly property color gameAccent: gameKind === "t4" ? "#71CBE5" : gameKind === "t5dr" ? (quiet ? "#C8394F" : "#D11F3F") : "#D3B59D"
    readonly property color ground: highContrast ? "#000000" : quiet ? "#0F1012" : gameKind === "t4" ? "#0D141D" : gameKind === "t5dr" ? "#100C10" : "#0E0F11"
    readonly property color card: highContrast ? "#080808" : quiet ? "#17191C" : gameKind === "t4" ? "#172330" : gameKind === "t5dr" ? "#1B1118" : "#16181C"
    readonly property color raised: highContrast ? "#161616" : quiet ? "#212327" : gameKind === "t4" ? "#233342" : gameKind === "t5dr" ? "#29171F" : "#202328"
    readonly property color highlighted: highContrast ? "#161616" : quiet ? "#2C2F35" : gameKind === "t5dr" ? "#321C25" : "#303640"
    readonly property color text: highContrast ? "#FFFFFF" : "#ECE9E1"
    readonly property color muted: highContrast ? "#D8D8D8" : "#A3A5AB"
    readonly property color value: highContrast ? "#FFE1BC" : quiet ? "#C9CBD0" : gameKind === "t4" ? "#BDD4E1" : gameKind === "t5dr" ? "#BEC3CC" : "#D3B59D"
    readonly property color rankGold: highContrast ? "#FFE1BC" : quiet ? value : gameKind === "t5dr" ? "#E5BD68" : readableAccent(gameAccent)
    readonly property color selected: highContrast ? "#FFFFFF" : "#F2EFE6"
    readonly property color inkHelp: highContrast ? "#292929" : "#50535A"
    readonly property color border: highContrast ? "#999999" : quiet ? "#3A3D44" : "#454A53"
    readonly property color focus: highContrast ? "#FFFFFF" : gameKind === "t4" ? "#CDEBF5" : gameKind === "t5dr" ? (quiet ? "#E8566A" : "#F13B56") : "#E9C5A7"
    readonly property color primaryFill: highContrast ? selected : gameKind === "t5dr" ? (quiet ? "#A3283C" : "#B51232") : readableAccent(gameAccent)
    readonly property color primaryText: highContrast ? ground : gameKind === "t5dr" ? "#FFFFFF" : ground
    readonly property color highlightStart: highContrast || quiet ? highlighted : gameKind === "t5dr" ? "#8D2F12" : highlighted
    readonly property color highlightEnd: highContrast || quiet ? highlighted : gameKind === "t5dr" ? "#870C2A" : highlighted
    // Small status marks (signal bars, badges): neutral when calm, the accent when vivid.
    readonly property color mark: quiet ? value : readableAccent(gameAccent)
    // Behind text: picture and atmosphere strength of the background (calm keeps them faint).
    readonly property real artStrength: quiet ? .3 : .58
    readonly property real atmosphereStrength: quiet ? .16 : .58
    readonly property color error: highContrast ? "#FFB8BC" : "#FF858C"
    readonly property color success: highContrast ? "#C1FFD2" : "#9AD8B9"
    readonly property int focusWidth: highContrast ? 5 : 3
    // Values are stage units. Floors are output pixels, including at 720p/540p.
    function px(size) {
        var floor = size >= 40 ? 28 : size >= 28 ? 22 : size >= 18 ? 18 : 16
        return Math.round(Math.max(size, floor / Math.max(0.5, viewportScale)) * textScale)
    }
    readonly property real listRowHeight: Math.max(88, px(22) * 1.3 + px(16) * 1.3 + 22)
    // Online tables have their own density; the game shelf keeps its existing scale.
    function onlinePx(size) { return Math.round(Math.max(size, 14 / Math.max(0.5, viewportScale)) * textScale) }
    readonly property real playerRowHeight: Math.max(32, onlinePx(14) * 1.25 + 8)
    function target(size) { return Math.max(size || 44, 44 / Math.max(0.5, viewportScale)) }
    function luminance(colour) {
        function linear(channel) { return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4) }
        return 0.2126 * linear(colour.r) + 0.7152 * linear(colour.g) + 0.0722 * linear(colour.b)
    }
    function readableAccent(raw) {
        if (highContrast || !raw) return value
        var original = Qt.lighter(raw, 1)
        var result = original
        // the lighter of the two palettes' selected surfaces (calm #2C2F35, vivid #303640): one accent tone for both
        var surface = Math.max(luminance(highlighted), luminance(Qt.color("#303640")))
        for (var step = 1; step <= 20 && (luminance(result) + 0.05) / (surface + 0.05) < 4.5; ++step) {
            var mix = step / 20
            result = Qt.rgba(original.r * (1 - mix) + mix, original.g * (1 - mix) + mix, original.b * (1 - mix) + mix, 1)
        }
        return result
    }
}
