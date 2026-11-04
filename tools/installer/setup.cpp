// OpenRecomp-FGC Setup and Uninstall (MIT). One source, two programs (tools/make_installer.py builds both):
//   Setup:     this program with an RCDATA resource "PAYLOAD" (the launcher's files, see make_installer.py).
//   Uninstall: the same program without it; Setup writes it into the install folder.
// Per-user only: files go to a folder the player can write to (default %LOCALAPPDATA%\Programs\OpenRecomp),
// shortcuts to the player's Start menu / desktop, the Apps & Features entry to HKEY_CURRENT_USER. No
// administrator rights, no service, no driver, no packer, nothing downloaded. Player data is never in the
// install folder: OpenRecomp-FGC keeps its settings in %LOCALAPPDATA%\OpenRecomp (OPENRECOMP_HOME), and games
// (T4, T5DR-Online-*) are left alone by an update and by the uninstall.
//
// Command line (Setup):     /S  /D=<folder>  /desktop  /nodesktop  /nostart  /lang=<en|de|es|fr|ja|ko|pt>  /log=<file>
// Command line (Uninstall): /S  /removesettings  /keepsettings  /lang=..  /log=<file>
// A full Setup (bundled games) also takes  /games=t5dr,t4  /nogames  (default: every game it carries).
// Exit codes: 0 done, 1 cancelled, 2 failed, 3 OpenRecomp-FGC still running (silent mode),
//             4 the launcher is installed but a bundled game is not (silent mode; the log says why).
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <propkey.h>
#include <propvarutil.h>
#include <commctrl.h>
#include <tlhelp32.h>
#include <bcrypt.h>
#include <compressapi.h>
#include <string>
#include <vector>
#include <set>
#include <algorithm>
#include <cstdio>
#include <cstdint>
#include <cwchar>

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "propsys.lib")
#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "cabinet.lib")
#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")

static const wchar_t *APP_NAME = L"OpenRecomp-FGC";
static const wchar_t *APP_FOLDER = L"OpenRecomp-FGC";          // the launcher inside the install folder
static const wchar_t *UNINSTALL_EXE = L"Uninstall OpenRecomp.exe";
static const wchar_t *MANIFEST = L"OpenRecomp-install.txt";
static const wchar_t *UNINSTALL_KEY = L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\OpenRecomp-FGC";
static const wchar_t *OWN_KEY = L"Software\\OpenRecomp-FGC\\Setup";
static const wchar_t *APP_ID = L"TheWishin.OpenRecompFGC";    // the launcher's AppUserModelID (openrecomp/app.py)
static const wchar_t *LINK_NAME = L"OpenRecomp-FGC.lnk";

// ------------------------------------------------------------------------------------------------ texts
enum Text {
    T_SETUP_TITLE, T_INTRO, T_UPDATE_INTRO, T_FOLDER, T_CHANGE, T_DESKTOP, T_START_AFTER, T_INSTALL, T_UPDATE,
    T_CANCEL, T_CLOSE, T_SPACE, T_NO_SPACE, T_NOT_WRITABLE, T_BAD_FOLDER, T_RUNNING, T_EXTRACTING, T_COPYING,
    T_SHORTCUTS, T_DONE, T_UPDATED, T_FAILED, T_DAMAGED, T_ALREADY_HERE, T_PICK_TITLE, T_UNINSTALL_TITLE,
    T_UNINSTALL_ASK, T_SETTINGS_ASK, T_REMOVED, T_KEPT, T_NOT_INSTALLED, T_CANCEL_ASK,
    T_GAMES, T_GAME_T5DR, T_GAME_T4, T_GAME_INSTALLING, T_GAMES_NOT_RUN, T_COUNT
};

struct Language { const wchar_t *code; const wchar_t *text[T_COUNT]; };

