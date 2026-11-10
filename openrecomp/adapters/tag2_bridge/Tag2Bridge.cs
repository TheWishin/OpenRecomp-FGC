// OpenRecomp-FGC <-> TAG2 PC launcher Core.
//
// This file is compiled on the player's PC by Windows PowerShell (Add-Type, C# 5) against the Core of the
// installed TAG2 PC (Tag2.Launcher.Core.dll). It holds no TAG2 code: every account, session, launch and Ranked
// step is the Core's own public method. One JSON object per line comes in on stdin and goes out on stdout:
//   in : {"id": n, "op": "...", ...}
//   out: {"id": n, "ok": true, "result": {...}} | {"id": n, "ok": false, "error": {...}} | {"event": "...", ...}
// Passwords arrive in a request line and are handed to the Core only; nothing here writes a request, a token or
// a session key to a log, an event or an error.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using Tag2.Launcher;

namespace OpenRecomp.Tag2
{
    public sealed class UserAgentHandler : DelegatingHandler
    {
        private readonly string agent;

        public UserAgentHandler(string agent)
            : base(new HttpClientHandler { AllowAutoRedirect = false })
        {
            this.agent = agent;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellation)
        {
            request.Headers.Remove("User-Agent");
            request.Headers.TryAddWithoutValidation("User-Agent", agent);
            return base.SendAsync(request, cancellation);
        }
    }

    public static class Bridge
    {
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 1048576 };
        private static readonly object OutLock = new object();
        private static readonly object StateLock = new object();
        private static readonly string[] SettingNames =
        {
            "RenderScale", "Internal540p", "GraphicsBackend", "ReadbackResolve", "ReadbackDeferred", "PresentVSync",
            "PresentQueueDepth", "Windowed", "AnisotropicOverride", "ForceRelay", "SkipStartupIntros"
        };
        private static TextWriter output;
        private static LauncherService service;
        private static Process game;
        private static string gameKind = "";
        private static bool launching;
        private static CancellationTokenSource rankedCancel;

