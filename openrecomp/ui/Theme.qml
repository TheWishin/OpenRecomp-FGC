pragma Singleton
import QtQuick

QtObject {
    readonly property int titleSize: 40
    readonly property int sectionSize: 28
    readonly property int labelSize: 20
    readonly property int dataSize: 22
    readonly property int helpSize: 16
    property real textScale: 1
    property bool highContrast: false
    readonly property color ground: highContrast ? "#000000" : "#0E0F11"
    readonly property color card: highContrast ? "#080808" : "#16181C"
    readonly property color raised: highContrast ? "#161616" : "#202328"
    readonly property color highlighted: highContrast ? "#161616" : "#303640"
    readonly property color text: highContrast ? "#FFFFFF" : "#ECE9E1"
    readonly property color muted: highContrast ? "#D8D8D8" : "#A3A5AB"
    readonly property color value: highContrast ? "#FFE1BC" : "#D3B59D"
    readonly property color selected: highContrast ? "#FFFFFF" : "#F2EFE6"
    readonly property color inkHelp: highContrast ? "#292929" : "#50535A"
    readonly property color border: highContrast ? "#999999" : "#454A53"
    readonly property color focus: highContrast ? "#FFFFFF" : "#E9C5A7"
    readonly property color error: highContrast ? "#FFB8BC" : "#FF858C"
    readonly property color success: highContrast ? "#C1FFD2" : "#9AD8B9"
    readonly property int focusWidth: highContrast ? 5 : 3
    function px(size) { return Math.round(Math.max(14, size) * textScale) }
    function luminance(colour) {
        function linear(channel) { return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4) }
        return 0.2126 * linear(colour.r) + 0.7152 * linear(colour.g) + 0.0722 * linear(colour.b)
    }
    function readableAccent(raw) {
        if (highContrast || !raw) return value
        var original = Qt.lighter(raw, 1)
        var result = original
        var surface = luminance(highlighted)
        for (var step = 1; step <= 20 && (luminance(result) + 0.05) / (surface + 0.05) < 4.5; ++step) {
            var mix = step / 20
            result = Qt.rgba(original.r * (1 - mix) + mix, original.g * (1 - mix) + mix, original.b * (1 - mix) + mix, 1)
        }
        return result
    }
}