// %1 = version, %2 = folder or sizes as each text says. Plain words, no jargon: players read these.
static const Language LANGUAGES[] = {
    {L"en", {
        L"OpenRecomp-FGC %1 Setup",
        L"OpenRecomp-FGC is installed for your Windows user only. No administrator rights are needed. It contains no game data: you build each game from your own copy.",
        L"OpenRecomp-FGC is already installed here. Setup updates it to %1. Your settings, games, builds and saves stay.",
        L"Install folder (the launcher goes into its OpenRecomp-FGC folder; games you add later can go here too):",
        L"Change...",
        L"Desktop shortcut",
        L"Start OpenRecomp-FGC when done",
        L"Install",
        L"Update",
        L"Cancel",
        L"Close",
        L"Needs %1 MB. Free on this drive: %2 MB.",
        L"Not enough free space: Setup needs %1 MB, this drive has %2 MB free. Choose another drive or folder.",
        L"Setup cannot write to this folder (Windows asks for administrator rights there). Choose a folder in your user folder or on another drive.",
        L"Choose a folder on a drive of this PC (for example D:\\Games\\OpenRecomp). Windows and OpenRecomp's own settings folder cannot be used.",
        L"OpenRecomp-FGC is still running from this folder. Close it (and any game started from it), then press Retry.",
        L"Unpacking and checking the files...",
        L"Copying the files...",
        L"Creating the shortcuts...",
        L"OpenRecomp-FGC %1 is installed. Start it from the Start menu.",
        L"OpenRecomp-FGC was updated to %1. Your settings and games were kept.",
        L"Setup could not finish: %1",
        L"The setup file is damaged (a file failed its check). Download it again.",
        L"OpenRecomp-FGC is already installed in this folder. To move it, uninstall it first (Settings > Apps).",
        L"Where should OpenRecomp-FGC go?",
        L"Uninstall OpenRecomp-FGC",
        L"Remove OpenRecomp-FGC from %1?\n\nYour games (T4, T5DR-Online folders), builds and saves are not touched.",
        L"Also remove OpenRecomp-FGC's own settings (preferences, pictures from your builds, saved logins)?\n\n%1\n\nGame saves in that folder are kept either way.",
        L"OpenRecomp-FGC was removed.",
        L"These stay in %1 (your games or files that were not installed by Setup):",
        L"OpenRecomp-FGC is not installed in this folder (no OpenRecomp-install.txt).",
        L"Stop the setup?",
        L"Also install these games (their signed releases are inside this Setup and are checked first):",
        L"Tekken 5 Dark Resurrection Online %1 (you build it from your own package + license)",
        L"Tekken 4 %1, beta (you build it from your own disc image)",
        L"Installing %1... %2 %",
        L"The games could not be installed. Start the launcher and install them there (Install or choose folder).",
    }},
    {L"de", {
        L"OpenRecomp-FGC %1 Setup",
        L"OpenRecomp-FGC wird nur für deinen Windows-Benutzer installiert. Administratorrechte sind nicht nötig. Es enthält keine Spieldaten: jedes Spiel baust du aus deiner eigenen Kopie.",
        L"OpenRecomp-FGC ist hier schon installiert. Setup aktualisiert es auf %1. Deine Einstellungen, Spiele, Builds und Spielstände bleiben.",
        L"Installationsordner (der Launcher kommt in den Unterordner OpenRecomp-FGC; Spiele kannst du später auch hier ablegen):",
        L"Ändern...",
        L"Verknüpfung auf dem Desktop",
        L"OpenRecomp-FGC danach starten",
        L"Installieren",
        L"Aktualisieren",
        L"Abbrechen",
        L"Schließen",
        L"Braucht %1 MB. Frei auf diesem Laufwerk: %2 MB.",
        L"Nicht genug Platz: Setup braucht %1 MB, auf diesem Laufwerk sind %2 MB frei. Wähle ein anderes Laufwerk oder einen anderen Ordner.",
        L"Setup kann in diesen Ordner nicht schreiben (Windows verlangt dort Administratorrechte). Wähle einen Ordner in deinem Benutzerordner oder auf einem anderen Laufwerk.",
        L"Wähle einen Ordner auf einem Laufwerk dieses PCs (zum Beispiel D:\\Spiele\\OpenRecomp). Windows und der Einstellungsordner von OpenRecomp gehen nicht.",
        L"OpenRecomp-FGC läuft noch aus diesem Ordner. Schließe es (und jedes daraus gestartete Spiel) und drücke dann Wiederholen.",
        L"Dateien werden entpackt und geprüft...",
        L"Dateien werden kopiert...",
        L"Verknüpfungen werden angelegt...",
        L"OpenRecomp-FGC %1 ist installiert. Starte es über das Startmenü.",
        L"OpenRecomp-FGC wurde auf %1 aktualisiert. Deine Einstellungen und Spiele sind geblieben.",
        L"Setup konnte nicht fertig werden: %1",
        L"Die Setup-Datei ist beschädigt (eine Datei hat die Prüfung nicht bestanden). Lade sie neu herunter.",
        L"OpenRecomp-FGC ist schon in diesem Ordner installiert. Zum Verschieben erst deinstallieren (Einstellungen > Apps).",
        L"Wohin soll OpenRecomp-FGC?",
        L"OpenRecomp-FGC deinstallieren",
        L"OpenRecomp-FGC aus %1 entfernen?\n\nDeine Spiele (Ordner T4, T5DR-Online), Builds und Spielstände werden nicht angerührt.",
        L"Auch die eigenen Einstellungen von OpenRecomp-FGC entfernen (Vorlieben, Bilder aus deinen Builds, gespeicherte Anmeldungen)?\n\n%1\n\nSpielstände in diesem Ordner bleiben in jedem Fall.",
        L"OpenRecomp-FGC wurde entfernt.",
        L"Das bleibt in %1 (deine Spiele oder Dateien, die Setup nicht installiert hat):",
        L"OpenRecomp-FGC ist in diesem Ordner nicht installiert (keine OpenRecomp-install.txt).",
        L"Setup abbrechen?",
        L"Diese Spiele auch installieren (ihre signierten Releases sind in diesem Setup und werden vorher geprüft):",
        L"Tekken 5 Dark Resurrection Online %1 (du baust es aus deinem eigenen Paket + Lizenz)",
        L"Tekken 4 %1, Beta (du baust es aus deinem eigenen Disc-Image)",
        L"%1 wird installiert... %2 %",
        L"Die Spiele konnten nicht installiert werden. Starte den Launcher und installiere sie dort (Installieren oder Ordner wählen).",
    }},
    {L"es", {
        L"Instalación de OpenRecomp-FGC %1",
        L"OpenRecomp-FGC se instala solo para tu usuario de Windows. No hacen falta permisos de administrador. No contiene datos de juegos: cada juego lo compilas desde tu propia copia.",
        L"OpenRecomp-FGC ya está instalado aquí. La instalación lo actualiza a %1. Tus ajustes, juegos, compilaciones y partidas guardadas se conservan.",
        L"Carpeta de instalación (el launcher va en su carpeta OpenRecomp-FGC; los juegos que añadas también pueden ir aquí):",
        L"Cambiar...",
        L"Acceso directo en el escritorio",
        L"Iniciar OpenRecomp-FGC al terminar",
        L"Instalar",
        L"Actualizar",
        L"Cancelar",
        L"Cerrar",
        L"Necesita %1 MB. Libre en esta unidad: %2 MB.",
        L"No hay espacio suficiente: se necesitan %1 MB y esta unidad tiene %2 MB libres. Elige otra unidad o carpeta.",
        L"No se puede escribir en esta carpeta (Windows pide permisos de administrador). Elige una carpeta de tu usuario o de otra unidad.",
        L"Elige una carpeta en una unidad de este PC (por ejemplo D:\\Juegos\\OpenRecomp). No se pueden usar Windows ni la carpeta de ajustes de OpenRecomp.",
        L"OpenRecomp-FGC sigue abierto desde esta carpeta. Ciérralo (y cualquier juego iniciado desde él) y pulsa Reintentar.",
        L"Descomprimiendo y comprobando los archivos...",
        L"Copiando los archivos...",
        L"Creando los accesos directos...",
        L"OpenRecomp-FGC %1 está instalado. Ábrelo desde el menú Inicio.",
        L"OpenRecomp-FGC se actualizó a %1. Tus ajustes y juegos se conservaron.",
        L"La instalación no pudo terminar: %1",
        L"El archivo de instalación está dañado (un archivo no pasó la comprobación). Descárgalo de nuevo.",
        L"OpenRecomp-FGC ya está instalado en esta carpeta. Para moverlo, desinstálalo primero (Configuración > Aplicaciones).",
        L"¿Dónde se instala OpenRecomp-FGC?",
        L"Desinstalar OpenRecomp-FGC",
        L"¿Quitar OpenRecomp-FGC de %1?\n\nTus juegos (carpetas T4, T5DR-Online), compilaciones y partidas guardadas no se tocan.",
        L"¿Quitar también los ajustes propios de OpenRecomp-FGC (preferencias, imágenes de tus compilaciones, inicios de sesión guardados)?\n\n%1\n\nLas partidas guardadas de esa carpeta se conservan siempre.",
        L"OpenRecomp-FGC se ha quitado.",
        L"Esto se queda en %1 (tus juegos o archivos que no instaló la instalación):",
        L"OpenRecomp-FGC no está instalado en esta carpeta (falta OpenRecomp-install.txt).",
        L"¿Detener la instalación?",
        L"Instalar también estos juegos (sus versiones firmadas vienen en este instalador y se comprueban antes):",
        L"Tekken 5 Dark Resurrection Online %1 (lo compilas con tu propio paquete + licencia)",
        L"Tekken 4 %1, beta (lo compilas con tu propia imagen de disco)",
        L"Instalando %1... %2 %",
        L"No se pudieron instalar los juegos. Abre el lanzador e instálalos allí (Instalar o elegir carpeta).",
    }},
    {L"fr", {
        L"Installation d'OpenRecomp-FGC %1",
        L"OpenRecomp-FGC est installé pour ton utilisateur Windows uniquement. Aucun droit administrateur n'est nécessaire. Il ne contient aucune donnée de jeu : chaque jeu est compilé à partir de ta propre copie.",
        L"OpenRecomp-FGC est déjà installé ici. L'installation le met à jour vers %1. Tes réglages, jeux, compilations et sauvegardes sont conservés.",
        L"Dossier d'installation (le launcher va dans son dossier OpenRecomp-FGC ; les jeux ajoutés plus tard peuvent aussi aller ici) :",
        L"Modifier...",
        L"Raccourci sur le bureau",
        L"Lancer OpenRecomp-FGC à la fin",
        L"Installer",
        L"Mettre à jour",
        L"Annuler",
        L"Fermer",
        L"Nécessite %1 Mo. Libre sur ce disque : %2 Mo.",
        L"Pas assez d'espace : il faut %1 Mo et ce disque a %2 Mo libres. Choisis un autre disque ou dossier.",
        L"Impossible d'écrire dans ce dossier (Windows y demande des droits administrateur). Choisis un dossier de ton profil ou d'un autre disque.",
        L"Choisis un dossier sur un disque de ce PC (par exemple D:\\Jeux\\OpenRecomp). Windows et le dossier de réglages d'OpenRecomp ne conviennent pas.",
        L"OpenRecomp-FGC tourne encore depuis ce dossier. Ferme-le (et tout jeu lancé depuis lui), puis appuie sur Réessayer.",
        L"Décompression et vérification des fichiers...",
        L"Copie des fichiers...",
        L"Création des raccourcis...",
        L"OpenRecomp-FGC %1 est installé. Lance-le depuis le menu Démarrer.",
        L"OpenRecomp-FGC a été mis à jour vers %1. Tes réglages et jeux sont conservés.",
        L"L'installation n'a pas pu se terminer : %1",
        L"Le fichier d'installation est endommagé (un fichier n'a pas passé la vérification). Télécharge-le à nouveau.",
        L"OpenRecomp-FGC est déjà installé dans ce dossier. Pour le déplacer, désinstalle-le d'abord (Paramètres > Applications).",
        L"Où installer OpenRecomp-FGC ?",
        L"Désinstaller OpenRecomp-FGC",
        L"Retirer OpenRecomp-FGC de %1 ?\n\nTes jeux (dossiers T4, T5DR-Online), compilations et sauvegardes ne sont pas touchés.",
        L"Retirer aussi les réglages propres d'OpenRecomp-FGC (préférences, images de tes compilations, connexions enregistrées) ?\n\n%1\n\nLes sauvegardes de jeu de ce dossier sont conservées dans tous les cas.",
        L"OpenRecomp-FGC a été retiré.",
        L"Ceci reste dans %1 (tes jeux ou des fichiers non installés par l'installation) :",
        L"OpenRecomp-FGC n'est pas installé dans ce dossier (pas de OpenRecomp-install.txt).",
        L"Arrêter l'installation ?",
        L"Installer aussi ces jeux (leurs versions signées sont dans ce programme d'installation et vérifiées d'abord) :",
        L"Tekken 5 Dark Resurrection Online %1 (tu le compiles avec ton propre paquet + licence)",
        L"Tekken 4 %1, bêta (tu le compiles avec ta propre image disque)",
        L"Installation de %1... %2 %",
        L"Les jeux n'ont pas pu être installés. Lance le lanceur et installe-les là (Installer ou choisir un dossier).",
    }},
    {L"ja", {
        L"OpenRecomp-FGC %1 セットアップ",
        L"OpenRecomp-FGC はこの Windows ユーザーだけにインストールされます。管理者権限は不要です。ゲームデータは含まれていません。各ゲームは自分のソフトからビルドします。",
        L"OpenRecomp-FGC はすでにここにインストールされています。%1 に更新します。設定、ゲーム、ビルド、セーブデータはそのまま残ります。",
        L"インストール先フォルダー（ランチャーは OpenRecomp-FGC フォルダーに入ります。後で追加するゲームもここに置けます）:",
        L"変更...",
        L"デスクトップにショートカット",
        L"完了後に OpenRecomp-FGC を起動",
        L"インストール",
        L"更新",
        L"キャンセル",
        L"閉じる",
        L"必要: %1 MB。このドライブの空き: %2 MB。",
        L"空き容量が足りません。%1 MB 必要ですが、このドライブの空きは %2 MB です。別のドライブかフォルダーを選んでください。",
        L"このフォルダーには書き込めません（管理者権限が必要な場所です）。ユーザーフォルダー内か別のドライブのフォルダーを選んでください。",
        L"この PC のドライブ上のフォルダーを選んでください（例: D:\\Games\\OpenRecomp）。Windows と OpenRecomp の設定フォルダーは使えません。",
        L"OpenRecomp-FGC がこのフォルダーからまだ実行中です。終了して（起動したゲームも）から「再試行」を押してください。",
        L"ファイルを展開して確認しています...",
        L"ファイルをコピーしています...",
        L"ショートカットを作成しています...",
        L"OpenRecomp-FGC %1 をインストールしました。スタートメニューから起動できます。",
        L"OpenRecomp-FGC を %1 に更新しました。設定とゲームはそのままです。",
        L"セットアップを完了できませんでした: %1",
        L"セットアップファイルが壊れています（確認に失敗したファイルがあります）。もう一度ダウンロードしてください。",
        L"OpenRecomp-FGC はすでにこのフォルダーにインストールされています。移動するには先にアンインストールしてください（設定 > アプリ）。",
        L"OpenRecomp-FGC のインストール先",
        L"OpenRecomp-FGC のアンインストール",
        L"%1 から OpenRecomp-FGC を削除しますか？\n\nゲーム（T4、T5DR-Online フォルダー）、ビルド、セーブデータには触れません。",
        L"OpenRecomp-FGC 自体の設定（環境設定、ビルドから作った画像、保存されたログイン）も削除しますか？\n\n%1\n\nこのフォルダー内のゲームのセーブデータはどちらの場合も残ります。",
        L"OpenRecomp-FGC を削除しました。",
        L"%1 に残るもの（ゲーム、またはセットアップがインストールしていないファイル）:",
        L"このフォルダーには OpenRecomp-FGC がインストールされていません（OpenRecomp-install.txt がありません）。",
        L"セットアップを中止しますか？",
        L"次のゲームも一緒にインストールする (署名付きリリースがこのセットアップに含まれ、先に確認されます):",
        L"Tekken 5 Dark Resurrection Online %1 (自分のパッケージ + ライセンスからビルド)",
        L"Tekken 4 %1、ベータ (自分のディスクイメージからビルド)",
        L"%1 をインストールしています... %2 %",
        L"ゲームをインストールできませんでした。ランチャーを起動してそこでインストールしてください (インストールまたはフォルダーを選択)。",
    }},
    {L"ko", {
        L"OpenRecomp-FGC %1 설치",
        L"OpenRecomp-FGC는 이 Windows 사용자에게만 설치됩니다. 관리자 권한이 필요 없습니다. 게임 데이터는 들어 있지 않으며, 각 게임은 본인의 사본으로 빌드합니다.",
        L"OpenRecomp-FGC가 이미 여기에 설치되어 있습니다. %1(으)로 업데이트합니다. 설정, 게임, 빌드, 저장 데이터는 그대로 남습니다.",
        L"설치 폴더 (런처는 OpenRecomp-FGC 폴더에 들어가며, 나중에 추가하는 게임도 여기에 둘 수 있습니다):",
        L"변경...",
        L"바탕 화면 바로 가기",
        L"완료 후 OpenRecomp-FGC 실행",
        L"설치",
        L"업데이트",
        L"취소",
        L"닫기",
        L"필요: %1 MB. 이 드라이브 여유 공간: %2 MB.",
        L"공간이 부족합니다. %1 MB가 필요하지만 이 드라이브에는 %2 MB만 남아 있습니다. 다른 드라이브나 폴더를 선택하세요.",
        L"이 폴더에 쓸 수 없습니다 (관리자 권한이 필요한 위치입니다). 사용자 폴더 안이나 다른 드라이브의 폴더를 선택하세요.",
        L"이 PC 드라이브의 폴더를 선택하세요 (예: D:\\Games\\OpenRecomp). Windows 폴더와 OpenRecomp 설정 폴더는 사용할 수 없습니다.",
        L"OpenRecomp-FGC가 아직 이 폴더에서 실행 중입니다. 종료한 뒤 (실행한 게임도) 다시 시도를 누르세요.",
        L"파일을 풀고 확인하는 중...",
        L"파일을 복사하는 중...",
        L"바로 가기를 만드는 중...",
        L"OpenRecomp-FGC %1 설치가 끝났습니다. 시작 메뉴에서 실행하세요.",
        L"OpenRecomp-FGC가 %1(으)로 업데이트되었습니다. 설정과 게임은 그대로입니다.",
        L"설치를 마치지 못했습니다: %1",
        L"설치 파일이 손상되었습니다 (확인에 실패한 파일이 있습니다). 다시 다운로드하세요.",
        L"OpenRecomp-FGC가 이미 이 폴더에 설치되어 있습니다. 옮기려면 먼저 제거하세요 (설정 > 앱).",
        L"OpenRecomp-FGC를 설치할 위치",
        L"OpenRecomp-FGC 제거",
        L"%1에서 OpenRecomp-FGC를 제거할까요?\n\n게임 (T4, T5DR-Online 폴더), 빌드, 저장 데이터는 건드리지 않습니다.",
        L"OpenRecomp-FGC 자체 설정 (환경 설정, 빌드에서 만든 그림, 저장된 로그인)도 제거할까요?\n\n%1\n\n그 폴더의 게임 저장 데이터는 어느 쪽이든 남습니다.",
        L"OpenRecomp-FGC를 제거했습니다.",
        L"%1에 남는 항목 (게임 또는 설치 프로그램이 설치하지 않은 파일):",
        L"이 폴더에는 OpenRecomp-FGC가 설치되어 있지 않습니다 (OpenRecomp-install.txt 없음).",
        L"설치를 중단할까요?",
        L"이 게임도 함께 설치 (서명된 릴리스가 이 설치 프로그램에 들어 있고 먼저 확인합니다):",
        L"Tekken 5 Dark Resurrection Online %1 (자신의 패키지 + 라이선스로 빌드)",
        L"Tekken 4 %1, 베타 (자신의 디스크 이미지로 빌드)",
        L"%1 설치 중... %2 %",
        L"게임을 설치하지 못했습니다. 런처를 시작해 거기서 설치하세요 (설치 또는 폴더 선택).",
    }},
    {L"pt", {
        L"Instalação do OpenRecomp-FGC %1",
        L"O OpenRecomp-FGC é instalado só para o seu usuário do Windows. Não precisa de permissão de administrador. Não contém dados de jogos: cada jogo é compilado a partir da sua própria cópia.",
        L"O OpenRecomp-FGC já está instalado aqui. A instalação o atualiza para %1. Suas configurações, jogos, compilações e saves continuam.",
        L"Pasta de instalação (o launcher vai na pasta OpenRecomp-FGC; jogos que você adicionar depois também podem ficar aqui):",
        L"Alterar...",
        L"Atalho na área de trabalho",
        L"Abrir o OpenRecomp-FGC ao terminar",
        L"Instalar",
        L"Atualizar",
        L"Cancelar",
        L"Fechar",
        L"Precisa de %1 MB. Livre nesta unidade: %2 MB.",
        L"Espaço insuficiente: são necessários %1 MB e esta unidade tem %2 MB livres. Escolha outra unidade ou pasta.",
        L"Não é possível gravar nesta pasta (o Windows pede permissão de administrador). Escolha uma pasta do seu usuário ou de outra unidade.",
        L"Escolha uma pasta em uma unidade deste PC (por exemplo D:\\Jogos\\OpenRecomp). O Windows e a pasta de configurações do OpenRecomp não podem ser usados.",
        L"O OpenRecomp-FGC ainda está aberto a partir desta pasta. Feche-o (e qualquer jogo aberto por ele) e clique em Repetir.",
        L"Descompactando e verificando os arquivos...",
        L"Copiando os arquivos...",
        L"Criando os atalhos...",
        L"O OpenRecomp-FGC %1 está instalado. Abra-o pelo menu Iniciar.",
        L"O OpenRecomp-FGC foi atualizado para %1. Suas configurações e jogos foram mantidos.",
        L"A instalação não pôde terminar: %1",
        L"O arquivo de instalação está danificado (um arquivo falhou na verificação). Baixe-o novamente.",
        L"O OpenRecomp-FGC já está instalado nesta pasta. Para movê-lo, desinstale-o primeiro (Configurações > Aplicativos).",
        L"Onde instalar o OpenRecomp-FGC?",
        L"Desinstalar o OpenRecomp-FGC",
        L"Remover o OpenRecomp-FGC de %1?\n\nSeus jogos (pastas T4, T5DR-Online), compilações e saves não são tocados.",
        L"Remover também as configurações do próprio OpenRecomp-FGC (preferências, imagens das suas compilações, logins salvos)?\n\n%1\n\nOs saves de jogos nessa pasta são mantidos de qualquer forma.",
        L"O OpenRecomp-FGC foi removido.",
        L"Isto fica em %1 (seus jogos ou arquivos que a instalação não colocou):",
        L"O OpenRecomp-FGC não está instalado nesta pasta (falta OpenRecomp-install.txt).",
        L"Parar a instalação?",
        L"Instalar também estes jogos (as versões assinadas estão neste instalador e são verificadas antes):",
        L"Tekken 5 Dark Resurrection Online %1 (você compila com seu próprio pacote + licença)",
        L"Tekken 4 %1, beta (você compila com sua própria imagem de disco)",
        L"Instalando %1... %2 %",
        L"Não foi possível instalar os jogos. Abra o launcher e instale-os lá (Instalar ou escolher pasta).",
    }},
};

