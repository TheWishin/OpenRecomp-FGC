// A stand-in for TAG2 PC's launcher Core, written for OpenRecomp-FGC's tests. It is NOT TAG2 code: it has the
// public names the bridge uses (LAUNCHER-API-EN.txt of the 0.16.33 handover) and deliberately simple behaviour
// that a test steers with <root>\stand-in.json. Its "game" is a harmless command from that file; its "service"
// is whatever http://127.0.0.1 address the file names. Nothing in it reads or writes a real account.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace Tag2.Launcher
{
    public sealed class LauncherConfig
    {
        public int Build = 16;
        public int Protocol = 3;
    }

    public sealed class Settings
    {
        public string PlayerName = "";
        public bool NamePending;
        public int RenderScale = 1;
        public bool Internal540p;
        public string GraphicsBackend = "d3d12";
        public string ReadbackResolve = "full";
        public bool ReadbackDeferred;
        public bool PresentVSync;
        public int PresentQueueDepth = 1;
        public bool Windowed;
        public int AnisotropicOverride = 3;
        public bool ForceRelay;
        public bool SkipStartupIntros;
    }

    public sealed class GameLocation
    {
        public bool Native540p;
        public string InputFingerprint;
        public string ShaderAppRoot;
        public string AppRoot;
        public string Entrypoint;
        public string DataRoot;
        public int Build;
        public int Protocol;
    }

    public sealed class RankedTeamCharacter
    {
        public int id;
        public int[] slots;
    }

    public sealed class RankedTeamCatalog
    {
        public string request_id;
        public RankedTeamCharacter[] characters;
    }

    public sealed class RankedTeamSelection
    {
        public RankedTeamSelection()
        {
            FirstCostume = -1;
            SecondCostume = -1;
        }

        public RankedTeamCatalog Catalog { get; set; }
        public int FirstCostume { get; set; }
        public int SecondCostume { get; set; }
    }

    public sealed class RankedIntentRequest
    {
        public string Id { get; internal set; }
    }

    public sealed class GameIntentStatus
    {
        public int team_catalog_version;
        public string phase;
        public string request_id;
        public string outcome;
        public string code;
        public bool online;
    }

    public sealed class RankedLaunchResult
    {
        public Process Game { get; internal set; }
        public RankedIntentRequest Request { get; internal set; }
        public GameIntentStatus Status { get; internal set; }
        public bool StartedGame { get; internal set; }
    }

    public sealed class CharacterRank
    {
        public int character;
        public int rank;
        public int points;
        public int streak;
    }

    public sealed class ProgressProfile
    {
        public string name;
        public string player_wins;
        public string player_losses;
        public string ranked_wins;
        public string ranked_losses;
        public int[] characters;
        public CharacterRank[] ranks;
    }

    public sealed class RankedProgress
    {
        public ProgressProfile Profile;
    }

    public sealed class LocalBuildRequiredException : InvalidOperationException
    {
        public LocalBuildRequiredException(string message)
            : base(message)
        {
        }
    }

    public sealed class LauncherService : IDisposable
    {
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
        public readonly string Root;
        public readonly string Local;
        private readonly HttpClient http;
        private Process owned;

        public LauncherConfig Config { get; private set; }
        public Settings Settings { get; private set; }

        public LauncherService(string root, HttpMessageHandler handler = null)
        {
            Root = Path.GetFullPath(root).TrimEnd('\\');
            Local = Path.Combine(Root, "local");
            Directory.CreateDirectory(Local);
            Config = new LauncherConfig();
            string saved = Path.Combine(Local, "launcher-settings.json");
            Settings = File.Exists(saved) ? Json.Deserialize<Settings>(File.ReadAllText(saved)) : new Settings();
            http = new HttpClient(handler ?? new HttpClientHandler());
        }

        private Dictionary<string, object> Steer()
        {
            string path = Path.Combine(Root, "stand-in.json");
            return File.Exists(path) ? Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path)) : new Dictionary<string, object>();
        }

        public bool HasAccount
        {
            get { return File.Exists(Path.Combine(Local, "account.dat")); }
        }

        public string AccountLoginName
        {
            get { return HasAccount ? File.ReadAllText(Path.Combine(Local, "account.dat")) : ""; }
        }

        public void ValidateSettings()
        {
            if (Settings.RenderScale < 1 || Settings.RenderScale > 3 || (Settings.Internal540p && Settings.RenderScale != 1))
            {
                throw new InvalidDataException("Rendering settings are invalid.");
            }
            if (Settings.GraphicsBackend != "d3d12" && Settings.GraphicsBackend != "vulkan")
            {
                throw new InvalidDataException("Choose a supported graphics backend.");
            }
        }

        public void SaveSettings()
        {
            ValidateSettings();
            File.WriteAllText(Path.Combine(Local, "launcher-settings.json"), Json.Serialize(Settings));
        }

        public static bool RequiresSignIn(Exception error)
        {
            if (error == null || !object.Equals(error.Data["HttpStatus"], 401))
            {
                return false;
            }
            object operation = error.Data["Operation"];
            return object.Equals(operation, "session") || object.Equals(operation, "profile") || object.Equals(operation, "leaderboard");
        }

        private async Task<string> ServiceAsync(string operation, object body)
        {
            Dictionary<string, object> steer = Steer();
            if (!steer.ContainsKey("service"))
            {
                throw new IOException("The service is not responding. Try again later.");
            }
            StringContent content = new StringContent(Json.Serialize(body), Encoding.UTF8, "application/json");
            using (HttpResponseMessage response = await http.PostAsync(Convert.ToString(steer["service"]) + operation, content).ConfigureAwait(false))
            {
                if (!response.IsSuccessStatusCode)
                {
                    IOException failure = new IOException("The service refused the request (" + (int)response.StatusCode + ").");
                    failure.Data["HttpStatus"] = (int)response.StatusCode;
                    failure.Data["Operation"] = operation;
                    throw failure;
                }
                return await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            }
        }

        private async Task<string> AuthenticateAsync(string operation, string nickname, string password)
        {
            if (string.IsNullOrEmpty(nickname) || nickname.Trim().Length < 2)
            {
                throw new ArgumentException("Choose a player name with 2 to 16 characters.");
            }
            if (password == null || password.Length < 8)
            {
                throw new ArgumentException("Use at least 8 characters for your password.");
            }
            await ServiceAsync(operation, new { product = "tag2-pc", protocol = Config.Protocol, build = Config.Build, nickname = nickname, password = password }).ConfigureAwait(false);
            File.WriteAllText(Path.Combine(Local, "account.dat"), nickname.Trim());
            Settings.PlayerName = nickname.Trim();
            SaveSettings();
            return nickname.Trim();
        }

        public Task<string> CreateAccountAsync(string nickname, string password, CancellationToken cancellation)
        {
            return AuthenticateAsync("register", nickname, password);
        }

        public Task<string> SignInAsync(string username, string password, CancellationToken cancellation)
        {
            return AuthenticateAsync("login", username, password);
        }

        public Task<GameLocation> ResolveGameAsync()
        {
            if (Steer().ContainsKey("no_build"))
            {
                throw new LocalBuildRequiredException("Use Updates > Build game to compile your own ISO / XEX before playing.");
            }
            return Task.FromResult(new GameLocation { AppRoot = Root, Entrypoint = Path.Combine(Root, "never-executed.exe"), DataRoot = Path.Combine(Root, "game"), Build = Config.Build, Protocol = Config.Protocol });
        }

        public ProcessStartInfo CreateGameStartInfo(GameLocation game, bool online, bool rankedStart)
        {
            ValidateSettings();
            if (!File.Exists(game.Entrypoint) || !Directory.Exists(game.DataRoot))
            {
                throw new FileNotFoundException("The game files are incomplete. Extract the full package before playing.");
            }
            List<string> list = new List<string>
            {
                "--d3d12_max_frame_latency=" + Settings.PresentQueueDepth,
                "--d3d12_present_vsync=" + Settings.PresentVSync.ToString().ToLowerInvariant(),
                "--vsync=true",
                "--video_mode_refresh_rate=60",
                "--draw_resolution_scale_x=" + Settings.RenderScale,
                "--draw_resolution_scale_y=" + Settings.RenderScale,
                "--game_data_root=" + game.DataRoot,
                "--gpu_backend=" + Settings.GraphicsBackend,
                "--tag2_skip_startup_intros=" + Settings.SkipStartupIntros.ToString().ToLowerInvariant()
            };
            if (Settings.Internal540p)
            {
                if (!game.Native540p)
                {
                    throw new InvalidOperationException("Install the current engine update to use 540p.");
                }
                list.Add("--tag2_internal_540p=true");
            }
            if (rankedStart)
            {
                list.Add("--tag2_launcher_ranked_start=true");
            }
            list.Add("--readback_resolve_deferred=" + (Settings.GraphicsBackend == "d3d12" && Settings.ReadbackResolve == "full" && Settings.ReadbackDeferred).ToString().ToLowerInvariant());
            if (Settings.GraphicsBackend == "vulkan")
            {
                list.Add("--vulkan_max_frame_latency=" + Settings.PresentQueueDepth);
                list.Add("--vulkan_allow_present_mode_immediate=" + (!Settings.PresentVSync).ToString().ToLowerInvariant());
            }
            ProcessStartInfo info = new ProcessStartInfo(game.Entrypoint, string.Join(" ", list)) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(game.Entrypoint) };
            info.EnvironmentVariables["TAG2_OFFLINE_TIMING"] = online ? "0" : "1";
            info.EnvironmentVariables["TAG2_PC_LOW_LATENCY_INPUT"] = "1";
            info.EnvironmentVariables["REX_PC_NATIVE_ROLLBACK"] = "1";
            if (Settings.ForceRelay)
            {
                info.EnvironmentVariables["TAG2_FORCE_RELAY"] = "1";
            }
            return info;
        }

        private async Task<Process> LaunchAsync(Action<string> status, bool online, bool rankedStart)
        {
            SaveSettings();
            GameLocation game = await ResolveGameAsync().ConfigureAwait(false);
            ProcessStartInfo info = CreateGameStartInfo(game, online, rankedStart);
            if (owned != null && !owned.HasExited)
            {
                throw new InvalidOperationException("The game is already running. Close it before preparing another launch.");
            }
            status("Preparing portable shader cache...");
            if (online)
            {
                status("Connecting to your online account...");
                await ServiceAsync("session", new { product = "tag2-pc", identity = AccountLoginName }).ConfigureAwait(false);
            }
            status(online ? "Starting the game..." : "Starting offline. Online rooms are unavailable.");
            object[] command = ((System.Collections.IEnumerable)Steer()["game_command"]).Cast<object>().ToArray();
            ProcessStartInfo inert = new ProcessStartInfo(Convert.ToString(command[0]), string.Join(" ", command.Skip(1).Select(a => "\"" + Convert.ToString(a) + "\""))) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Root };
            owned = Process.Start(inert);
            File.WriteAllText(Path.Combine(Local, "last-launch.json"), Json.Serialize(new { pid = owned.Id, arguments = info.Arguments, online = online, ranked = rankedStart, offline_timing = info.EnvironmentVariables["TAG2_OFFLINE_TIMING"] }));
            return owned;
        }

        public Task<Process> PlayAsync(Action<string> status)
        {
            return LaunchAsync(status, true, false);
        }

        public Task<Process> PlayOfflineAsync(Action<string> status)
        {
            return LaunchAsync(status, false, false);
        }

        public GameIntentStatus ReadGameIntentStatus(Process game)
        {
            if (game == null || game.HasExited)
            {
                throw new InvalidOperationException("The game is not running.");
            }
            return new GameIntentStatus { team_catalog_version = 1, phase = "idle", outcome = "", code = "", online = true };
        }

        public Task<RankedTeamCatalog> PreviewRankedTeamAsync(Process game, int[] team, CancellationToken cancellation)
        {
            if (team == null || team.Length != 2 || team[0] < 0 || team[1] < 0 || team[0] == team[1])
            {
                throw new ArgumentException("Choose two different characters.");
            }
            return Task.FromResult(new RankedTeamCatalog
            {
                request_id = "stand-in",
                characters = team.Select(id => new RankedTeamCharacter { id = id, slots = new[] { 0, 2 } }).ToArray()
            });
        }

        public RankedIntentRequest BeginRankedTeamIntent(Process game, RankedTeamSelection selection)
        {
            File.WriteAllText(Path.Combine(Local, "last-ranked.json"), Json.Serialize(new { team = selection.Catalog.characters.Select(c => c.id).ToArray(), costumes = new[] { selection.FirstCostume, selection.SecondCostume } }));
            return new RankedIntentRequest { Id = selection.Catalog.request_id };
        }

        public async Task<RankedLaunchResult> PlayRankedAsync(Action<string> progress, CancellationToken cancellation, Func<Process, int[], CancellationToken, Task<RankedTeamSelection>> selectTeam)
        {
            bool started = owned == null || owned.HasExited;
            Process game = started ? await LaunchAsync(progress, true, true).ConfigureAwait(false) : owned;
            progress("Loading your Ranked profile...");
            if (Steer().ContainsKey("ranked_wait"))
            {
                await Task.Delay(30000, cancellation).ConfigureAwait(false);
            }
            RankedTeamSelection selection = await selectTeam(game, new[] { -1, -1 }, cancellation).ConfigureAwait(false);
            cancellation.ThrowIfCancellationRequested();
            RankedIntentRequest request = BeginRankedTeamIntent(game, selection);
            return new RankedLaunchResult { Game = game, Request = request, StartedGame = started, Status = new GameIntentStatus { phase = "search", outcome = "searching", code = "", online = true } };
        }

        public async Task<RankedProgress> LoadRankedProgressAsync()
        {
            if (!HasAccount)
            {
                throw new InvalidOperationException("Start an online game once to create your profile.");
            }
            await ServiceAsync("profile", new { product = "tag2-pc", identity = AccountLoginName }).ConfigureAwait(false);
            return new RankedProgress { Profile = new ProgressProfile { name = AccountLoginName, ranked_wins = "3", ranked_losses = "1", player_wins = "5", player_losses = "2", characters = new[] { 9, 14 }, ranks = new[] { new CharacterRank { character = 9, rank = 4, points = 120, streak = 2 } } } };
        }

        public void Dispose()
        {
            http.Dispose();
        }
    }
}
