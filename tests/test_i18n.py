import ast
import json
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.base import Adapter
from openrecomp.nav import Game, Nav
from openrecomp.nav_common import SECTION_TITLES


ROOT = Path(__file__).parents[1]


def untranslated_literals(source):
    """Check every Python string, exempting code identifiers and external-data formats."""
    tree = ast.parse(source)
    ignored = set()
    errors = []
    english = i18n.catalog("en")

    def ignore(node):
        ignored.update(id(child) for child in ast.walk(node))

    def ignore_protocol(node, values):
        if isinstance(node, ast.Constant) and node.value in values:
            ignore(node)
        elif isinstance(node, ast.IfExp):
            ignore_protocol(node.body, values)
            ignore_protocol(node.orelse, values)

    def check_display(node, protocol=()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in protocol and any(ch.isalpha() for ch in node.value) and not node.value.startswith("@") and node.value not in ("1080p", "1440p", "4K", "SLUS-20328", "T5DR Online"):
                errors.append((node.lineno, node.value))
        elif isinstance(node, ast.IfExp):
            check_display(node.body, protocol)
            check_display(node.orelse, protocol)

    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            ignore(node)  # docstrings
        elif isinstance(node, ast.FunctionDef) and node.name == "quick_settings":
            for child in ast.walk(node):
                if isinstance(child, ast.Return):
                    ignore(child.value)  # adapter setting IDs, never display labels
        elif isinstance(node, ast.Subscript):
            ignore(node.slice)  # field names, never their values
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None:
                    ignore(key)
        elif isinstance(node, ast.Tuple) and len(node.elts) == 2:
            # Option pairs carry a stable setting value and a catalog label.
            label = node.elts[1]
            if isinstance(label, ast.Constant) and isinstance(label.value, str) and label.value.startswith("@"):
                ignore(node.elts[0])
        elif (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
              and isinstance(node.left, ast.Constant)
              and node.left.value in ("@t4.tools.", "@t4.network.", "@netext.")):
            ignore(node.left)  # fixed catalog families; complete keys remain checked below
        elif isinstance(node, ast.Compare):
            for child in (node.left, *node.comparators):
                if isinstance(child, (ast.Constant, ast.Tuple, ast.List)):
                    ignore(child)  # action IDs and core protocol values
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id in ("GLYPHS", "TRAIL", "OSK", "ONLINE_KEYS", "BACK_SOURCE", "__all__") for t in node.targets):
                ignore(node.value)  # physical button names, keyboard keys, exports
            if any(isinstance(t, ast.Name) and t.id == "PREFLIGHT_SCRIPT" for t in node.targets):
                ignore(node.value)  # internal PowerShell wrapper, never screen copy
            if any(isinstance(t, ast.Name) and t.id in ("SECTION_TITLES", "DEVICE_LABEL", "OSK_ACTIONS") for t in node.targets):
                for child in ast.walk(node.value):
                    if isinstance(child, ast.Constant) and child.value in english:
                        ignore(child)  # tables of catalog keys
            if any(isinstance(t, ast.Attribute) and t.attr in ("screen", "overlay", "device", "pad_kind", "confirm_kind") for t in node.targets):
                if isinstance(node.value, ast.Constant):
                    ignore(node.value)
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Attribute) and node.targets[0].attr == "screen":
                ignore_protocol(node.value, ("start", "hub"))
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript):
                target = node.targets[0].value
                if isinstance(target, ast.Attribute) and target.attr == "sec" and isinstance(target.value, ast.Name) and target.value.id == "self":
                    ignore_protocol(node.value, SECTION_TITLES)
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript) and isinstance(node.targets[0].slice, ast.Constant) and node.targets[0].slice.value == "overlay":
                if isinstance(node.value, ast.Constant) and node.value.value == "dialog":
                    ignore(node.value)  # binding uses the dialog view protocol, not a display label
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in ("getattr", "hasattr") and len(node.args) > 1:
                ignore(node.args[1])  # attribute names; a displayed fallback is still checked
            elif name in ("get", "setdefault", "getenv", "pop", "startswith", "import_module", "strftime", "compile", "match", "expanduser") and node.args:
                ignore(node.args[0])
            elif name in ("prompt", "glyph", "_ask", "_open_picker", "act", "on_setup") and node.args:
                ignore(node.args[0])
            elif name == "_go" and len(node.args) > 1:
                ignore(node.args[1])
            elif name == "say" and node.args:
                check_display(node.args[0])
            elif name == "message" and node.args:
                for key in ast.walk(node.args[0]):
                    if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value not in english:
                        errors.append((key.lineno, key.value))
                ignore(node.args[0])
            for kw in node.keywords:
                if kw.arg in ("label", "hint", "lead", "title", "verb", "kicker", "k", "v", "value", "note", "primary", "status", "version", "players", "last", "result", "empty", "bar"):
                    # Friend snapshots carry a protocol enum; Nav translates that enum.
                    friend_record = (name == "dict" and kw.arg == "status"
                                     and {item.arg for item in node.keywords}
                                     == {"name", "status", "activity", "invite", "retry"})
                    # Source checks return a reload instruction alongside localized errors.
                    source_record = (name == "dict" and kw.arg == "result"
                                     and {item.arg for item in node.keywords}
                                     == {"running", "result", "id", "ok"})
                    if not friend_record:
                        check_display(kw.value, ("reload",) if source_record else ())
                if kw.arg in ("id", "kind", "opens", "encoding", "errors", "mode"):
                    ignore(kw.value)

    # These are filenames, environment variables, technical units, and protocol identifiers.
    technical = {
        "netext_options", "online_feel", "net_line", "netext_forget_confirm", "netext_forget_preview",
        "netext_forget_cancel", "max_ping", "no_wifi", "steady", "responsive", "balanced", "smooth",
        "netext_set:", "netext_", "mm_filters", "forget_me", "feature_", "quick_match", "ranked_match",
        "rb_cost.txt", ".t5_netext", r"[a-z]{2,3}(?:-[A-Z]{2})?",
        "_items_", "_view_", "source:", "text:", "space", "del", "done", "random", "reload", "nt", "utf-8", "w", "replace",
        "folder", "file", "dir", "action", "dev", "auto", "1080p", "1440p", "4K", "SLUS-20328", "T5DR Online",
        "launcher", "runtime", "core.py", "t4core.py", "t4_launcher.pyw", "t5dr_launcher.pyw", "t5dr.exe",
        "reports", "t4-report-", "Tekken 4 Online",  # T4 report folder, temporary prefix and lobby metadata
        "T5DR Online.exe", "T5DROnline", "online.json", "release.json", "lobby", "t5lobby", "tools", "data",
        "cache", "fighters", "fighters.json", "python", "python.exe", "t4", "t5dr", "hero.png",
        "build_game.py", "ps3recomp", "-c", "from Crypto.Cipher import AES",
        "Downloads", "Desktop", "APPDATA", "OPENRECOMP_T4_ROOT", "OPENRECOMP_T5DR_ROOT", "T5_ONLINE_DIR",
        "%USERPROFILE%/Downloads/T5DR-Online-*", "%USERPROFILE%/Desktop/T5DR-Online-*", "T5DR-Online-*",
        ".json", ".iso", "*.iso", ".pkg", ".rap", ".openrecomp.tmp", "logs\\build_game.log",
        "--search", "-Force", "openrecomp", "taskkill", "/T", "/F", "/PID", "W", "L",
        "controls_edit.py", "controls_ui.py", "padmap.py", "padnav.py", "__init__.py", ".py", "replays.py", "launcher.log",
        "controls_edit", "controls_ui", "t5lobby.padmap", "t5lobby.padnav", "problem_report", "problem_check",
        "Context", "settings_lines", "build_info_for", "discover", "build", "desktop_dir",
        "controls_path", "DeviceRef", "load", "sources", "table", "bind", "save", "mask_text",
        "default_sources", "step", "drain", "update",
        # the Pad bindings page's row kinds, adapter methods and controls.ini option names (nav_controls_page)
        ":controls", "setting", "slot", "menu", "bindings", "generic", "socd", "stick", "clear_binding", "reset_controls",
        "apply_preset", "set_control_player", "set_control_option", "test", "keyboard", "bindcapture", "attack", "macro", "custom", "game_key",
        "idle", "waiting", "ready", "conflict", "multi", "timeout", "disconnected", "done", "ok",
        "check", "report", "problem", "play", "controls", "support", "error", "saved", "none", "sent", "support_note", "support_contact",
        "online_", "online_name", "online_password", "online_server", ":online",
        "offline", "connecting", "logged_in", "searching", "cancelling", "matched", "kicked", "match_found",
        "login_", "search_", "login_guest", "login_account", "login_register", "login_saved", "search_casual", "search_ranked",
        "registration", "recovery_codes", "acknowledge_recovery", "recovery_code:",
        "cancel", "logout", "casual", "ranked", "guard", "RequestError",
        "tasklist", "/FI", "IMAGENAME eq t5dr.exe", "/FO", "CSV", "/NH",
        "t5lobby.client", "t5lobby.buildid", "t5lobby.servers", "t5lobby.proto", "127.0.0.1:7781",
        "openrecomp-lobby", "openrecomp-lobby-close", ".tmp", "logged in from another place",
        "auth_failed", "insecure", "bad_name", "name_taken", "rate_limited", "version_mismatch",
        "proto_mismatch", "server_full", "busy_server", "unavailable", "refused",
        "online_chat", "challenge:", "join_room:", "chat:",
        "refresh_players", "refresh_rooms", "accept_challenge", "decline_challenge",
        "create_room", "leave_room", "send_chat", "no_players", "no_rooms", "no_chat",
        "start_match", "cancel_match", "stop_match", "result_win", "result_loss", "result_none", "return_lobby",
        "t4_rematch", "t4_rematch_decline",  # internal worker operations; the existing rematch labels are translated
        "result_game", "t4_result-", "[^A-Za-z0-9_-]",       # the T4 game's own result file (t4_online)
        "starting", "playing", "result", "result_sent",
        "t4lobby", "online-t4.json", "hashes.json", "toolchain.json", ".client", ".buildid", ".servers", ".proto", "IMAGENAME eq ",
        "net.log", "rb_frames.log", "host:", "join:", "manual", "start_game",
        "game_started", "game_playing", "nat_fallback", "direct", "lan", "r", "NETSUMMARY",
        r"\bconnected\b", r"(?:frames|frame)\s*[=: ]\s*(\d+)", r"mismatches\s*[=: ]\s*(\d+)",
        r"\blive\s+(\d+)", r"(?<!resim )\b(?:frames|frame)\s*[=: ]\s*(\d+)",
        "peer_timeout", "peer_quit", "no_peer", "build_mismatch",
        "frames", "desync", "rb", "openrecomp-t4-stop",
        "file_or_folder", "available", "checking", "installing", "current", "unconfigured",
        ".zip", "con", "prn", "aux", "nul", "conin$", "conout$", "com", "lpt",
        "sha256", "installs", "pending-", "xb", "_openrecomp_t4core_", "core", "replays", ".openrecomp-",
        "online_room_name", "online_room_password", "online_room_code", "online_friend_name", "_password",
        "create_password_room", "create_code_room", "join_room_code", "room_invite_code",
        "refresh_friends", "add_friend", "remove_friend", "invite_friend", "invite_room",
        "accept_friend", "decline_friend", "cancel_friend", "accept_invite", "decline_invite", "cancel_invite",
        "no_friends", "private_rooms", "friends", "incoming", "outgoing", "_online_friend_",
        "password", "code", "online", "in_match", "rematch", "logs", ".match_driver", ".t4game",
        "continue", "won", "lost", "draw", "t5_ready", "t5_answer", "t5_rematch", "t5_return", "t5_driver",
        "openrecomp-t5-match", "openrecomp-t5-match-close", "openrecomp-t5-state", "unqueue", "reconnecting", "chapterNext", "chapterPrev",
        # the lobby page's region and line ids (nav_online_layout) and the rank plate file name
        "card", "chat_lobby", "chat_toggle", "compose", "f:", "find", "friend_bar", "game_setup", "game_update", "h:",
        "hist_page", "i:", "lb_page", "lb_sort", "mention", "online_profile", "online_room_", "online_tour_", "p:",
        "pcompose", "preport", "private_open", "profile_player", "ranked_strict", "room_bar", "search", "spec_",
        "spec_watch_tour", "stats_mode", "stats_sort", "tabs", "rank_%02d.png", "ranks", "ping_measured",
        # T4 ranked (t4_online): the badges' folder and file names, the found match's side list
        "ui", "assets", "t4_rank_%02d.svg", "sides",
        # the settings page's group ids and its own rows (nav_settings_page)
        "display", "controls", "online", "audio", "offline", "replays", "updates", "advanced", "pad_bindings",
        "launcher_update", "game_updates", "test_versions", "screen_side", "always_left", "reset:replay_dir",
        "check_all", "settingsGroup", "groups", "tier_for", "threshold", "field", "login_show_password",
        "login_remember", "login_forgot", "login_back", "login_saved", "login_account", "login_register", "login_guest",
        "online_status", "online_name", "online_password", "online_server", "mode_direct", "native", "auto_login", "recover",
        "login", "main", "remember",
        "reconnected",
        "[a-z0-9_-]+", "invalid game id", "OpenRecomp-FGC-launches", ".lock", "a+b",
        "openrecomp-game-reservation",
        "online_address", "host", "join", "collect_logs", "disconnect", "direct_back", "mode_lobby", "mode_direct",
        "vendor", "OPENRECOMP_T4_SERVER", "OPENRECOMP_T5_SERVER", "t5_lobby_server", "t5dr-servers/1", "ca", "[0-9A-Za-z.+-]{1,40}",
        "TEKKEN4_RUNAHEAD", "TEKKEN4_NET_DIAG", "TEKKEN4_NET_HASH_PROFILE",
        "TEKKEN4_NET_COST_PROFILE", "TEKKEN4_NET_COALESCE", "TEKKEN4_NET_STRICT_HELLO",
        "TEKKEN4_RB_AUDIO_TIMELINE", "TEKKEN4_NET_DELAY_MATCH", "TEKKEN4_NET_SIM_SAFE_WAIT",
        "TEKKEN4_NET_END", "TEKKEN4_NET_SHOTS", "TEKKEN4_NET_DESYNC_DUMP", "TEKKEN4_NET_SIM",
        "compiler", "iso", "udp", "checked", "stopping", "peer", "t4-online", "game", "disc", "SLUS_203.28",
        "net_preflight.ps1", "t4net_build.json", "check-", "check.ps1", "preflight.json",
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
        "-Tool", "-BuildStamp", "-Iso", "-Elf", "-Output", "-Peer", "-Port", "-AsHost",
        "-RunDir", "-OutputDirectory", "collect_test_logs.ps1", "openrecomp-t4-direct",
        "build_id", "elf_sha1", "net", "strict_hello", "delay_match", r"[0-9a-f]{16}",
        r"[A-Za-z0-9_.+ -]{1,100}", r"[0-9a-f]{64}", r"[0-9a-f]{40}",
        "stdout.txt", "stderr.txt", "wb",
        # The Build page: card ids and card states (nav_build), the tools pipeline's install outcomes.
        "files", "more", "todo", "work", "wait", "failed", "reboot", "--silent",
        "launcher.json", "settings.json", "controls.json", "servers.json", "t5dr_build.json", "PS3_CONTROLS",
        ".settings-", ".controls-", "_OpenRecompSettings", "_coexist_defaults", "code_id", "same", "different",
        "unknown", "coexistence", "coexistence_folder", "t5dr_settings_copy",
        r"[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?",
    }
    # Existing-install discovery reads these exact metadata fields, registry keys,
    # shell folder names and shortcut formats; none are player-facing copy.
    technical.update({
        "root", "install", "install_dir", "install_path", "installlocation", "t5dr_root", "out_dir",
        "recent", "recent_folders", "recent_paths", "last_folder", "last_directory", "last_dir",
        "game_folder", "game_dir", "location", "installdir", "recent_directories",
        "displayicon", "uninstallstring", "Microsoft", "Windows", "Recent", "Documents",
        "desktop", "personal", "{374de290-123f-4565-9164-39c4925e467b}",
        "<5I", "<I", "<H", "utf-16-le", "mbcs", ".lnk",
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU",
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        r"Software\T5DR Online", r"Software\T5DROnline", r"Software\T5DR",
        r"Software\T5DR Online\Setup", r"Software\T5DROnline\Setup",
        r"Software\T5DR Online\Launcher", r"Software\T5DROnline\Launcher",
        r"Software\Microsoft\Windows\CurrentVersion\App Paths\T5DR Online.exe",
    })
    # Exact native-client actions, payload fields and runtime names. Display contexts
    # are checked above even when their value is a recognized protocol token.
    technical.update({
        ".t5_accounts", ".t5_challenges", ".t5_community", ".t5_profiles", ".t5_rules", ".t5_spectating",
        ".t5_tournaments", "__file__", "_account_blocks", "_game_guard", "_online_account", "_online_api",
        "_online_authorized", "_online_busy", "_online_challenge", "_online_character_locked",
        "_online_community_pair", "_online_community_prefs", "_online_driver", "_online_driver_busy",
        "_online_driver_events", "_online_driver_lock", "_online_driver_results", "_online_early_start",
        "_online_ingame_menu", "_online_invites", "_online_leaving_set", "_online_match",
        "_online_match_client_options", "_online_match_id", "_online_name", "_online_next_authorized",
        "_online_outgoing_invite", "_online_phase", "_online_ready_check", "_online_rematch",
        "_online_rules_match", "_online_set", "_online_set_slot", "_online_start_seen", "_online_started_path",
        "_online_tours", "_spec_epoch", "_t5_challenge_prefs", "_t5_profile", "_t5_profile_pages", "accept:",
        "accept_friend:", "accept_invite:", "accepted", "access", "account", "account_block", "account_blocks",
        "account_change_password", "account_new_codes", "account_recovery", "account_tools",
        "account_unblock:", "accounts", "accounts_refresh_blocks", "active", "activity", "adapter", "after",
        "all", "always_left", "any", "asdfghjkl-", "ask_result", "attention", "auto_skip",
        "auto_skip_after_round", "auto_skip_ok", "auto_skip_supported", "auto_spectate",
        "auto_unless_declined", "automatic", "away", "back", "badge", "badges_ok", "before", "best_of",
        "block", "blocks", "board", "borderless", "boss", "both_confirm", "both_left", "bracket",
        "build_failed", "build_ok", "built", "bumped", "busy", "call", "called", "can_create", "can_manage",
        "cancel_build", "cancel_challenge", "cancel_challenge:", "cancel_friend:", "cancel_watch", "cancelled",
        "capabilities", "casual_first_to", "casual_losses", "casual_ok", "casual_sets_ok", "casual_side",
        "casual_stage", "casual_stages", "casual_supported", "casual_wins", "challenge", "challenge_",
        "challenge_delay", "challenge_delay_max", "challenge_option:", "challenge_preferences",
        "challenge_update", "challenged", "champion", "change_password", "char", "character_locked", "chars",
        "chat", "check:", "checked_in", "checkin", "checkin_minutes", "checkin_opens", "checks",
        "choose_named", "client", "client_created", "client_options", "close", "close_profile", "codes", "col",
        "community", "community_", "community_apply", "community_back_in_line", "community_bar",
        "community_copy_code", "community_create", "community_fighter:", "community_kick:",
        "community_member:", "community_new_code", "community_option", "community_option:", "community_pair",
        "community_pair_option", "community_pair_option:", "community_sit_out", "community_stats",
        "community_table:", "community_totals", "confirm", "confirmed", "connection", "count", "crash",
        "crash_repeat", "create", "create_hint", "cycler", "damaged", "date", "deadline", "decline_friend:",
        "decline_invite:", "declined", "DEFAULTS", "delay", "delay_max", "delay_supported", "delta",
        "dealt", "descending", "detail", "detail:", "detail_dirty", "direct_ip", "dirs", "disabled", "display",
        "disputed", "double", "down", "dq", "draws", "dry_open", "dry_start", "early_quit",
        "early_quit_repeat", "effects", "end", "ended", "entrant", "entrants", "expired", "expires", "exts",
        "fallback", "feature_accounts:", "feature_accounts:blocks", "feature_accounts:codes",
        "feature_accounts:password", "feature_accounts:recover", "feature_challenges:",
        "feature_challenges:cancel", "feature_challenges:send", "feature_community:",
        "feature_community:community_back_in_line", "feature_community:community_create",
        "feature_community:community_pair", "feature_community:community_sit_out", "feature_profile:",
        "feature_rules:", "feature_spectate:", "feature_spectate:prefs", "feature_spectate:start",
        "feature_spectate:watch", "feature_tour:", "feature_tour:accept:", "feature_tour:list", "fight",
        "fighter", "fingerprint", "finished", "firewall_suspect", "first_to", "for_history", "forfeit",
        "format", "fraction", "friend", "friend_incoming", "friend_list", "friend_outgoing", "friend_request",
        "friend_status", "friend_update", "from", "game_closed", "game_is_running", "game_state",
        "game_supports_auto_skip", "game_supports_ingame_ui", "game_supports_life150", "game_supports_pick",
        "game_supports_rules", "games", "generation", "group", "guesses", "guest", "handicap", "handicap_ok",
        "has_friends", "has_next", "has_spectate", "has_stats", "heading", "hidden", "hint", "history", "hold",
        "id", "images", "in", "in_line", "index", "ingame_pick", "ingame_rematch", "ingame_rematch_ok",
        "ingame_ui_fallback", "ingame_ui_ready", "input_delay", "INPUT_DELAYS", "inputs", "internal_res",
        "internal_res_set", "invite", "invite_friend:", "invite_room:", "invite_update", "invite_wait",
        "invited", "invites", "kb", "key", "kind", "known", "label", "language", "last", "lead", "leaderboard",
        "leaderboard_", "leaderboard_next", "leaderboard_previous", "leaderboard_refresh", "leaderboard_sort:",
        "leave", "leave_set", "left", "life", "life_max", "life150", "line", "list", "list_dirty", "listed",
        "live", "loading", "lobby_state", "locations", "lock", "locked", "losers_rounds", "loss", "losses",
        "low_priority", "lower", "lowest", "made", "main", "match", "match_cancel", "match_flow", "match_id",
        "match_result", "match_reveal", "match_rules", "match_start", "matches", "matches_24h", "max_players",
        "max_size", "maximized", "maximum", "me", "members", "mention:", "mentioned", "mentions",
        "mentions_ok", "message", "mode", "ms", "multi_challenge_ok", "mute", "my_room", "name", "nat",
        "nat_error", "nat_relay", "nat_result", "nat_start", "nat_status", "nat_upgrade", "native",
        "native_hint", "needs_rebuild", "netcode", "new_recovery_codes", "next", "next_detail", "next_list",
        "nickname", "no_connection", "no_ranked_chars", "no_report", "no_report_repeat", "no_result",
        "no_return", "no_statistics", "not_allowed", "note", "notice", "number", "off", "offer_ingame_ui",
        "offered", "offline_action", "offset", "on", "onesided", "online.challenge_ft", "online.community",
        "online.community_hint", "online.first_to", "online.ingame_back_in_line", "online.ingame_expired",
        "online.ingame_next", "online.ingame_sit_out", "online.match_health", "online.ready_hint",
        "online.rematch", "online.rematch_auto", "online.rematch_confirm", "online.rematch_countdown",
        "online.rotation_queue", "online.rotation_winner", "online.set_game", "online.set_next",
        "online.set_score", "online.start_match", "online.waiting_peer_ready", "online_block_name",
        "online_current_password", "online_fighter", "online_fingerprint", "online_identity",
        "online_new_password", "online_profile_name", "online_recovery_code", "online_repeat_password",
        "online_status", "online_supported", "online_tour_clock", "online_tour_dq", "online_tour_name",
        "open_challenges", "opening", "openrecomp-unwatch", "opens", "opp_char", "opponent", "opponent_left",
        "opponent_ready", "options", "organizer", "origin", "osk", "outgoing_invite", "over", "override",
        "owner", "owner_id", "p", "p1", "p2", "page", "pair", "path", "peak_rank", "peer_delay_max",
        "peer_lost", "pending", "phase", "picture_error", "pin", "ping", "pkg", "place", "player", "players",
        "players_24h", "policy", "poll", "practice", "preferences", "previous", "primary", "private",
        "private_rooms_ok", "profile", "profile_", "profile_board:", "profile_char:", "profile_history:",
        "profile_history_next", "profile_history_offset", "profile_history_previous",
        "profile_history_replay:", "profile_load", "profile_player:", "profile_ranked_char:", "profile_self",
        "profile_stats:", "profile_stats:all", "profile_summary", "profiles", "prompts", "provisional",
        "queue", "quit", "qwertyuiop", "rank", "ranked_chars", "ranked_games", "ranked_losses", "ranked_wins",
        "rap", "rated", "rating", "rd", "ready_check", "ready_timeout", "reason", "rebuild", "reconnecting",
        "record", "recover_account", "recovery_codes_left", "refresh", "relay", "relay_full", "rematch_offer",
        "rematch_policy", "rematch_rules", "rematch_ui", "rematch_window", "remove_friend:", "replay",
        "replay_dir", "replay_entries", "replay_group", "replay_id", "replay_loss", "replay_names",
        "replay_win", "reply", "reset", "reset:", "resolved", "retry", "rev", "right", "role", "rollback",
        "room", "room_code", "room_limits", "room_tables", "room_tables_ok", "rooms", "roots", "rotation",
        "round", "rounds", "row", "rows", "rp", "rules", "rules_life", "rules_life:", "run", "running",
        "saved_available", "score", "screen_side", "score_mismatch", "seconds", "seed", "seeding", "seeds", "selected",
        "selected_set", "self", "send", "send_challenge", "server", "servers", "session", "sessions", "set",
        "set_auto_skip_after_round", "set_casual_prefs", "set_end", "set_life", "set_next", "set_restart",
        "set_spectate_prefs", "set_wins", "sets", "sets_supported", "setting:", "shadows", "side", "signup",
        "single", "size", "skip", "slot", "social", "sort", "source", "spec_count", "spec_end",
        "spec_generation", "spec_ready", "spec_stop", "spec_watch", "spec_watch_", "spec_watch_friend:",
        "spec_watch_room:", "spec_watch_table:", "spec_watch_tour:", "spectate", "spectating", "spectators",
        "spectators_ranked", "stage", "stage_blur", "stages", "stale", "standings", "start", "start_minutes",
        "start_time", "state", "stats", "stats_", "stats_mode:", "stats_refresh", "stats_sort:", "status",
        "steps", "stop_game", "stopped", "stream", "sub", "t", "t5.delay_frames", "t5_", "t5_leave_set",
        "t5lobby.fighter_art", "tables", "target", "targets", "text", "ticket", "tid", "time", "title",
        "tls_fingerprint", "token", "too_short", "tour_", "tour_abandon_change", "tour_accept", "tour_accept:",
        "tour_access", "tour_admin", "tour_call", "tour_call_end", "tour_cancel:", "tour_changed",
        "tour_checkin", "tour_checkin:", "tour_confirm", "tour_confirm:", "tour_create", "tour_create_hint",
        "tour_dq", "tour_dq:", "tour_entrant:", "tour_get", "tour_join", "tour_leave", "tour_leave:",
        "tour_list", "tour_notice", "tour_option", "tour_option:", "tour_refresh", "tour_refresh_detail",
        "tour_refresh_detail:", "tour_select", "tour_select:", "tour_select_set", "tour_select_set:",
        "tour_standing:", "tour_start:", "tournament", "tournaments", "training", "training_ok", "udp_blocked",
        "udp_unreachable", "unblock", "unlock_items", "unlock_stages", "unverified", "unwatch", "up", "value",
        "verb", "version", "version_tag", "void", "voids_24h", "vsync", "warning", "watch",
        "watch-status.json", "watch-verdict.json", "welcome", "when", "win", "win_rate", "win0", "win1",
        "window", "window1080", "window1440", "winner", "winrate", "wins", "wins_needed", "wish", "wrong",
        "wrong_passwords", "x", "you", "you_char", "your_match", ".2f", ".1f", ".0f", "+g",
        ".t5_moderation", ".t5_private_chat", "feature_moderation:", "feature_private:",
        "moderation", "moderation_block:", "moderation_mute:", "moderation_muted:",
        "moderation_notice", "moderation_refresh_mutes", "moderation_unmute:", "mutes", "mutes_ok",
        "online_private_chat", "online_private_report_reason", "private_", "private_chat",
        "private_close", "private_empty", "private_message", "private_message:", "private_open:",
        "private_read", "private_report", "private_reports", "private_select:", "private_send",
        "receipt", "to",
    })
    technical.update({
        # another launcher of the same game (other_launchers): row ids, choices, lock files, Windows structure fields
        "other_here", "other_keep", "other", "here", "kernel32", "ntdll", "dwSize", "cntUsage", "pid", "heap",
        "module", "threads", "ppid", "prio", "flags", "exe", "length", "buffer", "%s-%d.lock",
        "OpenRecomp-FGC-presence", "openrecomp-other-launchers", "online-",
    })
    technical.update({
        ".exe", ".png", ".jpg", ".jpeg", ".webp", "preview", "library_repository", "library_folder", "library_source", "library_manage",
        "library_loading", "library_preview", "library_remove", "library_update",
    })
    technical.update({
        "T4", "tools/build_game.ps1", "tools/iso_extract.py", "tools/net_preflight.ps1", "config", "patches",
        "t4-source", "-I", "-B", "--check", "OK", "build_game.ps1", "iso_extract.py", "deps", "ps2recomp", "out",
        "ps2xRuntime", "ps2EntryRunner.exe", "TEKKEN 4", "gl", "locks", "OpenRecomp", "4k", "fxaa",
        "sound", "unlock_all", "progressive", "debug_panel", "TEKKEN4_SOUND", "TEKKEN4_UNLOCK_ALL",
        "TEKKEN4_PROGRESSIVE", "PS2X_DEBUG_PANEL", "exclusive",
        "git", "cmake", "ninja", "vs2022", "msvc", "utf-8-sig", "report-", "T4-test-logs-",
        "CXX_ID=", "CXX_VERSION=", "toolchain", "direct:", "network:", "firewall", "forward", "tailscale",
        "FAILED at step ", "Full log:",
        "_title", "tools:recheck", "tool:", "tool_copy:",
        "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity", "winget",
        "not a winget install", r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment", "Environment", "Path",
        "winget install --id Python.Python.3.12 --exact",
        "winget install --id Git.Git --exact",
        "winget install --id Kitware.CMake --exact",
        "winget install --id Ninja-build.Ninja --exact",
        ('winget install --id Microsoft.VisualStudio.2022.BuildTools --exact '
         '--override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"'),
        r"(?<![\d.])(\d+\.\d+(?:\.\d+)*)(?!\d)", r"14\.\d+\.\d+",
        "C:/Program Files (x86)", "C:/Program Files", "Microsoft Visual Studio", "Installer", "vswhere.exe",
        "-latest", "-products", "-version", "[17.0,18.0)", "-requires",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath", "installationVersion",
        "VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt", "VC/Tools/MSVC", "bin/Hostx64/x64/cl.exe",
        "Windows Kits/10", "Include", "um/Windows.h", "Lib", "um/x64/kernel32.lib", "--version",
        "CMake/bin", "Microsoft/WinGet/Links", "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin",
        "Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja", "VC/Auxiliary/Build/vcvars64.bat",
    })
    formats = {
        'f"{platform} RECOMP"', 'f"slot{i}"', 'f"{self.game.id}:{self.section()}"', 'f"{letter}:\\\\"',
        'f"v{version}"', 'f"face_{gid:02d}.png"', 'f"hero_{gid:02d}.png"',
        'f"{e.score[0]}:{e.score[1]}"', 'f"{a} – {b}"', 'f"{m.group(2)}.{m.group(1)}., {m.group(3)}"',
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            if ast.get_source_segment(source, node) in formats:
                ignore(node)
    for node in ast.walk(tree):
        if id(node) in ignored or not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        if not any(ch.isalpha() for ch in value):
            continue
        if value.startswith("@"):
            if value[1:] not in english and value != "@language.":
                errors.append((node.lineno, value))
        elif re.fullmatch(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", value):
            continue  # hexadecimal colours, never translated text
        elif value not in technical:
            errors.append((node.lineno, value))
    return errors


class FakeAdapter:
    native_label = ""

    def source_state(self):
        return dict(running=False, result="", id="", ok=False)

    def found(self):
        return True

    def ready(self):
        return True

    def status(self):
        return {"status": "Ready", "version": "1", "players": "No", "last": "Never", "detail": "Ready."}

    def running(self):
        return False

    def hero(self):
        return ""

    def recent_results(self):
        return []

    def settings(self):
        return []

    def quick_settings(self):
        return []


def game():
    manifest = {"id": "test", "short": "Test", "accent": "#ffffff", "numeral": "T", "title": "Test", "subtitle": "", "sections": ["play"]}
    return Game(manifest, FakeAdapter())


class Catalogs(unittest.TestCase):
    def test_catalogs_have_equal_keys_and_placeholders(self):
        catalogs = {code: json.loads((ROOT / "openrecomp" / "i18n" / (code + ".json")).read_text(encoding="utf-8")) for code in i18n.LANGUAGES}
        keys = set(catalogs["en"])
        for code, entries in catalogs.items():
            self.assertEqual(set(entries), keys, code)
            for key in keys:
                self.assertEqual(set(re.findall(r"{(.*?)}", entries[key])), set(re.findall(r"{(.*?)}", catalogs["en"][key])), (code, key))

    def test_missing_translation_falls_back_to_english(self):
        english = i18n.catalog("en")
        german = dict(i18n.catalog("de"))
        german.pop("quick_access")
        with mock.patch("openrecomp.i18n.catalog", side_effect=lambda code: english if code == "en" else german):
            self.assertEqual(i18n.text("de", "quick_access"), "Quick access")

    def test_templates_keep_native_countdown_placeholders_in_every_language(self):
        for code in i18n.LANGUAGES:
            for key in ("online.rematch_countdown", "online.set_next"):
                with self.subTest(code=code, key=key):
                    template = i18n.template(code, key)
                    self.assertEqual(template, i18n.catalog(code)[key])
                    self.assertIn("{seconds}", template)
                    self.assertEqual(template.format(seconds=5), i18n.text(code, key, seconds=5))

    def test_template_uses_localized_english_and_key_fallbacks_without_formatting(self):
        english = {"countdown": "Next in {seconds}", "fallback": "Wait {seconds}"}
        german = {"countdown": "Weiter in {seconds}"}
        with mock.patch("openrecomp.i18n.catalog", side_effect=lambda code: english if code == "en" else german):
            self.assertEqual(i18n.template("de", "countdown"), "Weiter in {seconds}")
            self.assertEqual(i18n.template("de", "fallback"), "Wait {seconds}")
            self.assertEqual(i18n.template("de", "missing.key"), "missing.key")

    def test_shared_input_delay_wording_matches_t5dr(self):
        expected = {
            "de": "Online-Input-Delay", "es": "Input delay online", "fr": "Input delay en ligne",
            "ja": "オンライン入力遅延", "ko": "온라인 입력 지연", "pt-BR": "Input delay online",
        }
        for code, label in expected.items():
            self.assertEqual(i18n.text(code, "input_delay"), label, code)

    def test_switching_language_changes_the_view(self):
        nav = Nav([game()], language="en")
        nav.act("social")
        before = nav.view()
        nav.act("confirm")
        after = nav.view()
        self.assertNotEqual(before, after)
        self.assertEqual(after["drawer"]["rows"][0]["value"], "Deutsch")

    def test_language_cycles_both_ways_and_notifies(self):
        changed = []
        nav = Nav([game()], language="en", on_language=changed.append)
        nav.act("social")
        for action, expected in (("left", "pt-BR"), ("right", "en"), ("confirm", "de")):
            nav.act(action)
            self.assertEqual(nav.language, expected)
        self.assertEqual(changed, ["pt-BR", "en", "de"])

    def test_unknown_at_strings_are_untouched_in_the_view(self):
        nav = Nav([game()], language="de")
        nav.game.m["title"] = "@Player"
        nav.say("@folder/path")
        view = nav.view()
        self.assertEqual(view["shelf"]["tiles"][0]["name"], "@Player")
        self.assertEqual(view["toast"], "@folder/path")
        self.assertEqual(i18n.localize(["@Player", "@folder/path", "@missing.key"], "ja"),
                         ["@Player", "@folder/path", "@missing.key"])
        self.assertEqual(i18n.localize("@quick_access", "de"), "Schnellzugriff")

    def test_placeholder_reaches_the_view_in_every_language(self):
        expected = {
            "en": "@Player is starting.", "de": "@Player startet.", "es": "Iniciando @Player.",
            "fr": "Lancement de @Player.", "ja": "@Playerを起動しています。",
            "ko": "@Player을 시작합니다.", "pt-BR": "Iniciando @Player.",
        }
        for code in i18n.LANGUAGES:
            nav = Nav([game()], language=code)
            nav.say(i18n.message("game_starting", name="@Player"))
            self.assertEqual(nav.view()["toast"], expected[code], code)

    def test_nested_placeholders_and_cycler_values_translate_in_the_view(self):
        adapter = FakeAdapter()
        adapter.settings = lambda: [dict(id="test", label="@display", value=True,
                                         options=[(True, "@on"), (False, "@off")])]
        adapter.quick_settings = lambda: ["test"]
        g = Game(game().m, adapter)
        for code in i18n.LANGUAGES:
            nav = Nav([g], language=code)
            nav.act("confirm")
            nav.act("down")
            nav.dry = True
            nav.act("right")
            view = nav.view()
            self.assertEqual(view["rows"][1]["value"], "‹ " + i18n.text(code, "on") + " ›", code)
            self.assertEqual(view["detail"]["rows"][0]["v"], i18n.text(code, "on"), code)
            self.assertEqual(view["toast"], i18n.text(code, "dry_run", what=i18n.text(code, "dry_change", name=i18n.text(code, "display"))), code)

    def test_adapter_messages_survive_the_view(self):
        g = game()
        g.a = Adapter(g.m)
        for code in i18n.LANGUAGES:
            nav = Nav([g], language=code)
            self.assertEqual(nav.view()["hint"], i18n.text(code, "game_not_found", name="Test"), code)
            nav.act("play")
            self.assertEqual(nav.view()["toast"], i18n.text(code, "game_not_found", name="Test"), code)

    def test_adapter_error_with_values_survives_the_view(self):
        for code in i18n.LANGUAGES:
            nav = Nav([game()], language=code)
            nav.game.a.start = mock.Mock(side_effect=RuntimeError(Adapter.message("t4.locked", holder="@Player")))
            nav.act("play")
            self.assertEqual(nav.view()["toast"], i18n.text(code, "action_failed", error=i18n.text(code, "t4.locked", holder="@Player")), code)

    def test_external_error_cause_is_preserved_in_recovery_message(self):
        for value in ("@Player: core error", {"reason": "core error"}):
            nav = Nav([game()], language="ja")
            error = RuntimeError(value)
            nav.game.a.start = mock.Mock(side_effect=error)
            nav.act("play")
            self.assertEqual(nav.view()["toast"], i18n.text("ja", "action_failed", error=str(error)))

    def test_file_picker_title_translates_its_source_label(self):
        for code in i18n.LANGUAGES:
            g = game()
            g.a = Adapter(g.m)
            g.a.sources = lambda: [dict(id="iso", label="@game_iso", value="@missing", ok=False,
                                       kind="file", exts=[".iso"], dirs=[], hint="@iso.hint")]
            nav = Nav([g], language=code)
            with mock.patch.object(nav, "_picker_entries", return_value=[]):
                nav._items_build(g)[0]["run"]()
                self.assertEqual(nav.view()["picker"]["title"], i18n.text(code, "choose_named", name=i18n.text(code, "game_iso")), code)

    def test_recent_results_translate_without_changing_win_state(self):
        for code in i18n.LANGUAGES:
            nav = Nav([game()], language=code)
            nav.game.a.recent_results = lambda: ["W", "L"]
            cells = nav.view()["shelf"]["tiles"][0]["results"]
            self.assertEqual([cell["text"] for cell in cells], [i18n.text(code, "result.win_short"), i18n.text(code, "result.loss_short")], code)
            self.assertEqual([cell["win"] for cell in cells], [True, False], code)

    def test_catalogs_are_loaded_once(self):
        i18n._catalog.cache_clear()
        try:
            with mock.patch.object(Path, "open", autospec=True, side_effect=Path.open) as opened:
                for _ in range(3):
                    for code in i18n.LANGUAGES:
                        i18n.localize({"label": "@quick_access", "hint": "@language"}, code)
                self.assertEqual(opened.call_count, len(i18n.LANGUAGES))
                self.assertEqual(len({call.args[0] for call in opened.call_args_list}), len(i18n.LANGUAGES))
        finally:
            i18n._catalog.cache_clear()

    def test_python_has_no_player_facing_literals(self):
        paths = [ROOT / "openrecomp" / "nav.py", *(ROOT / "openrecomp").glob("nav_*.py"),
                 *(ROOT / "openrecomp" / "adapters").glob("*.py")]
        for path in paths:
            self.assertEqual(untranslated_literals(path.read_text(encoding="utf-8")), [], path.name)

    def test_python_scan_accepts_setting_ids_and_protocol_defaults(self):
        source = ('def quick_settings(self):\n'
                  '    return ["resolution", "fullscreen", "display", "internal_res"]\n'
                  'value = self.s.get("resolution", "auto")\n')
        self.assertEqual(untranslated_literals(source), [])
        self.assertTrue(untranslated_literals('dict(label="auto")'))
        self.assertTrue(untranslated_literals('def quick_settings(self):\n'
                                             '    self.say("Choose a setting")\n'
                                             '    return ["resolution"]\n'))

    def test_python_scan_accepts_fixed_bundle_protocols_without_exempting_labels(self):
        for value in ("ps2EntryRunner.exe", "CXX_VERSION=", "tools:recheck", "winget install --id Git.Git --exact"):
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                self.assertTrue(untranslated_literals(f'dict(label={value!r})'))
                self.assertTrue(untranslated_literals(f'self.say({value!r})'))
        for prefix in ("@t4.tools.", "@t4.network."):
            self.assertEqual(untranslated_literals(f'label = {prefix!r} + key'), [])
            self.assertTrue(untranslated_literals(f'token = {prefix!r}'))
        self.assertTrue(untranslated_literals('label = "@t4.unreviewed." + key'))
        self.assertTrue(untranslated_literals('label = "@t4.tools.new_player_message"'))

    def test_python_scan_accepts_library_protocol_but_checks_visible_text(self):
        for value in (".exe", ".png", ".jpg", ".jpeg", ".webp", "preview", "library_repository", "library_source", "library_manage",
                      "library_loading", "library_preview", "library_remove", "library_update"):
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                self.assertTrue(untranslated_literals(f'dict(label={value!r})'))
                self.assertTrue(untranslated_literals(f'self.say({value!r})'))
        self.assertTrue(untranslated_literals('token = "library_player_warning"'))

    def test_python_scan_accepts_netext_protocol_but_checks_visible_text(self):
        for value in ("netext_options", "online_feel", "net_line", "max_ping", "no_wifi", "steady",
                      "responsive", "balanced", "smooth", "mm_filters", "forget_me"):
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                self.assertTrue(untranslated_literals(f'dict(label={value!r})'))
                self.assertTrue(untranslated_literals(f'self.say({value!r})'))
        self.assertEqual(untranslated_literals('label = "@netext." + key'), [])
        self.assertTrue(untranslated_literals('label = "@netext.unreviewed"'))
        self.assertTrue(untranslated_literals('label = "@netext."'))

    def test_python_scan_accepts_runtime_names_and_temporary_file_prefix(self):
        source = ('for name in ("core", "replays"):\n'
                  '    _runtime_path(root, name)\n'
                  'core = load_runtime(root, "core")\n'
                  'replays_mod = load_runtime(root, "replays")\n'
                  'tempfile.NamedTemporaryFile(prefix=".openrecomp-", suffix=".tmp")\n')
        self.assertEqual(untranslated_literals(source), [])
        for value in ("core", "replays", ".openrecomp-"):
            with self.subTest(value=value):
                self.assertTrue(untranslated_literals(f'dict(label="{value}")'))
                self.assertTrue(untranslated_literals(f'dict(hint="{value}")'))
        self.assertTrue(untranslated_literals('self.say("Choose a runtime")'))
        self.assertTrue(untranslated_literals('tempfile.NamedTemporaryFile(prefix="Choose a file")'))

    def test_python_scan_accepts_controls_temporary_prefix_but_checks_display_contexts(self):
        self.assertEqual(untranslated_literals(
            'tempfile.NamedTemporaryFile(prefix=".controls-", suffix=".json")'), [])
        for field in ("label", "hint", "title", "status"):
            with self.subTest(field=field):
                self.assertTrue(untranslated_literals(f'dict({field}=".controls-")'))
        self.assertTrue(untranslated_literals('self.say(".controls-")'))
        self.assertTrue(untranslated_literals(
            'tempfile.NamedTemporaryFile(prefix=".controls-other-", suffix=".json")'))

    def test_python_scan_accepts_default_install_globs_but_checks_display_contexts(self):
        for value in ("%USERPROFILE%/Downloads/T5DR-Online-*", "%USERPROFILE%/Desktop/T5DR-Online-*"):
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'locations = ["{value}"]'), [])
                self.assertTrue(untranslated_literals(f'dict(label="{value}")'))
                self.assertTrue(untranslated_literals(f'self.say("{value}")'))

    def test_python_scan_rejects_untranslated_texts_and_f_strings(self):
        examples = [
            'dict(label="Start game", hint="Choose a file")',
            'dict(lead="ready", title="Hello", verb="Watch", kicker="Local", rows=[dict(k="Name", v="Unknown")])',
            'self.say(f"Starting {name}.")',
            'return [(True, "On"), (False, "Off")]',
            'status = "Ready"',
            'dict(label="file", value="ready")',
            'return "Choose your files first."',
        ]
        for source in examples:
            self.assertTrue(untranslated_literals(source), source)

    def test_python_scan_accepts_play_section_id_but_checks_display_labels(self):
        source = 'self.sec[g.id] = "play" if g.a.ready() or "build" not in secs else "build"'
        self.assertEqual(untranslated_literals(source), [])
        self.assertTrue(untranslated_literals('dict(label="play")'))
        self.assertTrue(untranslated_literals('dict(label="play" if ready else "@section.build")'))

    def test_python_scan_accepts_navigation_ids_only_in_protocol_assignments(self):
        for source in ('self.screen = "hub" if found else "start"',
                       'self.sec[game.id] = "online" if online else "play"'):
            self.assertEqual(untranslated_literals(source), [], source)
        for value in ("online", "hub", "start"):
            for source in (f'dict(label="{value}")', f'self.say("{value}")'):
                self.assertTrue(untranslated_literals(source), source)
        for source in ('self.screen = "hub" if found else "Choose a game"',
                       'self.sec[game.id] = "online" if online else "Choose a section"',
                       'self.sec[game.id] = "online" if self.say("Choose a section") else "play"',
                       'self.title = "hub" if found else "start"'):
            self.assertTrue(untranslated_literals(source), source)

    def test_python_scan_accepts_dialog_overlay_protocol_but_checks_display_text(self):
        self.assertEqual(untranslated_literals('v["overlay"] = "dialog"'), [])
        for source in ('v["overlay"] = "Choose a dialog"', 'v["dialog"] = "dialog"',
                       'v["overlay"] = v["title"] = "dialog"',
                       'dict(label="dialog")', 'self.say("dialog")'):
            self.assertTrue(untranslated_literals(source), source)

    def test_python_scan_accepts_optional_api_names_but_checks_displayed_defaults(self):
        self.assertEqual(untranslated_literals('getattr(adapter, "controls_supported", lambda: False)()'), [])
        self.assertEqual(untranslated_literals('hasattr(adapter, "_controls_session")'), [])
        source = ('check = (getattr(client, "has_friends", None) if friends '
                  'else getattr(client, "private_rooms_ok", None))')
        self.assertEqual(untranslated_literals(source), [])
        self.assertTrue(untranslated_literals('getattr(adapter, "message", "Try again")'))
        for name in ("has_friends", "private_rooms_ok"):
            self.assertTrue(untranslated_literals(f'self.say("{name}")'))

    def test_python_scan_checks_technical_names_in_toasts(self):
        self.assertEqual(untranslated_literals('self.say("@online.failure")'), [])
        for value in ("online", "ready", "core", "searching"):
            with self.subTest(value=value):
                self.assertTrue(untranslated_literals(f'self.say("{value}")'))
                self.assertTrue(untranslated_literals(f'self.say("@online.failure" if failed else "{value}")'))

    def test_python_scan_accepts_hex_colours_but_checks_display_labels(self):
        for colour in ("#ECE9E1", "#abcdef", "#80ECE9E1"):
            self.assertEqual(untranslated_literals(f'dict(accent="{colour}")'), [])
            self.assertTrue(untranslated_literals(f'dict(label="{colour}")'))
        for colour in ("#GGGGGG", "#Choose", "#ECE9E1 text"):
            self.assertTrue(untranslated_literals(f'dict(accent="{colour}")'))

    def test_python_scan_accepts_online_ids_but_checks_their_display_labels(self):
        self.assertEqual(untranslated_literals('dict(phase="searching", id="login_saved")'), [])
        self.assertEqual(untranslated_literals('ONLINE_KEYS = (("qwertyuiop",),)'), [])
        self.assertTrue(untranslated_literals('dict(label="searching")'))
        self.assertTrue(untranslated_literals('dict(hint="login_saved")'))

    def test_python_scan_accepts_match_social_and_reservation_identifiers(self):
        values = (
            "online_room_password", "online_room_code", "online_friend_name", "_password",
            "create_password_room", "create_code_room", "join_room_code", "refresh_friends",
            "accept_friend", "invite_room", "accept_invite", "cancel_invite", "_online_friend_",
            "private_rooms", "friends", "incoming", "outgoing", "online", "in_match",
            "rematch", "logs", ".match_driver", ".t4game", "continue", "won", "lost", "draw",
            "t5_ready", "t5_driver", "t5_rematch", "t5_return", "openrecomp-t5-match",
            "openrecomp-t5-match-close", "[a-z0-9_-]+", "invalid game id",
            "OpenRecomp-FGC-launches", ".lock", "a+b", "openrecomp-game-reservation",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                for field in ("label", "lead", "hint", "title", "status"):
                    self.assertTrue(untranslated_literals(f'dict({field}={value!r})'), field)
        self.assertTrue(untranslated_literals('token = "openrecomp-player-message"'))
        self.assertTrue(untranslated_literals('token = "join_room_new_message"'))

    def test_python_scan_accepts_native_120_protocol_but_checks_visible_contexts(self):
        values = ("feature_tour:", "tour_select_set:", "online_current_password",
                  "profile_history_replay:", "ranked_chars", "rules_life:",
                  "spec_watch_table:", "watch-status.json", "community_pair_option:",
                  "auto_unless_declined", "challenge_delay_max", "t5_leave_set")
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                for field in ("label", "title", "hint", "status"):
                    self.assertTrue(untranslated_literals(f'dict({field}={value!r})'))
                self.assertTrue(untranslated_literals(f'self.say({value!r})'))
        for value in ("feature_tour:New player message", "new_native_protocol_token",
                      "watch-new-player-message.json"):
            self.assertTrue(untranslated_literals(f'token = {value!r}'))

    def test_python_scan_accepts_chat_protocol_but_checks_visible_contexts(self):
        values = (".t5_moderation", ".t5_private_chat", "feature_moderation:", "feature_private:",
                  "moderation_mute:", "moderation_unmute:", "moderation_block:",
                  "online_private_chat", "online_private_report_reason", "private_open:",
                  "private_send", "private_select:", "private_report", "receipt")
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                for field in ("label", "title", "hint", "status"):
                    self.assertTrue(untranslated_literals(f'dict({field}={value!r})'))
                self.assertTrue(untranslated_literals(f'self.say({value!r})'))
        self.assertTrue(untranslated_literals('self.say("Message blocked: hate terms are not allowed.")'))
        self.assertTrue(untranslated_literals('token = "private_new_player_message"'))

    def test_python_scan_accepts_beta_switches_but_checks_their_display_labels(self):
        for value in ("online_address", "host", "join", "collect_logs", "disconnect", "direct_back",
                      "TEKKEN4_RUNAHEAD", "TEKKEN4_NET_DIAG", "TEKKEN4_NET_HASH_PROFILE",
                      "TEKKEN4_NET_COST_PROFILE", "TEKKEN4_NET_COALESCE", "TEKKEN4_NET_STRICT_HELLO",
                      "TEKKEN4_RB_AUDIO_TIMELINE", "TEKKEN4_NET_DELAY_MATCH", "TEKKEN4_NET_SIM_SAFE_WAIT",
                      "TEKKEN4_NET_END", "TEKKEN4_NET_SHOTS", "TEKKEN4_NET_DESYNC_DUMP", "TEKKEN4_NET_SIM"):
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                self.assertTrue(untranslated_literals(f'dict(label={value!r})'))
                self.assertTrue(untranslated_literals(f'self.say({value!r})'))
        self.assertTrue(untranslated_literals('token = "TEKKEN4_PLAYER_MESSAGE"'))

    def test_python_scan_accepts_preflight_protocol_but_keeps_display_checks(self):
        source = ('PREFLIGHT_SCRIPT = "param([string]$Tool)\\n. $Tool"\n'
                  'command = ["powershell.exe", "-NoProfile", "-File", "net_preflight.ps1"]\n'
                  'checks = ("build", "compiler", "iso", "udp")\n')
        self.assertEqual(untranslated_literals(source), [])
        for value in ("powershell.exe", "compiler", "udp", "net_preflight.ps1", "-NoProfile", "stopping",
                      r"[A-Za-z0-9_.+ -]{1,100}", r"[0-9a-f]{64}", r"[0-9a-f]{40}"):
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                self.assertTrue(untranslated_literals(f'dict(label={value!r})'))
                self.assertTrue(untranslated_literals(f'self.say({value!r})'))
        self.assertTrue(untranslated_literals('script = "param([string]$Tool)"'))

    def test_python_scan_recognizes_only_the_friend_snapshot_status_enum(self):
        source = ('dict(name=friend["name"], status="online" if active else "offline", '
                  'activity="", invite=True, retry=0)')
        self.assertEqual(untranslated_literals(source), [])
        self.assertTrue(untranslated_literals('dict(status="offline")'))
        self.assertTrue(untranslated_literals(source.replace('"offline"', '"Try again later"')))
        self.assertTrue(untranslated_literals(source.replace('status=', 'label=')))

    def test_python_scan_recognizes_only_the_source_snapshot_reload_result(self):
        for result in ('"reload"', '"reload" if ok else "@generic.requirement_bad_hash"'):
            source = f'dict(running=False, result={result}, id=sid, ok=ok)'
            self.assertEqual(untranslated_literals(source), [], source)
        for result in ('"Choose a file"', '"ready"', '"reload" if ok else "Choose a file"'):
            source = f'dict(running=False, result={result}, id=sid, ok=ok)'
            self.assertTrue(untranslated_literals(source), source)
        for source in ('dict(result="reload")',
                       'dict(running=False, result="reload", id=sid, ok=ok, label="@start")',
                       'dict(running=False, label="reload", id=sid, ok=ok)',
                       'self.say("reload")'):
            self.assertTrue(untranslated_literals(source), source)

    def test_python_scan_accepts_coexistence_paths_but_checks_display_contexts(self):
        values = (
            "launcher.json", "settings.json", "controls.json", "servers.json", "t5dr_build.json",
            "PS3_CONTROLS", ".settings-", "_OpenRecompSettings", "_coexist_defaults",
            "code_id", "same", "different", "unknown", "coexistence",
            "coexistence_folder", "t5dr_settings_copy",
            r"[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                for field in ("label", "hint", "title", "status"):
                    self.assertTrue(untranslated_literals(f'dict({field}={value!r})'))
                self.assertTrue(untranslated_literals(f'self.say({value!r})'))
        self.assertTrue(untranslated_literals('token = "Choose an existing installation"'))
        self.assertTrue(untranslated_literals('token = "coexistence-player-message"'))

    def test_python_scan_accepts_discovery_metadata_but_checks_display_contexts(self):
        values = ("installlocation", "recent_folders", "last_directory", "Documents", ".lnk",
                  "utf-16-le", "<5I", "{374de290-123f-4565-9164-39c4925e467b}",
                  r"Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU",
                  r"Software\T5DR Online\Launcher")
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(untranslated_literals(f'token = {value!r}'), [])
                for field in ("label", "hint", "title", "status"):
                    self.assertTrue(untranslated_literals(f'dict({field}={value!r})'))
                self.assertTrue(untranslated_literals(f'self.say({value!r})'))
        self.assertTrue(untranslated_literals('token = "Use your existing T5DR"'))
        self.assertTrue(untranslated_literals('token = "recent_new_player_message"'))

    def test_qml_has_no_player_facing_literals(self):
        forbidden = ("Quick access", "Recent sets", "Choose your fighter", "Your main:", "Folder", "File", "MAIN")
        for path in (ROOT / "openrecomp" / "ui").glob("*.qml"):
            source = path.read_text(encoding="utf-8")
            self.assertFalse(any(text in source for text in forbidden), path.name)


if __name__ == "__main__":
    unittest.main()