static const Language *g_lang = &LANGUAGES[0];

static void pick_language(const std::wstring &forced) {
    std::wstring code = forced;
    if (code.empty()) {     // the Windows display language, as the launcher's "Auto"
        wchar_t name[LOCALE_NAME_MAX_LENGTH] = L"";
        if (!LCIDToLocaleName(MAKELCID(GetUserDefaultUILanguage(), SORT_DEFAULT), name, LOCALE_NAME_MAX_LENGTH, 0))
            name[0] = 0;
        code = name;
    }
    std::wstring two = code.substr(0, 2);
    for (auto &c : two) c = (wchar_t)towlower(c);
    for (const auto &l : LANGUAGES)
        if (two == l.code) { g_lang = &l; return; }
    g_lang = &LANGUAGES[0];
}

static std::wstring T(Text id, const std::wstring &a = L"", const std::wstring &b = L"") {
    std::wstring s = g_lang->text[id], out;
    for (size_t i = 0; i < s.size(); i++) {
        if (s[i] == L'%' && i + 1 < s.size() && (s[i + 1] == L'1' || s[i + 1] == L'2')) {
            out += s[i + 1] == L'1' ? a : b;
            i++;
        } else out += s[i];
    }
    return out;
}

// ------------------------------------------------------------------------------------------------ small helpers
static FILE *g_log = nullptr;
static bool g_silent = false;

static void logf(const wchar_t *fmt, ...) {
    if (!g_log) return;
    va_list ap;
    va_start(ap, fmt);
    vfwprintf(g_log, fmt, ap);
    va_end(ap);
    fputwc(L'\n', g_log);
    fflush(g_log);
}

static std::wstring utf8_to_wide(const std::string &s) {
    if (s.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s.data(), (int)s.size(), nullptr, 0);
    if (n <= 0) return L"";
    std::wstring w(n, 0);
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s.data(), (int)s.size(), &w[0], n);
    return w;
}

static std::string wide_to_utf8(const std::wstring &w) {
    if (w.empty()) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s(n, 0);
    WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}

static std::wstring lower(std::wstring s) {
    CharLowerBuffW(&s[0], (DWORD)s.size());
    return s;
}

static std::wstring strip_slash(std::wstring p) {
    while (p.size() > 3 && (p.back() == L'\\' || p.back() == L'/')) p.pop_back();
    return p;
}

static std::wstring full_path(const std::wstring &p) {
    wchar_t buf[32768];
    DWORD n = GetFullPathNameW(p.c_str(), 32768, buf, nullptr);
    if (!n || n >= 32768) return L"";
    return strip_slash(buf);
}

static std::wstring join(const std::wstring &a, const std::wstring &b) {
    if (a.empty()) return b;
    std::wstring r = a;
    if (r.back() != L'\\') r += L'\\';
    std::wstring c = b;
    std::replace(c.begin(), c.end(), L'/', L'\\');
    return r + c;
}

static bool is_dir(const std::wstring &p) {
    DWORD a = GetFileAttributesW(p.c_str());
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}

static bool exists(const std::wstring &p) { return GetFileAttributesW(p.c_str()) != INVALID_FILE_ATTRIBUTES; }

static bool under(const std::wstring &path, const std::wstring &folder) {
    if (folder.empty()) return false;
    std::wstring p = lower(strip_slash(path)), f = lower(strip_slash(folder));
    return p == f || (p.size() > f.size() && p.compare(0, f.size(), f) == 0 && (p[f.size()] == L'\\' || f.back() == L'\\'));
}

static std::wstring known_folder(REFKNOWNFOLDERID id) {
    PWSTR p = nullptr;
    std::wstring r;
    if (SUCCEEDED(SHGetKnownFolderPath(id, KF_FLAG_DEFAULT, nullptr, &p))) r = p;
    CoTaskMemFree(p);
    return r;
}

static std::wstring env(const wchar_t *name) {
    wchar_t buf[32768];
    DWORD n = GetEnvironmentVariableW(name, buf, 32768);
    return n && n < 32768 ? std::wstring(buf) : L"";
}

static std::wstring user_home() {   // OpenRecomp-FGC's own settings (openrecomp/manifest.py user_dir)
    std::wstring h = env(L"OPENRECOMP_HOME");
    if (!h.empty()) return full_path(h);
    return join(known_folder(FOLDERID_LocalAppData), L"OpenRecomp");
}

static bool make_dirs(const std::wstring &p) {
    if (p.empty() || is_dir(p)) return true;
    size_t slash = p.find_last_of(L'\\');
    if (slash != std::wstring::npos && slash > 2 && !make_dirs(p.substr(0, slash))) return false;
    return CreateDirectoryW(p.c_str(), nullptr) || GetLastError() == ERROR_ALREADY_EXISTS;
}

static std::wstring self_path() {
    wchar_t buf[32768];
    DWORD n = GetModuleFileNameW(nullptr, buf, 32768);
    return n && n < 32768 ? std::wstring(buf) : L"";
}

static std::wstring last_error_text(DWORD code) {
    wchar_t *msg = nullptr;
    FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr,
                   code, 0, (LPWSTR)&msg, 0, nullptr);
    std::wstring s = msg ? msg : L"";
    LocalFree(msg);
    while (!s.empty() && (s.back() == L'\n' || s.back() == L'\r' || s.back() == L' ')) s.pop_back();
    return s + L" (" + std::to_wstring(code) + L")";
}

static unsigned long long free_bytes(std::wstring p) {
    while (!p.empty() && !is_dir(p)) {
        size_t slash = p.find_last_of(L'\\');
        if (slash == std::wstring::npos) return 0;
        p = p.substr(0, slash == 2 ? 3 : slash);
        if (p.size() <= 3 && !is_dir(p)) return 0;
    }
    ULARGE_INTEGER avail;
    if (!GetDiskFreeSpaceExW(p.c_str(), &avail, nullptr, nullptr)) return 0;
    return avail.QuadPart;
}

static int message(UINT flags, const std::wstring &text, HWND owner = nullptr) {
    logf(L"message: %s", text.c_str());
    if (g_silent) return (flags & MB_YESNO) ? IDNO : ((flags & MB_RETRYCANCEL) ? IDCANCEL : IDOK);
    return MessageBoxW(owner, text.c_str(), APP_NAME, flags | MB_SETFOREGROUND);
}

// ------------------------------------------------------------------------------------------------ the payload
struct Entry {
    std::wstring path;          // relative, '\\' separated
    uint64_t size = 0, stored = 0;
    uint32_t method = 0;        // 0 stored, COMPRESS_ALGORITHM_XPRESS_HUFF, COMPRESS_ALGORITHM_LZMS
    uint8_t sha256[32] = {};
    const uint8_t *data = nullptr;
};