        public static int Run(string root, string agent)
        {
            output = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true };
            TextReader input = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));
            try
            {
                service = new LauncherService(root, new UserAgentHandler(agent));
            }
            catch (Exception e)
            {
                Send(Dict("event", "fatal", "error", Error(e)));
                return 2;
            }
            Send(Dict("event", "ready", "agent", agent));
            string line;
            while ((line = input.ReadLine()) != null)
            {
                Dictionary<string, object> request;
                try
                {
                    request = Json.Deserialize<Dictionary<string, object>>(line);
                }
                catch (Exception)
                {
                    continue;
                }
                if (request == null || !request.ContainsKey("op"))
                {
                    continue;
                }
                if (Convert.ToString(request["op"]) == "quit")
                {
                    break;
                }
                Handle(request);
            }
            CancelRanked();
            service.Dispose();
            return 0;
        }

        private static async void Handle(Dictionary<string, object> request)
        {
            object id = request.ContainsKey("id") ? request["id"] : null;
            try
            {
                object result = await Dispatch(Convert.ToString(request["op"]), request, id).ConfigureAwait(false);
                Send(Dict("id", id, "ok", true, "result", result));
            }
            catch (Exception e)
            {
                Send(Dict("id", id, "ok", false, "error", Error(e)));
            }
        }

        private static Task<object> Dispatch(string op, Dictionary<string, object> request, object id)
        {
            switch (op)
            {
                case "hello": return Task.FromResult<object>(Hello());
                case "settings_set": return Task.FromResult<object>(SetSettings(Map(request, "values"), true));
                case "sign_in": return Authenticate(request, false);
                case "register": return Authenticate(request, true);
                case "play": return Play(Convert.ToString(request["mode"]) == "online", id);
                case "ranked": return Ranked(request, id);
                case "ranked_cancel": CancelRanked(); return Task.FromResult<object>(Dict("cancelled", true));
                case "game_status": return Task.FromResult<object>(GameStatus());
                case "stop": return Task.FromResult<object>(Stop(request.ContainsKey("force") && Convert.ToBoolean(request["force"])));
                case "progress": return Progress();
                case "start_info": return Task.FromResult<object>(StartInfo(request));
                default: throw new ArgumentException("Unknown bridge request.");
            }
        }

        // ------------------------------------------------------------------ account and settings
        private static Dictionary<string, object> Account()
        {
            return Dict("has_account", service.HasAccount, "login_name", service.AccountLoginName,
                "player_name", service.Settings.PlayerName ?? "", "name_pending", service.Settings.NamePending);
        }

        private static Dictionary<string, object> Hello()
        {
            return Dict("account", Account(), "settings", ReadSettings(), "build", service.Config.Build,
                "protocol", service.Config.Protocol);
        }

        private static Dictionary<string, object> ReadSettings()
        {
            Dictionary<string, object> values = new Dictionary<string, object>();
            foreach (string name in SettingNames)
            {
                values[name] = typeof(Settings).GetField(name).GetValue(service.Settings);
            }
            return values;
        }

        private static Dictionary<string, object> SetSettings(Dictionary<string, object> values, bool save)
        {
            Dictionary<string, object> before = ReadSettings();
            try
            {
                foreach (KeyValuePair<string, object> pair in values)
                {
                    if (Array.IndexOf(SettingNames, pair.Key) < 0)
                    {
                        throw new ArgumentException("Unknown setting.");
                    }
                    FieldInfo field = typeof(Settings).GetField(pair.Key);
                    field.SetValue(service.Settings, Convert.ChangeType(pair.Value, field.FieldType));
                }
                if (save)
                {
                    service.SaveSettings();
                }
                else
                {
                    service.ValidateSettings();
                }
            }
            catch (Exception)
            {
                foreach (KeyValuePair<string, object> pair in before)
                {
                    typeof(Settings).GetField(pair.Key).SetValue(service.Settings, pair.Value);
                }
                throw;
            }
            return ReadSettings();
        }

        private static async Task<object> Authenticate(Dictionary<string, object> request, bool register)
        {
            string name = Convert.ToString(request["name"]);
            string password = Convert.ToString(request["password"]);
            request.Remove("password");
            string shown = register
                ? await service.CreateAccountAsync(name, password, CancellationToken.None).ConfigureAwait(false)
                : await service.SignInAsync(name, password, CancellationToken.None).ConfigureAwait(false);
            Dictionary<string, object> account = Account();
            account["name"] = shown;
            return account;
        }

        // ------------------------------------------------------------------ the game process
        private static void Claim()
        {
            lock (StateLock)
            {
                if (launching || (game != null && !Exited(game)))
                {
                    throw new InvalidOperationException("The game is already running.");
                }
                launching = true;
            }
        }

        private static bool Exited(Process process)
        {
            try
            {
                return process.HasExited;
            }
            catch (Exception)
            {
                return true;
            }
        }

        private static Dictionary<string, object> Own(Process process, string kind)
        {
            lock (StateLock)
            {
                bool fresh = game != process;
                if (fresh && game != null)
                {
                    game.Dispose();
                }
                game = process;
                gameKind = kind;
                if (fresh)
                {
                    int pid = process.Id;
                    try
                    {
                        process.EnableRaisingEvents = true;
                        process.Exited += delegate { Send(Dict("event", "game_exit", "pid", pid)); };
                    }
                    catch (Exception)
                    {
                    }
                }
            }
            return Dict("pid", process.Id, "kind", kind);
        }

        private static async Task<object> Play(bool online, object id)
        {
            Claim();
            try
            {
                Action<string> status = delegate(string text) { Send(Dict("event", "status", "id", id, "text", Clean(text))); };
                Process process = online
                    ? await service.PlayAsync(status).ConfigureAwait(false)
                    : await service.PlayOfflineAsync(status).ConfigureAwait(false);
                return Own(process, online ? "online" : "offline");
            }
            finally
            {
                lock (StateLock)
                {
                    launching = false;
                }
            }
        }

        private static int Costume(RankedTeamCatalog catalog, int index, int wanted)
        {
            if (wanted < 0 || catalog.characters == null || catalog.characters.Length <= index || catalog.characters[index] == null)
            {
                return -1;
            }
            int[] slots = catalog.characters[index].slots ?? new int[0];
            return Array.IndexOf(slots, wanted) >= 0 ? wanted : -1;
        }

        private static async Task<object> Ranked(Dictionary<string, object> request, object id)
        {
            int[] wanted = Ints(request, "team");
            int[] costumes = Ints(request, "costumes") ?? new[] { -1, -1 };
            CancellationTokenSource cancel = new CancellationTokenSource();
            lock (StateLock)
            {
                if (launching || rankedCancel != null)
                {
                    throw new InvalidOperationException("A Ranked request is already being prepared.");
                }
                launching = true;
                rankedCancel = cancel;
            }
            try
            {
                RankedTeamCatalog shown = null;
                Action<string> status = delegate(string text) { Send(Dict("event", "status", "id", id, "text", Clean(text))); };
                Func<Process, int[], CancellationToken, Task<RankedTeamSelection>> select = async delegate(Process process, int[] last, CancellationToken token)
                {
                    int[] team = wanted ?? last;
                    if (team == null || team.Length != 2 || team[0] < 0 || team[1] < 0)
                    {
                        throw new InvalidOperationException("Choose your Ranked team first.");
                    }
                    RankedTeamCatalog catalog = await service.PreviewRankedTeamAsync(process, team, token).ConfigureAwait(false);
                    shown = catalog;
                    return new RankedTeamSelection
                    {
                        Catalog = catalog,
                        FirstCostume = Costume(catalog, 0, costumes.Length > 0 ? costumes[0] : -1),
                        SecondCostume = Costume(catalog, 1, costumes.Length > 1 ? costumes[1] : -1)
                    };
                };
                RankedLaunchResult result = await service.PlayRankedAsync(status, cancel.Token, select).ConfigureAwait(false);
                Dictionary<string, object> answer = Own(result.Game, "ranked");
                answer["started_game"] = result.StartedGame;
                answer["outcome"] = result.Status == null ? "" : result.Status.outcome ?? "";
                answer["code"] = result.Status == null ? "" : result.Status.code ?? "";
                answer["phase"] = result.Status == null ? "" : result.Status.phase ?? "";
                ArrayList team2 = new ArrayList();
                if (shown != null && shown.characters != null)
                {
                    foreach (RankedTeamCharacter character in shown.characters)
                    {
                        if (character != null)
                        {
                            team2.Add(Dict("id", character.id, "slots", character.slots ?? new int[0]));
                        }
                    }
                }
                answer["team"] = team2;
                return answer;
            }
            catch (Exception)
            {
                Adopt();
                throw;
            }
            finally
            {
                lock (StateLock)
                {
                    launching = false;
                    rankedCancel = null;
                }
                cancel.Dispose();
            }
        }

        // A Ranked request that failed after the Core had started the game leaves that game at its menu. Find it
        // (the install's own TekkenTag2Hints.exe, the one process ReadGameIntentStatus accepts) so that the launcher
        // still shows it as running and can stop it.
        private static void Adopt()
        {
            lock (StateLock)
            {
                if (game != null && !Exited(game))
                {
                    return;
                }
            }
            foreach (Process process in Process.GetProcessesByName("TekkenTag2Hints"))
            {
                bool ours = false;
                try
                {
                    ours = !process.HasExited && Path.GetFullPath(process.MainModule.FileName).StartsWith(service.Root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
                }
                catch (Exception)
                {
                }
                if (ours)
                {
                    Send(Dict("event", "game", "pid", Own(process, "ranked")["pid"], "kind", "ranked"));
                    return;
                }
                process.Dispose();
            }
        }

        private static void CancelRanked()
        {
            lock (StateLock)
            {
                if (rankedCancel != null)
                {
                    try
                    {
                        rankedCancel.Cancel();
                    }
                    catch (ObjectDisposedException)
                    {
                    }
                }
            }
        }

        private static Dictionary<string, object> GameStatus()
        {
            Process process;
            string kind;
            lock (StateLock)
            {
                process = game;
                kind = gameKind;
            }
            if (process == null || Exited(process))
            {
                return Dict("running", false, "busy", launching);
            }
            Dictionary<string, object> answer = Dict("running", true, "busy", launching, "pid", process.Id, "kind", kind,
                "phase", "", "outcome", "", "code", "", "online", false);
            if (kind != "offline")
            {
                try
                {
                    GameIntentStatus status = service.ReadGameIntentStatus(process);
                    answer["phase"] = status.phase ?? "";
                    answer["outcome"] = status.outcome ?? "";
                    answer["code"] = status.code ?? "";
                    answer["online"] = status.online;
                }
                catch (Exception)
                {
                }
            }
            return answer;
        }

        private static Dictionary<string, object> Stop(bool force)
        {
            Process process;
            lock (StateLock)
            {
                process = game;
            }
            if (process == null || Exited(process))
            {
                return Dict("running", false);
            }
            if (force)
            {
                process.Kill();
            }
            else if (!process.CloseMainWindow())
            {
                return Dict("running", true, "asked", false);
            }
            return Dict("running", true, "asked", true);
        }

        // ------------------------------------------------------------------ Ranked progress (only when asked)
        private static async Task<object> Progress()
        {
            RankedProgress progress = await service.LoadRankedProgressAsync().ConfigureAwait(false);
            ProgressProfile profile = progress.Profile;
            ArrayList ranks = new ArrayList();
            if (profile != null && profile.ranks != null)
            {
                foreach (CharacterRank rank in profile.ranks)
                {
                    ranks.Add(Dict("character", rank.character, "rank", rank.rank, "points", rank.points, "streak", rank.streak));
                }
            }
            return Dict("name", profile == null ? "" : profile.name ?? "",
                "ranked_wins", profile == null ? "" : profile.ranked_wins ?? "",
                "ranked_losses", profile == null ? "" : profile.ranked_losses ?? "",
                "player_wins", profile == null ? "" : profile.player_wins ?? "",
                "player_losses", profile == null ? "" : profile.player_losses ?? "",
                "team", profile == null || profile.characters == null ? new int[0] : profile.characters, "ranks", ranks);
        }

        // ------------------------------------------------------------------ launch settings, constructed only
        // The Core's CreateGameStartInfo with the settings applied the way settings_set applies them: what the
        // Core's own Play methods start. Nothing is started here (the launch contract test reads this).
        private static Dictionary<string, object> StartInfo(Dictionary<string, object> request)
        {
            Dictionary<string, object> before = ReadSettings();
            try
            {
                if (request.ContainsKey("settings"))
                {
                    SetSettings(Map(request, "settings"), false);
                }
                GameLocation location = new GameLocation();
                foreach (KeyValuePair<string, object> pair in Map(request, "game"))
                {
                    FieldInfo field = typeof(GameLocation).GetField(pair.Key);
                    if (field == null)
                    {
                        throw new ArgumentException("Unknown game field.");
                    }
                    field.SetValue(location, Convert.ChangeType(pair.Value, field.FieldType));
                }
                ProcessStartInfo info = service.CreateGameStartInfo(location, Convert.ToBoolean(request["online"]), Convert.ToBoolean(request["ranked"]));
                Dictionary<string, object> environment = new Dictionary<string, object>();
                foreach (string name in new[] { "TAG2_OFFLINE_TIMING", "TAG2_PC_LOW_LATENCY_INPUT", "REX_PC_NATIVE_ROLLBACK", "TAG2_VBLANK_HYBRID_US", "TAG2_FORCE_RELAY" })
                {
                    environment[name] = info.EnvironmentVariables.ContainsKey(name) ? info.EnvironmentVariables[name] : null;
                }
                return Dict("file", info.FileName, "arguments", info.Arguments, "cwd", info.WorkingDirectory,
                    "shell", info.UseShellExecute, "environment", environment);
            }
            finally
            {
                foreach (KeyValuePair<string, object> pair in before)
                {
                    typeof(Settings).GetField(pair.Key).SetValue(service.Settings, pair.Value);
                }
            }
        }

        // ------------------------------------------------------------------ helpers
        private static Dictionary<string, object> Map(Dictionary<string, object> request, string key)
        {
            Dictionary<string, object> map = request.ContainsKey(key) ? request[key] as Dictionary<string, object> : null;
            if (map == null)
            {
                throw new ArgumentException("The bridge request is incomplete.");
            }
            return map;
        }

        private static int[] Ints(Dictionary<string, object> request, string key)
        {
            IEnumerable list = request.ContainsKey(key) ? request[key] as IEnumerable : null;
            if (list == null || list is string)
            {
                return null;
            }
            List<int> values = new List<int>();
            foreach (object value in list)
            {
                values.Add(Convert.ToInt32(value));
            }
            return values.ToArray();
        }

        private static string Clean(string text)
        {
            text = Regex.Replace(text ?? "", "[\\x00-\\x1f\\x7f]", " ");
            return text.Length > 300 ? text.Substring(0, 300) : text;
        }

        private static Dictionary<string, object> Error(Exception error)
        {
            while ((error is AggregateException || error is TargetInvocationException) && error.InnerException != null)
            {
                error = error.InnerException;
            }
            string type = error.GetType().Name;
            string kind = "error";
            if (LauncherService.RequiresSignIn(error))
            {
                kind = "sign_in";
            }
            else if (error is OperationCanceledException)
            {
                kind = "cancelled";
            }
            else if (type == "LocalBuildRequiredException" || error is FileNotFoundException)
            {
                kind = "build";
            }
            else if (type == "ProfileNotInitializedException")
            {
                kind = "profile";
            }
            else if (error is ArgumentException)
            {
                kind = "input";
            }
            object status = error.Data.Contains("HttpStatus") ? error.Data["HttpStatus"] : null;
            return Dict("kind", kind, "type", type, "message", Clean(error.Message), "http", status);
        }

        private static Dictionary<string, object> Dict(params object[] pairs)
        {
            Dictionary<string, object> map = new Dictionary<string, object>();
            for (int i = 0; i + 1 < pairs.Length; i += 2)
            {
                map[(string)pairs[i]] = pairs[i + 1];
            }
            return map;
        }

        private static void Send(Dictionary<string, object> message)
        {
            string line = Json.Serialize(message);
            lock (OutLock)
            {
                try
                {
                    output.WriteLine(line);
                }
                catch (IOException)
                {
                }
            }
        }
    }
}
