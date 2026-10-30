/* Pre-Python failure text: same seven languages as openrecomp/i18n. MIT. */
static const wchar_t *startup_failure(LANGID language) {
    switch (PRIMARYLANGID(language)) {
    case LANG_GERMAN:
        return L"OpenRecomp konnte sein privates Python nicht starten. Entpacke die vollst\u00e4ndige Launcher-ZIP erneut.";
    case LANG_SPANISH:
        return L"OpenRecomp no pudo iniciar su Python privado. Vuelve a extraer el ZIP completo del lanzador.";
    case LANG_FRENCH:
        return L"OpenRecomp n'a pas pu d\u00e9marrer son Python priv\u00e9. Extrais \u00e0 nouveau le ZIP complet du lanceur.";
    case LANG_JAPANESE:
        return L"OpenRecomp\u5c02\u7528\u306ePython\u3092\u8d77\u52d5\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\u3002\u30e9\u30f3\u30c1\u30e3\u30fc\u306eZIP\u5168\u4f53\u3092\u3082\u3046\u4e00\u5ea6\u5c55\u958b\u3057\u3066\u304f\u3060\u3055\u3044\u3002";
    case LANG_KOREAN:
        return L"OpenRecomp\uac00 \uc804\uc6a9 Python\uc744 \uc2dc\uc791\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. \ub7f0\ucc98 ZIP \uc804\uccb4\ub97c \ub2e4\uc2dc \uc555\ucd95 \ud574\uc81c\ud558\uc138\uc694.";
    case LANG_PORTUGUESE:
        return L"O OpenRecomp n\u00e3o conseguiu iniciar seu Python privado. Extraia novamente o ZIP completo do inicializador.";
    default:
        return L"OpenRecomp could not start its private Python. Extract the complete launcher zip again.";
    }
}