struct Payload {
    std::wstring version, name;
    uint64_t unpacked = 0;
    std::vector<Entry> entries;
    bool ok = false;
};

static bool safe_relative(const std::wstring &p) {
    if (p.empty() || p.size() > 400 || p[0] == L'\\' || p.find(L':') != std::wstring::npos) return false;
    size_t start = 0;
    while (start <= p.size()) {
        size_t end = p.find(L'\\', start);
        std::wstring part = p.substr(start, end == std::wstring::npos ? std::wstring::npos : end - start);
        if (part.empty() || part == L"." || part == L".." || part.back() == L'.' || part.back() == L' ') return false;
        for (wchar_t c : part)
            if (c < 32 || wcschr(L"<>\"|?*/", c)) return false;
        if (end == std::wstring::npos) break;
        start = end + 1;
    }
    return true;
}

static Payload read_payload() {
    Payload p;
    HRSRC res = FindResourceW(nullptr, L"PAYLOAD", RT_RCDATA);
    if (!res) return p;
    HGLOBAL h = LoadResource(nullptr, res);
    DWORD size = SizeofResource(nullptr, res);
    const uint8_t *b = h ? (const uint8_t *)LockResource(h) : nullptr;
    if (!b || size < 16 || memcmp(b, "ORSETUP1", 8) != 0) return p;
    const uint8_t *end = b + size, *q = b + 8;
    auto need = [&](size_t n) { return (size_t)(end - q) >= n; };
    uint32_t header = 0;
    memcpy(&header, q, 4);
    q += 4;
    if (!need(header)) return p;
    std::string text((const char *)q, header);
    q += header;
    uint32_t count = 0;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t nl = text.find('\n', pos);
        std::string line = text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
        pos = nl == std::string::npos ? text.size() : nl + 1;
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string k = line.substr(0, eq), v = line.substr(eq + 1);
        if (k == "version") p.version = utf8_to_wide(v);
        else if (k == "name") p.name = utf8_to_wide(v);
        else if (k == "files") count = (uint32_t)strtoul(v.c_str(), nullptr, 10);
    }
    if (p.version.empty() || count == 0 || count > 100000) return p;
    for (uint32_t i = 0; i < count; i++) {
        Entry e;
        uint32_t len = 0;
        if (!need(4)) return p;
        memcpy(&len, q, 4);
        q += 4;
        if (len == 0 || len > 1000 || !need(len + 8 + 8 + 4 + 32)) return p;
        e.path = utf8_to_wide(std::string((const char *)q, len));
        std::replace(e.path.begin(), e.path.end(), L'/', L'\\');
        q += len;
        memcpy(&e.size, q, 8); q += 8;
        memcpy(&e.stored, q, 8); q += 8;
        memcpy(&e.method, q, 4); q += 4;
        memcpy(e.sha256, q, 32); q += 32;
        if (!safe_relative(e.path) || !need((size_t)e.stored) || e.size > (1ull << 32)
            || (e.method == 0 && e.stored != e.size)
            || (e.method != 0 && e.method != COMPRESS_ALGORITHM_XPRESS_HUFF && e.method != COMPRESS_ALGORITHM_LZMS))
            return p;
        e.data = q;
        q += e.stored;
        p.unpacked += e.size;
        p.entries.push_back(e);
    }
    p.ok = q == end;
    return p;
}

static bool sha256(const uint8_t *data, size_t n, uint8_t out[32]) {
    return BCryptHash(BCRYPT_SHA256_ALG_HANDLE, nullptr, 0, (PUCHAR)data, (ULONG)n, out, 32) == 0;
}

// The bytes of one entry, checked against its SHA-256. Empty with ok=false when the file is damaged.
static std::vector<uint8_t> unpack_entry(const Entry &e, bool &ok) {
    std::vector<uint8_t> out;
    ok = false;
    if (e.method == 0) {
        out.assign(e.data, e.data + e.size);
    } else {
        DECOMPRESSOR_HANDLE d = nullptr;
        if (!CreateDecompressor(e.method, nullptr, &d)) return out;
        out.resize((size_t)e.size);
        SIZE_T got = 0;
        BOOL fine = Decompress(d, e.data, (SIZE_T)e.stored, out.empty() ? nullptr : out.data(), (SIZE_T)e.size, &got);
        CloseDecompressor(d);
        if (!fine || got != e.size) { out.clear(); return out; }
    }
    uint8_t digest[32];
    if (!sha256(out.data(), out.size(), digest) || memcmp(digest, e.sha256, 32) != 0) { out.clear(); return out; }
    ok = true;
    return out;
}

static bool write_file(const std::wstring &path, const uint8_t *data, size_t n) {
    HANDLE f = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return false;
    size_t done = 0;
    bool fine = true;
    while (done < n && fine) {
        DWORD chunk = (DWORD)std::min<size_t>(n - done, 1 << 24), wrote = 0;
        fine = WriteFile(f, data + done, chunk, &wrote, nullptr) && wrote == chunk;
        done += wrote;
    }
    fine = CloseHandle(f) && fine;
    return fine;
}

// ------------------------------------------------------------------------------------------------ the install record
// <install>\OpenRecomp-install.txt: what Setup put there, so an update removes only its own old files and the
// uninstall removes only the launcher. "game=" lines are the T4 source Setup placed once: a game, never removed.
struct Record {
    std::wstring version;
    std::vector<std::wstring> files, games;
    bool desktop = false;
};

static bool read_record(const std::wstring &folder, Record &r) {
    HANDLE f = CreateFileW(join(folder, MANIFEST).c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    if (f == INVALID_HANDLE_VALUE) return false;
    LARGE_INTEGER size;
    std::string text;
    if (GetFileSizeEx(f, &size) && size.QuadPart < (64 << 20)) {
        text.resize((size_t)size.QuadPart);
        DWORD got = 0;
        if (!ReadFile(f, text.empty() ? nullptr : &text[0], (DWORD)text.size(), &got, nullptr)) text.clear();
        text.resize(got);
    }
    CloseHandle(f);
    if (text.rfind("# OpenRecomp-FGC install", 0) != 0) return false;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t nl = text.find('\n', pos);
        std::string line = text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
        pos = nl == std::string::npos ? text.size() : nl + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string k = line.substr(0, eq);
        std::wstring v = utf8_to_wide(line.substr(eq + 1));
        std::replace(v.begin(), v.end(), L'/', L'\\');
        if (k == "version") r.version = v;
        else if (k == "desktop") r.desktop = v == L"1";
        else if (k == "file" && safe_relative(v)) r.files.push_back(v);
        else if (k == "game" && safe_relative(v)) r.games.push_back(v);
    }
    return true;
}

static bool write_record(const std::wstring &folder, const Record &r) {
    std::string text = "# OpenRecomp-FGC install record, written by Setup. Uninstall removes the file= lines only.\n";
    text += "version=" + wide_to_utf8(r.version) + "\n";
    text += std::string("desktop=") + (r.desktop ? "1" : "0") + "\n";
    for (auto &f : r.files) { std::wstring s = f; std::replace(s.begin(), s.end(), L'\\', L'/'); text += "file=" + wide_to_utf8(s) + "\n"; }
    for (auto &g : r.games) { std::wstring s = g; std::replace(s.begin(), s.end(), L'\\', L'/'); text += "game=" + wide_to_utf8(s) + "\n"; }
    std::wstring tmp = join(folder, std::wstring(MANIFEST) + L".tmp");
    if (!write_file(tmp, (const uint8_t *)text.data(), text.size())) return false;
    return MoveFileExW(tmp.c_str(), join(folder, MANIFEST).c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
}

// ------------------------------------------------------------------------------------------------ processes
static std::vector<std::wstring> processes_under(const std::wstring &folder) {
    std::vector<std::wstring> found;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return found;
    PROCESSENTRY32W pe = {sizeof(pe)};
    DWORD me = GetCurrentProcessId();
    for (BOOL ok = Process32FirstW(snap, &pe); ok; ok = Process32NextW(snap, &pe)) {
        if (pe.th32ProcessID == me || !pe.th32ProcessID) continue;
        HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pe.th32ProcessID);
        if (!h) continue;
        wchar_t buf[32768];
        DWORD n = 32768;
        if (QueryFullProcessImageNameW(h, 0, buf, &n) && under(buf, folder)) found.push_back(buf);
        CloseHandle(h);
    }
    CloseHandle(snap);
    return found;
}

// ------------------------------------------------------------------------------------------------ shortcuts and registry
static bool make_link(const std::wstring &link, const std::wstring &target, const std::wstring &args,
                      const std::wstring &workdir, const std::wstring &icon, const std::wstring &description) {
    IShellLinkW *sl = nullptr;
    if (FAILED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&sl)))) return false;
    sl->SetPath(target.c_str());
    sl->SetArguments(args.c_str());
    sl->SetWorkingDirectory(workdir.c_str());
    sl->SetDescription(description.c_str());
    if (!icon.empty()) sl->SetIconLocation(icon.c_str(), 0);
    IPropertyStore *ps = nullptr;
    if (SUCCEEDED(sl->QueryInterface(IID_PPV_ARGS(&ps)))) {
        PROPVARIANT pv;
        if (SUCCEEDED(InitPropVariantFromString(APP_ID, &pv))) {
            ps->SetValue(PKEY_AppUserModel_ID, pv);
            ps->Commit();
            PropVariantClear(&pv);
        }
        ps->Release();
    }
    IPersistFile *pf = nullptr;
    bool ok = SUCCEEDED(sl->QueryInterface(IID_PPV_ARGS(&pf))) && SUCCEEDED(pf->Save(link.c_str(), TRUE));
    if (pf) pf->Release();
    sl->Release();
    return ok;
}

// Removes a shortcut only when it points into this install folder (never a shortcut the player made elsewhere).
static void remove_link_into(const std::wstring &link, const std::wstring &folder) {
    if (!exists(link)) return;
    IShellLinkW *sl = nullptr;
    bool ours = false;
    if (SUCCEEDED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&sl)))) {
        IPersistFile *pf = nullptr;
        if (SUCCEEDED(sl->QueryInterface(IID_PPV_ARGS(&pf)))) {
            if (SUCCEEDED(pf->Load(link.c_str(), STGM_READ))) {
                wchar_t target[32768] = L"";
                if (SUCCEEDED(sl->GetPath(target, 32768, nullptr, SLGP_RAWPATH))) ours = under(target, folder);
            }
            pf->Release();
        }
        sl->Release();
    }
    if (ours) DeleteFileW(link.c_str());
}

static void set_string(HKEY k, const wchar_t *name, const std::wstring &v) {
    RegSetValueExW(k, name, 0, REG_SZ, (const BYTE *)v.c_str(), (DWORD)((v.size() + 1) * sizeof(wchar_t)));
}

static void set_dword(HKEY k, const wchar_t *name, DWORD v) { RegSetValueExW(k, name, 0, REG_DWORD, (const BYTE *)&v, sizeof(v)); }

static std::wstring get_string(HKEY root, const wchar_t *key, const wchar_t *name) {
    wchar_t buf[32768];
    DWORD size = sizeof(buf);
    if (RegGetValueW(root, key, name, RRF_RT_REG_SZ, nullptr, buf, &size) != ERROR_SUCCESS) return L"";
    return buf;
}

// ------------------------------------------------------------------------------------------------ install
struct Options {
    std::wstring folder;     // the install folder (contains OpenRecomp-FGC\)
    bool desktop = false, start = true;
    std::vector<std::wstring> games;   // bundled games to install ("t5dr", "t4"), see install_games()
};

// ------------------------------------------------------------------------------------------------ bundled games
// A full Setup also carries the signed GitHub release files of T5DR Online and T4, untouched:
// bundled-games\<game>\<release zip>, SHA256SUMS, SHA256SUMS.sig (tools/make_installer.py --games). They are
// unpacked into the staging folder like every file (SHA-256 checked), never placed in the install. Once the
// launcher is in place, its own Python installs each chosen game with the launcher's release checks
// (openrecomp/bundled_games.py: signature with the launcher's built-in keys, SHA256SUMS, unpack rules, marker).
static const wchar_t *GAMES_DIR = L"bundled-games";
static const wchar_t *GAME_IDS[] = {L"t5dr", L"t4"};

static bool is_bundle_entry(const std::wstring &rel) { return lower(rel).rfind(std::wstring(GAMES_DIR) + L"\\", 0) == 0; }

static std::wstring bundle_game(const std::wstring &rel) {      // "t5dr" for bundled-games\t5dr\<file>
    size_t a = rel.find(L'\\');
    size_t b = a == std::wstring::npos ? a : rel.find(L'\\', a + 1);
    return b == std::wstring::npos ? L"" : lower(rel.substr(a + 1, b - a - 1));
}

// The version in the game's release zip name (T5DR-Online-1.2.0.zip, OpenRecomp-Tekken4-v0.1.0.zip), "" when absent.
static std::wstring bundle_version(const Payload &p, const std::wstring &game) {
    for (auto &e : p.entries) {
        if (!is_bundle_entry(e.path) || bundle_game(e.path) != game) continue;
        std::wstring name = e.path.substr(e.path.find_last_of(L'\\') + 1);
        if (lower(name).size() < 5 || lower(name).substr(name.size() - 4) != L".zip") continue;
        std::wstring stem = name.substr(0, name.size() - 4);
        size_t dash = stem.find_last_of(L'-');
        // T5DR-Online-1.2.0 / OpenRecomp-Tekken4-v0.1.0 (a test suffix like -beta.1 keeps its own dash)
        for (const wchar_t *head : {L"T5DR-Online-", L"OpenRecomp-Tekken4-"})
            if (stem.rfind(head, 0) == 0) return stem.substr(wcslen(head));
        return dash == std::wstring::npos ? L"" : stem.substr(dash + 1);
    }
    return L"";
}

static bool payload_has_game(const Payload &p, const std::wstring &game) { return !bundle_version(p, game).empty(); }

static bool wanted(const Options &o, const std::wstring &game) {
    return std::find(o.games.begin(), o.games.end(), game) != o.games.end();
}

static std::wstring read_text_file(const std::wstring &path) {
    HANDLE f = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                           OPEN_EXISTING, 0, nullptr);
    if (f == INVALID_HANDLE_VALUE) return L"";
    std::string text(64 * 1024, 0);
    DWORD got = 0;
    if (!ReadFile(f, &text[0], (DWORD)text.size(), &got, nullptr)) got = 0;
    CloseHandle(f);
    text.resize(got);
    if (text.rfind("\xEF\xBB\xBF", 0) == 0) text.erase(0, 3);
    return utf8_to_wide(text);
}

static std::wstring g_games_summary;    // the launcher's own words about the bundled games (its 7 languages)
static bool g_games_failed = false;

struct Progress {
    HWND window = nullptr;
    volatile LONG cancel = 0;
    void step(Text what, int percent) {
        if (window) PostMessageW(window, WM_APP + 1, (WPARAM)what, (LPARAM)percent);
    }
    void say(const std::wstring &text, int percent) {      // a status line made here (the window frees it)
        if (!window) return;
        auto *copy = new std::wstring(text);
        if (!PostMessageW(window, WM_APP + 3, (WPARAM)copy, (LPARAM)percent)) delete copy;
    }
};

static std::wstring launcher_dir(const std::wstring &folder) { return join(folder, APP_FOLDER); }
static std::wstring python_exe(const std::wstring &folder) { return join(launcher_dir(folder), L"portable\\pythonw.exe"); }
// The launcher's icon when the bundle carries it; else the uninstaller's (the same picture, resource 1).
static std::wstring icon_path(const std::wstring &folder) {
    std::wstring ico = join(launcher_dir(folder), L"openrecomp\\ui\\assets\\icon.ico");
    return exists(ico) ? ico : join(folder, UNINSTALL_EXE);
}

static bool is_game_entry(const std::wstring &rel) {
    std::wstring l = lower(rel);
    return l.rfind(L"t4\\", 0) == 0;
}

static std::wstring game_title(const std::wstring &game) { return game == L"t5dr" ? L"Tekken 5 DR Online" : L"Tekken 4"; }

// Runs the launcher's openrecomp.bundled_games on the release files unpacked into stage\bundled-games and waits.
// The launcher's Python checks every game like an update from GitHub and writes its result in the player's language.
static void install_games(const std::wstring &folder, const std::wstring &stage, const Options &o, Progress &pr) {
    std::wstring list;
    for (auto &g : o.games) list += (list.empty() ? L"" : L",") + g;
    std::wstring status = join(stage, L"games-status.txt"), summary = join(stage, L"games-summary.txt");
    std::wstring py = python_exe(folder);
    std::wstring cmd = L"\"" + py + L"\" -B -m openrecomp.bundled_games --from \"" + join(stage, GAMES_DIR) +
                       L"\" --parent \"" + folder + L"\" --games " + list + L" --lang " + g_lang->code +
                       L" --summary \"" + summary + L"\" --status \"" + status + L"\"";
    logf(L"games: %s", cmd.c_str());
    STARTUPINFOW si = {sizeof(si)};
    PROCESS_INFORMATION pi = {};
    if (!CreateProcessW(py.c_str(), &cmd[0], nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, launcher_dir(folder).c_str(), &si, &pi)) {
        logf(L"games: could not start the launcher's Python: %s", last_error_text(GetLastError()).c_str());
        g_games_summary = T(T_GAMES_NOT_RUN);
        g_games_failed = true;
        return;
    }
    CloseHandle(pi.hThread);
    pr.say(T(T_GAME_INSTALLING, game_title(o.games[0]), L"0"), 96);
    std::wstring shown;
    for (int waited = 0; WaitForSingleObject(pi.hProcess, 250) == WAIT_TIMEOUT; waited += 250) {
        if (waited > 30 * 60 * 1000) {             // never hang Setup for ever: half an hour is far beyond any PC
            TerminateProcess(pi.hProcess, 9);
            WaitForSingleObject(pi.hProcess, 5000);
            break;
        }
        std::wstring line = read_text_file(status);           // "<game> <percent>"
        size_t space = line.find(L' ');
        if (space != std::wstring::npos && line != shown) {
            shown = line;
            std::wstring game = line.substr(0, space), pct = line.substr(space + 1);
            while (!pct.empty() && (pct.back() == L'\n' || pct.back() == L'\r')) pct.pop_back();
            if (game == L"t5dr" || game == L"t4") pr.say(T(T_GAME_INSTALLING, game_title(game), pct), 96);
        }
    }
    DWORD code = 2;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    g_games_summary = read_text_file(summary);
    logf(L"games: exit %lu: %s", code, g_games_summary.c_str());
    if (g_games_summary.empty()) g_games_summary = T(T_GAMES_NOT_RUN);
    g_games_failed = code != 0;
}

static void remove_empty_parents(const std::wstring &folder, std::wstring rel) {
    for (;;) {
        size_t slash = rel.find_last_of(L'\\');
        if (slash == std::wstring::npos) return;
        rel = rel.substr(0, slash);
        if (!RemoveDirectoryW(join(folder, rel).c_str())) return;
    }
}

static void remove_tree(const std::wstring &dir) {   // only our own staging folder
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(join(dir, L"*").c_str(), &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            std::wstring n = fd.cFileName;
            if (n == L"." || n == L"..") continue;
            std::wstring p = join(dir, n);
            if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && !(fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) remove_tree(p);
            else { SetFileAttributesW(p.c_str(), FILE_ATTRIBUTE_NORMAL); DeleteFileW(p.c_str()); }
        } while (FindNextFileW(h, &fd));
        FindClose(h);
    }
    RemoveDirectoryW(dir.c_str());
}

static bool move_with_retry(const std::wstring &from, const std::wstring &to) {
    for (int i = 0; i < 40; i++) {     // antivirus and the search indexer hold new files for a moment
        DWORD a = GetFileAttributesW(to.c_str());
        if (a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_READONLY)) SetFileAttributesW(to.c_str(), a & ~FILE_ATTRIBUTE_READONLY);
        if (MoveFileExW(from.c_str(), to.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) return true;
        DWORD e = GetLastError();
        if (e != ERROR_ACCESS_DENIED && e != ERROR_SHARING_VIOLATION && e != ERROR_LOCK_VIOLATION) return false;
        Sleep(250);
    }
    return false;
}

// Returns "" when done, else the reason (in the player's language).
static std::wstring install(const Payload &payload, const Options &o, Progress &pr, bool &updated) {
    std::wstring folder = o.folder;
    Record old;
    updated = read_record(folder, old);
    logf(L"install %s into %s (%s)", payload.version.c_str(), folder.c_str(), updated ? L"update" : L"new");
    if (!make_dirs(folder)) return T(T_NOT_WRITABLE);
    std::wstring stage = join(folder, L".setup-" + std::to_wstring(GetCurrentProcessId()));
    remove_tree(stage);
    if (!CreateDirectoryW(stage.c_str(), nullptr)) return T(T_NOT_WRITABLE);
    SetFileAttributesW(stage.c_str(), FILE_ATTRIBUTE_HIDDEN);
    bool place_games = !is_dir(join(folder, L"T4"));       // the T4 source only once: later the launcher updates it
    std::vector<const Entry *> todo;
    for (auto &e : payload.entries) {
        if (is_bundle_entry(e.path)) {
            if (wanted(o, bundle_game(e.path))) todo.push_back(&e);    // to the staging folder only
        } else if (!is_game_entry(e.path) || place_games) {
            todo.push_back(&e);
        }
    }
    // 1. Every file unpacked and checked in the staging folder before anything in the install changes.
    uint64_t done = 0, total = 0;
    for (auto *e : todo) total += e->size;
    pr.step(T_EXTRACTING, 0);
    for (auto *e : todo) {
        if (pr.cancel) { remove_tree(stage); return L"cancel"; }
        bool ok = false;
        std::vector<uint8_t> bytes = unpack_entry(*e, ok);
        if (!ok) { remove_tree(stage); return T(T_DAMAGED); }
        std::wstring target = join(stage, e->path);
        size_t slash = target.find_last_of(L'\\');
        if (!make_dirs(target.substr(0, slash)) || !write_file(target, bytes.data(), bytes.size())) {
            DWORD err = GetLastError();
            remove_tree(stage);
            return T(T_FAILED, last_error_text(err));
        }
        done += e->size;
        pr.step(T_EXTRACTING, (int)(total ? done * 80 / total : 80));
    }
    // 2. The files moved into place (same drive: a rename each). Nothing of the player's is touched. A file
    // that is replaced waits in the staging folder's backup until the install record is written: any failure
    // before that puts every replaced file back and takes every new one out (a failed first install leaves no
    // files without a record, a failed update leaves the old version as it was).
    pr.step(T_COPYING, 80);
    std::set<std::wstring> now;
    Record rec;
    rec.version = payload.version;
    rec.desktop = o.desktop;
    rec.games = old.games;
    std::wstring backup = join(stage, L".old");
    struct Placed { std::wstring rel; bool had_old; };
    std::vector<Placed> placed;
    auto roll_back = [&]() -> bool {
        bool clean = true;
        for (auto it = placed.rbegin(); it != placed.rend(); ++it) {
            std::wstring target = join(folder, it->rel);
            SetFileAttributesW(target.c_str(), FILE_ATTRIBUTE_NORMAL);
            if (!DeleteFileW(target.c_str()) && exists(target)) { clean = false; continue; }
            if (it->had_old) {
                if (!move_with_retry(join(backup, it->rel), target)) { clean = false; continue; }
            } else {
                remove_empty_parents(folder, it->rel);
            }
        }
        if (clean) remove_tree(stage);
        else logf(L"rollback incomplete: the old files wait in %s", backup.c_str());
        return clean;
    };
    int fail_at = _wtoi(env(L"OPENRECOMP_SETUP_TEST_FAIL_AT").c_str());   // tests: the n-th placement fails
    for (auto *e : todo) {
        if (is_bundle_entry(e->path)) continue;            // the games' release files stay in the staging folder
        std::wstring target = join(folder, e->path);
        size_t slash = target.find_last_of(L'\\');
        bool had_old = exists(target);
        bool ok = make_dirs(target.substr(0, slash));
        if (ok && had_old) {
            std::wstring saved = join(backup, e->path);
            ok = make_dirs(saved.substr(0, saved.find_last_of(L'\\'))) && move_with_retry(target, saved);
        }
        if (ok && fail_at > 0 && (int)placed.size() + 1 == fail_at) { ok = false; SetLastError(ERROR_SHARING_VIOLATION); }
        if (ok) ok = move_with_retry(join(stage, e->path), target);
        if (!ok) {
            DWORD err = GetLastError();
            logf(L"could not place %s: %s", e->path.c_str(), last_error_text(err).c_str());
            if (had_old && !exists(target)) move_with_retry(join(backup, e->path), target);
            if (!had_old) remove_empty_parents(folder, e->path);     // folders made for this file only
            roll_back();
            return T(T_FAILED, e->path + L": " + last_error_text(err));
        }
        placed.push_back({e->path, had_old});
        if (is_game_entry(e->path)) {
            if (std::find(rec.games.begin(), rec.games.end(), e->path) == rec.games.end()) rec.games.push_back(e->path);
        } else {
            rec.files.push_back(e->path);
            now.insert(lower(e->path));
        }
    }
    if (!write_record(folder, rec)) {
        DWORD err = GetLastError();
        roll_back();
        return T(T_FAILED, last_error_text(err));
    }
    remove_tree(backup);             // the new version is recorded: the backup of the old files goes
    // 3. Launcher files of the old version that the new one no longer has.
    for (auto &f : old.files) {
        if (now.count(lower(f))) continue;
        std::wstring p = join(folder, f);
        SetFileAttributesW(p.c_str(), FILE_ATTRIBUTE_NORMAL);
        if (DeleteFileW(p.c_str())) remove_empty_parents(folder, f);
    }
    // 4. Shortcuts and the Apps & Features entry (this user only).
    pr.step(T_SHORTCUTS, 95);
    std::wstring programs = known_folder(FOLDERID_Programs), desktop = known_folder(FOLDERID_Desktop);
    std::wstring target = python_exe(folder), args = L"-B -m openrecomp", work = launcher_dir(folder), icon = icon_path(folder);
    if (!programs.empty() && !make_link(join(programs, LINK_NAME), target, args, work, icon, APP_NAME))
        logf(L"could not make the Start menu shortcut in %s", programs.c_str());
    if (!desktop.empty()) {
        if (o.desktop) {
            if (!make_link(join(desktop, LINK_NAME), target, args, work, icon, APP_NAME))
                logf(L"could not make the desktop shortcut in %s", desktop.c_str());
        } else {
            remove_link_into(join(desktop, LINK_NAME), folder);
        }
    }
    HKEY k;
    if (RegCreateKeyExW(HKEY_CURRENT_USER, UNINSTALL_KEY, 0, nullptr, 0, KEY_WRITE, nullptr, &k, nullptr) == ERROR_SUCCESS) {
        std::wstring un = join(folder, UNINSTALL_EXE);
        set_string(k, L"DisplayName", APP_NAME);
        set_string(k, L"DisplayVersion", payload.version);
        set_string(k, L"Publisher", L"OpenRecomp-FGC project");
        set_string(k, L"InstallLocation", folder);
        set_string(k, L"DisplayIcon", icon);
        set_string(k, L"UninstallString", L"\"" + un + L"\"");
        set_string(k, L"QuietUninstallString", L"\"" + un + L"\" /S");
        set_dword(k, L"NoModify", 1);
        set_dword(k, L"NoRepair", 1);
        set_dword(k, L"EstimatedSize", (DWORD)(payload.unpacked / 1024));
        RegCloseKey(k);
    }
    if (RegCreateKeyExW(HKEY_CURRENT_USER, OWN_KEY, 0, nullptr, 0, KEY_WRITE, nullptr, &k, nullptr) == ERROR_SUCCESS) {
        set_string(k, L"InstallLocation", folder);
        set_string(k, L"Version", payload.version);
        RegCloseKey(k);
    }
    SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, nullptr, nullptr);
    // 5. The bundled games, now that the launcher that checks them is in place. A game that fails leaves the
    // launcher installed: the summary says so, and the launcher can install that game later.
    g_games_summary.clear();
    g_games_failed = false;
    if (!o.games.empty() && is_dir(join(stage, GAMES_DIR))) install_games(folder, stage, o, pr);
    remove_tree(stage);
    pr.step(updated ? T_UPDATED : T_DONE, 100);
    logf(L"done: %zu files", rec.files.size());
    return L"";
}

static void start_launcher(const std::wstring &folder) {
    std::wstring py = python_exe(folder);
    std::wstring cmd = L"\"" + py + L"\" -B -m openrecomp";
    STARTUPINFOW si = {sizeof(si)};
    PROCESS_INFORMATION pi = {};
    if (CreateProcessW(py.c_str(), &cmd[0], nullptr, nullptr, FALSE, 0, nullptr, launcher_dir(folder).c_str(), &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
}

// The registered install, when its folder still has our record.
static std::wstring registered_folder() {
    std::wstring f = get_string(HKEY_CURRENT_USER, OWN_KEY, L"InstallLocation");
    Record r;
    return !f.empty() && read_record(f, r) ? f : L"";
}

static std::wstring default_folder() {
    std::wstring f = registered_folder();
    if (!f.empty()) return f;
    std::wstring base = known_folder(FOLDERID_UserProgramFiles);    // %LOCALAPPDATA%\Programs
    if (base.empty()) base = join(known_folder(FOLDERID_LocalAppData), L"Programs");
    return join(base, L"OpenRecomp");
}

// "" when the folder can be used, else why not.
static std::wstring check_folder(const std::wstring &folder, uint64_t need) {
    if (folder.size() < 4 || folder[1] != L':' || folder[2] != L'\\') return T(T_BAD_FOLDER);
    std::wstring windows = env(L"WINDIR");
    if (under(folder, windows) || under(folder, user_home()) || under(user_home(), folder)) return T(T_BAD_FOLDER);
    UINT type = GetDriveTypeW(folder.substr(0, 3).c_str());
    if (type == DRIVE_NO_ROOT_DIR || type == DRIVE_CDROM || type == DRIVE_UNKNOWN) return T(T_BAD_FOLDER);
    unsigned long long free = free_bytes(folder);
    if (free < need) return T(T_NO_SPACE, std::to_wstring(need >> 20), std::to_wstring(free >> 20));
    // Writable? Probe in the nearest existing folder; nothing is left behind.
    std::wstring probe_dir = folder;
    while (!is_dir(probe_dir) && probe_dir.size() > 3) probe_dir = probe_dir.substr(0, probe_dir.find_last_of(L'\\'));
    if (probe_dir.size() == 2) probe_dir += L'\\';
    std::wstring probe = join(probe_dir, L".openrecomp-setup-probe-" + std::to_wstring(GetCurrentProcessId()));
    HANDLE f = CreateFileW(probe.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_TEMPORARY | FILE_FLAG_DELETE_ON_CLOSE, nullptr);
    if (f == INVALID_HANDLE_VALUE) return T(T_NOT_WRITABLE);
    CloseHandle(f);
    return L"";
}

// ------------------------------------------------------------------------------------------------ uninstall
static void remove_settings(const std::wstring &home) {
    // Only OpenRecomp-FGC's own settings: preferences, the player's manifests, pictures, private T5DR preferences
    // and logins. Kept: installs\ (T4 zips the player registered), t4-source\*\save (game saves), anything unknown.
    for (const wchar_t *f : {L"config.json", L"config.json.tmp"}) DeleteFileW(join(home, f).c_str());
    for (const wchar_t *d : {L"art", L"games", L"t5dr"}) {
        std::wstring p = join(home, d);
        DWORD a = GetFileAttributesW(p.c_str());
        if (a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY) && !(a & FILE_ATTRIBUTE_REPARSE_POINT)) remove_tree(p);
    }
    WIN32_FIND_DATAW fd;
    std::wstring t4 = join(home, L"t4-source");
    HANDLE h = FindFirstFileW(join(t4, L"*").c_str(), &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            std::wstring n = fd.cFileName;
            if (n == L"." || n == L".." || !(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) continue;
            DeleteFileW(join(join(t4, n), L"settings.json").c_str());
            RemoveDirectoryW(join(t4, n).c_str());     // only when nothing else (no save) is left
        } while (FindNextFileW(h, &fd));
        FindClose(h);
    }
    RemoveDirectoryW(t4.c_str());
    RemoveDirectoryW(home.c_str());
}

static std::vector<std::wstring> leftovers(const std::wstring &folder) {
    std::vector<std::wstring> out;
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(join(folder, L"*").c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) return out;
    do {
        std::wstring n = fd.cFileName;
        if (n != L"." && n != L"..") out.push_back(n);
    } while (FindNextFileW(h, &fd) && out.size() < 12);
    FindClose(h);
    return out;
}

static int uninstall(const std::wstring &folder, int settings_choice /* -1 ask, 0 keep, 1 remove */) {
    Record r;
    if (!read_record(folder, r)) { message(MB_ICONERROR, T(T_NOT_INSTALLED)); return 2; }
    if (message(MB_YESNO | MB_ICONQUESTION, T(T_UNINSTALL_ASK, folder)) != IDYES && !g_silent) return 1;
    for (;;) {
        auto running = processes_under(launcher_dir(folder));
        if (running.empty()) break;
        if (message(MB_RETRYCANCEL | MB_ICONWARNING, T(T_RUNNING)) != IDRETRY) return g_silent ? 3 : 1;
    }
    std::vector<std::wstring> files = r.files;
    std::sort(files.begin(), files.end(), [](const std::wstring &a, const std::wstring &b) { return a.size() > b.size(); });
    for (auto &f : files) {
        if (is_game_entry(f)) continue;
        std::wstring p = join(folder, f);
        SetFileAttributesW(p.c_str(), FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(p.c_str());
    }
    for (auto &f : files) remove_empty_parents(folder, f);
    RemoveDirectoryW(launcher_dir(folder).c_str());
    // The launcher's own update workspace beside it (openrecomp/updater.py: backups of older launcher versions).
    std::wstring updates = launcher_dir(folder) + L".update";
    DWORD ua = GetFileAttributesW(updates.c_str());
    if (ua != INVALID_FILE_ATTRIBUTES && (ua & FILE_ATTRIBUTE_DIRECTORY) && !(ua & FILE_ATTRIBUTE_REPARSE_POINT)) remove_tree(updates);
    DeleteFileW(join(folder, MANIFEST).c_str());
    for (auto &dir : {known_folder(FOLDERID_Programs), known_folder(FOLDERID_Desktop)})
        if (!dir.empty()) remove_link_into(join(dir, LINK_NAME), folder);
    // Only this folder's entries: a second copy's uninstaller never takes the Apps entry of the registered one.
    if (lower(get_string(HKEY_CURRENT_USER, UNINSTALL_KEY, L"InstallLocation")) == lower(folder))
        RegDeleteTreeW(HKEY_CURRENT_USER, UNINSTALL_KEY);
    if (lower(get_string(HKEY_CURRENT_USER, OWN_KEY, L"InstallLocation")) == lower(folder))
        RegDeleteTreeW(HKEY_CURRENT_USER, L"Software\\OpenRecomp-FGC");
    std::wstring home = user_home();
    if (is_dir(home)) {
        bool remove = settings_choice == 1;
        if (settings_choice < 0 && !g_silent) remove = message(MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2, T(T_SETTINGS_ASK, home)) == IDYES;
        if (remove) remove_settings(home);
    }
    RemoveDirectoryW(folder.c_str());     // only when empty: games and the player's files stay
    std::wstring text = T(T_REMOVED);
    auto left = leftovers(folder);
    if (!left.empty() && is_dir(folder)) {
        text += L"\n\n" + T(T_KEPT, folder);
        for (auto &n : left) text += L"\n  " + n;
    }
    SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, nullptr, nullptr);
    message(MB_ICONINFORMATION, text);
    logf(L"uninstalled from %s", folder.c_str());
    return 0;
}

// ------------------------------------------------------------------------------------------------ the window
enum { ID_FOLDER = 101, ID_CHANGE, ID_DESKTOP, ID_START, ID_INSTALL, ID_CANCEL, ID_SPACE, ID_STATUS, ID_PROGRESS, ID_INTRO,
       ID_GAMES, ID_GAME_FIRST };

struct Ui {
    HWND wnd = nullptr, folder = nullptr, change = nullptr, desktop = nullptr, start = nullptr, install = nullptr,
         cancel = nullptr, space = nullptr, status = nullptr, progress = nullptr, intro = nullptr;
    HWND game[2] = {nullptr, nullptr};     // one checkbox per bundled game (GAME_IDS order), when the payload has it
    HFONT font = nullptr, bold = nullptr;
    const Payload *payload = nullptr;
    Options opt;
    Progress pr;
    HANDLE worker = nullptr;
    bool busy = false, finished = false, updated = false, locked = false;
    std::wstring result;
    int dpi = 96;
    int exit_code = 1;
};
static Ui g;

static int S(int v) { return MulDiv(v, g.dpi, 96); }

static std::wstring window_text(HWND h) {
    int n = GetWindowTextLengthW(h);
    std::wstring s(n, 0);
    GetWindowTextW(h, &s[0], n + 1);
    return s;
}

// Files are unpacked next to their place and renamed into it: the payload's size plus some room.
static uint64_t needed(const Payload &p) { return p.unpacked + p.unpacked / 10 + (50ull << 20); }
static uint64_t needed_bytes() { return needed(*g.payload); }

static void refresh_space() {
    std::wstring folder = full_path(window_text(g.folder));
    unsigned long long free = folder.empty() ? 0 : free_bytes(folder);
    SetWindowTextW(g.space, T(T_SPACE, std::to_wstring(needed_bytes() >> 20), std::to_wstring(free >> 20)).c_str());
}

static DWORD WINAPI worker_main(LPVOID) {
    // COM is per thread: without this the shortcuts' CoCreateInstance failed and a window install had none.
    HRESULT com = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
    g.result = install(*g.payload, g.opt, g.pr, g.updated);
    if (SUCCEEDED(com)) CoUninitialize();
    PostMessageW(g.wnd, WM_APP + 2, 0, 0);
    return 0;
}

static void browse() {
    IFileOpenDialog *d = nullptr;
    if (FAILED(CoCreateInstance(CLSID_FileOpenDialog, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&d)))) return;
    DWORD flags = 0;
    d->GetOptions(&flags);
    d->SetOptions(flags | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST);
    d->SetTitle(T(T_PICK_TITLE).c_str());
    std::wstring current = full_path(window_text(g.folder));
    while (!current.empty() && !is_dir(current) && current.size() > 3) current = current.substr(0, current.find_last_of(L'\\'));
    IShellItem *start = nullptr;
    if (!current.empty() && SUCCEEDED(SHCreateItemFromParsingName(current.c_str(), nullptr, IID_PPV_ARGS(&start)))) {
        d->SetFolder(start);
        start->Release();
    }
    if (SUCCEEDED(d->Show(g.wnd))) {
        IShellItem *item = nullptr;
        if (SUCCEEDED(d->GetResult(&item))) {
            PWSTR path = nullptr;
            if (SUCCEEDED(item->GetDisplayName(SIGDN_FILESYSPATH, &path))) {
                std::wstring chosen = strip_slash(path);
                Record r;
                // A folder that already holds other things gets its own OpenRecomp folder inside.
                if (!read_record(chosen, r) && !leftovers(chosen).empty() && lower(chosen.substr(chosen.find_last_of(L'\\') + 1)) != L"openrecomp")
                    chosen = join(chosen, L"OpenRecomp");
                SetWindowTextW(g.folder, chosen.c_str());
                refresh_space();
            }
            CoTaskMemFree(path);
            item->Release();
        }
    }
    d->Release();
}

static void begin_install() {
    std::wstring folder = full_path(window_text(g.folder));
    std::wstring why = check_folder(folder, needed_bytes());
    if (!why.empty()) { message(MB_ICONWARNING, why, g.wnd); return; }
    for (;;) {
        if (processes_under(launcher_dir(folder)).empty()) break;
        if (message(MB_RETRYCANCEL | MB_ICONWARNING, T(T_RUNNING), g.wnd) != IDRETRY) return;
    }
    g.opt.folder = folder;
    g.opt.desktop = SendMessageW(g.desktop, BM_GETCHECK, 0, 0) == BST_CHECKED;
    g.opt.start = SendMessageW(g.start, BM_GETCHECK, 0, 0) == BST_CHECKED;
    g.opt.games.clear();
    for (int i = 0; i < 2; i++)
        if (g.game[i] && SendMessageW(g.game[i], BM_GETCHECK, 0, 0) == BST_CHECKED) g.opt.games.push_back(GAME_IDS[i]);
    g.busy = true;
    for (HWND h : {g.folder, g.change, g.desktop, g.start, g.install, g.game[0], g.game[1]}) if (h) EnableWindow(h, FALSE);
    g.worker = CreateThread(nullptr, 0, worker_main, nullptr, 0, nullptr);
    if (!g.worker) { g.busy = false; message(MB_ICONERROR, T(T_FAILED, last_error_text(GetLastError())), g.wnd); }
}

static HWND control(const wchar_t *cls, const std::wstring &text, DWORD style, int x, int y, int w, int h, int id, HFONT f) {
    HWND c = CreateWindowExW(0, cls, text.c_str(), WS_CHILD | WS_VISIBLE | style, S(x), S(y), S(w), S(h), g.wnd,
                             (HMENU)(INT_PTR)id, GetModuleHandleW(nullptr), nullptr);
    SendMessageW(c, WM_SETFONT, (WPARAM)f, TRUE);
    return c;
}

static LRESULT CALLBACK wnd_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    switch (m) {
    case WM_CREATE: {
        g.wnd = h;
        NONCLIENTMETRICSW nm = {sizeof(nm)};
        SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof(nm), &nm, 0);
        nm.lfMessageFont.lfHeight = -S(12);
        g.font = CreateFontIndirectW(&nm.lfMessageFont);
        nm.lfMessageFont.lfWeight = FW_BOLD;
        nm.lfMessageFont.lfHeight = -S(16);
        g.bold = CreateFontIndirectW(&nm.lfMessageFont);
        Record r;
        bool update = read_record(g.opt.folder, r);
        control(L"STATIC", T(T_SETUP_TITLE, g.payload->version), 0, 16, 12, 520, 24, 0, g.bold);
        g.intro = control(L"STATIC", update ? T(T_UPDATE_INTRO, g.payload->version) : T(T_INTRO), 0, 16, 42, 520, 48, ID_INTRO, g.font);
        control(L"STATIC", g.locked ? T(T_ALREADY_HERE) : T(T_FOLDER), 0, 16, 98, 520, 34, 0, g.font);
        g.folder = control(L"EDIT", g.opt.folder, WS_BORDER | ES_AUTOHSCROLL | WS_TABSTOP | (g.locked ? ES_READONLY : 0), 16, 136, 410, 24, ID_FOLDER, g.font);
        g.change = control(L"BUTTON", T(T_CHANGE), BS_PUSHBUTTON | WS_TABSTOP, 434, 135, 102, 26, ID_CHANGE, g.font);
        if (g.locked) EnableWindow(g.change, FALSE);
        g.space = control(L"STATIC", L"", 0, 16, 166, 520, 20, ID_SPACE, g.font);
        g.desktop = control(L"BUTTON", T(T_DESKTOP), BS_AUTOCHECKBOX | WS_TABSTOP, 16, 192, 520, 22, ID_DESKTOP, g.font);
        g.start = control(L"BUTTON", T(T_START_AFTER), BS_AUTOCHECKBOX | WS_TABSTOP, 16, 216, 520, 22, ID_START, g.font);
        SendMessageW(g.desktop, BM_SETCHECK, (update ? r.desktop : g.opt.desktop) ? BST_CHECKED : BST_UNCHECKED, 0);
        SendMessageW(g.start, BM_SETCHECK, g.opt.start ? BST_CHECKED : BST_UNCHECKED, 0);
        int y = 248;                // a full Setup: one checkbox per game it carries (both on)
        if (payload_has_game(*g.payload, L"t5dr") || payload_has_game(*g.payload, L"t4")) {
            control(L"STATIC", T(T_GAMES), 0, 16, y - 4, 520, 34, ID_GAMES, g.font);     // two lines
            y += 32;
            for (int i = 0; i < 2; i++) {
                std::wstring v = bundle_version(*g.payload, GAME_IDS[i]);
                if (v.empty()) continue;
                g.game[i] = control(L"BUTTON", T(i == 0 ? T_GAME_T5DR : T_GAME_T4, v), BS_AUTOCHECKBOX | WS_TABSTOP,
                                    28, y, 508, 22, ID_GAME_FIRST + i, g.font);
                SendMessageW(g.game[i], BM_SETCHECK, wanted(g.opt, GAME_IDS[i]) ? BST_CHECKED : BST_UNCHECKED, 0);
                y += 24;
            }
            y += 8;
        }
        g.progress = control(PROGRESS_CLASSW, L"", 0, 16, y, 520, 16, ID_PROGRESS, g.font);
        SendMessageW(g.progress, PBM_SETRANGE, 0, MAKELPARAM(0, 100));
        g.status = control(L"STATIC", L"", 0, 16, y + 22, 520, 36, ID_STATUS, g.font);
        g.install = control(L"BUTTON", update ? T(T_UPDATE) : T(T_INSTALL), BS_DEFPUSHBUTTON | WS_TABSTOP, 320, y + 64, 104, 28, ID_INSTALL, g.font);
        g.cancel = control(L"BUTTON", T(T_CANCEL), BS_PUSHBUTTON | WS_TABSTOP, 432, y + 64, 104, 28, ID_CANCEL, g.font);
        refresh_space();
        SetFocus(g.install);
        return 0;
    }
    case WM_CTLCOLORSTATIC: {       // labels and checkboxes on the window's own background
        HDC dc = (HDC)w;
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, GetSysColor(COLOR_WINDOWTEXT));
        return (LRESULT)GetSysColorBrush(COLOR_WINDOW);
    }
    case WM_COMMAND:
        if (LOWORD(w) == ID_CHANGE) browse();
        else if (LOWORD(w) == ID_FOLDER && HIWORD(w) == EN_CHANGE) refresh_space();
        else if (LOWORD(w) == ID_INSTALL) begin_install();
        else if (LOWORD(w) == ID_CANCEL) SendMessageW(h, WM_CLOSE, 0, 0);
        return 0;
    case WM_APP + 1:
        SetWindowTextW(g.status, T((Text)w, g.payload->version).c_str());
        SendMessageW(g.progress, PBM_SETPOS, (WPARAM)l, 0);
        return 0;
    case WM_APP + 3: {          // Progress::say: a text made by the worker
        std::wstring *text = (std::wstring *)w;
        SetWindowTextW(g.status, text->c_str());
        SendMessageW(g.progress, PBM_SETPOS, (WPARAM)l, 0);
        delete text;
        return 0;
    }
    case WM_APP + 2:
        WaitForSingleObject(g.worker, INFINITE);
        CloseHandle(g.worker);
        g.worker = nullptr;
        g.busy = false;
        if (g.result == L"cancel") { DestroyWindow(h); return 0; }
        if (!g.result.empty()) {
            message(MB_ICONERROR, g.result, h);
            for (HWND c : {g.folder, g.change, g.desktop, g.start, g.install, g.game[0], g.game[1]})
                if (c) EnableWindow(c, !g.locked || (c != g.folder && c != g.change));
            g.exit_code = 2;
            return 0;
        }
        g.finished = true;
        g.exit_code = 0;
        SetWindowTextW(g.cancel, T(T_CLOSE).c_str());
        ShowWindow(g.install, SW_HIDE);
        if (!g_games_summary.empty()) SetWindowTextW(g.status, g_games_summary.c_str());
        if (g.opt.start) {
            if (g_games_failed) message(MB_ICONWARNING, g_games_summary, h);    // before the launcher covers it
            start_launcher(g.opt.folder);
            DestroyWindow(h);
        }
        return 0;
    case WM_CLOSE:
        if (g.busy) {
            if (MessageBoxW(h, T(T_CANCEL_ASK).c_str(), APP_NAME, MB_YESNO | MB_ICONQUESTION) == IDYES) InterlockedExchange(&g.pr.cancel, 1);
            return 0;
        }
        DestroyWindow(h);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(h, m, w, l);
}

static int run_window(const Payload &payload, Options opt, bool locked) {
    g.payload = &payload;
    g.opt = opt;
    g.locked = locked;
    INITCOMMONCONTROLSEX icc = {sizeof(icc), ICC_PROGRESS_CLASS | ICC_STANDARD_CLASSES};
    InitCommonControlsEx(&icc);
    HINSTANCE inst = GetModuleHandleW(nullptr);
    WNDCLASSEXW wc = {sizeof(wc)};
    wc.lpfnWndProc = wnd_proc;
    wc.hInstance = inst;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"OpenRecompSetup";
    wc.hIcon = LoadIconW(inst, MAKEINTRESOURCEW(1));
    wc.hIconSm = wc.hIcon;
    RegisterClassExW(&wc);
    HDC dc = GetDC(nullptr);
    g.dpi = GetDeviceCaps(dc, LOGPIXELSY);
    ReleaseDC(nullptr, dc);
    int games = (payload_has_game(payload, L"t5dr") ? 1 : 0) + (payload_has_game(payload, L"t4") ? 1 : 0);
    RECT r = {0, 0, S(552), S(354 + (games ? 40 + 24 * games : 0))};
    DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
    AdjustWindowRect(&r, style, FALSE);
    int w = r.right - r.left, hgt = r.bottom - r.top;
    HWND wnd = CreateWindowExW(0, wc.lpszClassName, T(T_SETUP_TITLE, payload.version).c_str(), style,
                               (GetSystemMetrics(SM_CXSCREEN) - w) / 2, (GetSystemMetrics(SM_CYSCREEN) - hgt) / 2, w, hgt,
                               nullptr, nullptr, inst, nullptr);
    if (!wnd) return 2;
    ShowWindow(wnd, SW_SHOWNORMAL);
    MSG msg;
    while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
        if (!IsDialogMessageW(wnd, &msg)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
    if (g.finished && !g.opt.start)
        message(g_games_failed ? MB_ICONWARNING : MB_ICONINFORMATION, T(g.updated ? T_UPDATED : T_DONE, payload.version)
                + (g_games_summary.empty() ? std::wstring() : L"\n\n" + g_games_summary));
    return g.exit_code;
}

// ------------------------------------------------------------------------------------------------ main
static bool flag(const std::vector<std::wstring> &args, const wchar_t *name) {
    for (auto &a : args) if (lower(a) == lower(name)) return true;
    return false;
}

static std::wstring value(const std::vector<std::wstring> &args, const wchar_t *prefix) {
    size_t n = wcslen(prefix);
    for (auto &a : args) if (a.size() >= n && lower(a.substr(0, n)) == lower(prefix)) return a.substr(n);
    return L"";
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32);       // never a DLL from the download folder
    HeapSetInformation(nullptr, HeapEnableTerminationOnCorruption, nullptr, 0);
    int argc = 0;
    LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    std::vector<std::wstring> args;
    for (int i = 1; i < argc; i++) args.push_back(argv[i]);
    LocalFree(argv);
    g_silent = flag(args, L"/S");
    pick_language(value(args, L"/lang="));
    std::wstring log = value(args, L"/log=");
    if (!log.empty()) _wfopen_s(&g_log, log.c_str(), L"a, ccs=UTF-8");
    CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
    int code = 2;
    Payload payload = read_payload();
    if (!payload.entries.empty() || FindResourceW(nullptr, L"PAYLOAD", RT_RCDATA)) {
        // ---------------- Setup
        if (!payload.ok) {
            message(MB_ICONERROR, T(T_DAMAGED));
            code = 2;
        } else {
            std::wstring registered = registered_folder();
            Options o;
            std::wstring asked = value(args, L"/D=");
            o.folder = !asked.empty() ? full_path(asked) : default_folder();
            Record r;
            o.desktop = read_record(o.folder, r) ? r.desktop : !flag(args, L"/nodesktop");
            if (flag(args, L"/desktop")) o.desktop = true;
            if (flag(args, L"/nodesktop")) o.desktop = false;
            o.start = !flag(args, L"/nostart");
            std::wstring pick = lower(value(args, L"/games="));
            for (const wchar_t *id : GAME_IDS) {
                bool asked_for = pick.empty() || (L"," + pick + L",").find(std::wstring(L",") + id + L",") != std::wstring::npos;
                if (payload_has_game(payload, id) && asked_for && !flag(args, L"/nogames")) o.games.push_back(id);
            }
            bool locked = !registered.empty() && lower(registered) == lower(o.folder);
            if (g_silent) {
                if (!registered.empty() && lower(registered) != lower(o.folder)) {
                    message(MB_ICONERROR, T(T_ALREADY_HERE));
                    code = 2;
                } else {
                    std::wstring why = check_folder(o.folder, needed(payload));
                    if (!why.empty()) { message(MB_ICONERROR, why); code = 2; }
                    else if (!processes_under(launcher_dir(o.folder)).empty()) { message(MB_ICONERROR, T(T_RUNNING)); code = 3; }
                    else {
                        Progress pr;
                        bool updated = false;
                        std::wstring result = install(payload, o, pr, updated);
                        if (!result.empty()) { message(MB_ICONERROR, result); code = 2; }
                        else { code = g_games_failed ? 4 : 0; if (o.start) start_launcher(o.folder); }
                    }
                }
            } else {
                if (!registered.empty()) o.folder = registered;       // one install per user: an update in place
                code = run_window(payload, o, !registered.empty() || locked);
            }
        }
    } else {
        // ---------------- Uninstall. The program in the install folder cannot delete itself while it runs: it
        // copies itself to the temporary folder, starts that copy and ends; the copy does the work.
        std::wstring me = self_path();
        std::wstring folder = me.substr(0, me.find_last_of(L'\\'));
        std::wstring from = value(args, L"/from=");
        int settings = flag(args, L"/removesettings") ? 1 : (flag(args, L"/keepsettings") ? 0 : -1);
        if (from.empty()) {
            Record r;
            if (!read_record(folder, r)) { message(MB_ICONERROR, T(T_NOT_INSTALLED)); code = 2; }
            else {
                wchar_t temp[MAX_PATH + 1];
                GetTempPathW(MAX_PATH + 1, temp);
                std::wstring copy = join(temp, L"OpenRecomp-uninstall-" + std::to_wstring(GetCurrentProcessId()) + L".exe");
                std::wstring cmd = L"\"" + copy + L"\" \"/from=" + folder + L"\" /parent=" + std::to_wstring(GetCurrentProcessId());
                if (g_silent) cmd += L" /S";
                if (settings == 1) cmd += L" /removesettings";
                if (settings == 0) cmd += L" /keepsettings";
                std::wstring lang = value(args, L"/lang=");
                if (!lang.empty()) cmd += L" /lang=" + lang;
                if (!log.empty()) cmd += L" \"/log=" + log + L"\"";
                STARTUPINFOW si = {sizeof(si)};
                PROCESS_INFORMATION pi = {};
                if (CopyFileW(me.c_str(), copy.c_str(), FALSE)
                    && CreateProcessW(copy.c_str(), &cmd[0], nullptr, nullptr, FALSE, 0, nullptr, temp, &si, &pi)) {
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                    code = 0;
                } else {
                    message(MB_ICONERROR, T(T_FAILED, last_error_text(GetLastError())));
                    code = 2;
                }
            }
        } else {
            DWORD parent = (DWORD)wcstoul(value(args, L"/parent=").c_str(), nullptr, 10);
            if (parent) {
                HANDLE p = OpenProcess(SYNCHRONIZE, FALSE, parent);
                if (p) { WaitForSingleObject(p, 30000); CloseHandle(p); }
            }
            code = uninstall(full_path(from), settings);
            if (code == 0) {
                std::wstring un = join(full_path(from), UNINSTALL_EXE);
                for (int i = 0; i < 20 && exists(un) && !DeleteFileW(un.c_str()); i++) Sleep(250);
                RemoveDirectoryW(full_path(from).c_str());
            }
        }
    }
    CoUninitialize();
    if (g_log) fclose(g_log);
    return code;
}
