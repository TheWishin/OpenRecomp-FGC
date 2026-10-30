/* MIT; build manually with the Windows SDK, see docs/PACKAGING.md. */
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <wchar.h>
#include <stdlib.h>
#include "startup-locales.h"

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR arguments, int show) {
    wchar_t module[32768], home[32768];
    DWORD count = GetModuleFileNameW(NULL, module, 32768);
    if (!count || count >= 32768) return 1;
    wchar_t *slash = wcsrchr(module, L'\\');
    if (!slash) return 1;
    *slash = 0;
    DWORD home_length = GetEnvironmentVariableW(L"OPENRECOMP_HOME", home, 32768);
    if (!home_length) {
        if (SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, SHGFP_TYPE_CURRENT, home) != S_OK)
            return 1;
        if (wcslen(home) + 13 >= 32768) return 1;
        wcscat_s(home, 32768, L"\\OpenRecomp");
        if (!SetEnvironmentVariableW(L"OPENRECOMP_HOME", home)) return 1;
    } else if (home_length >= 32768) return 1;
    size_t capacity = 2 * wcslen(module) + wcslen(arguments) + 100;
    wchar_t *command = calloc(capacity, sizeof(wchar_t));
    wchar_t *python = calloc(wcslen(module) + 30, sizeof(wchar_t));
    if (!command || !python) { free(command); free(python); return 1; }
    swprintf_s(python, wcslen(module) + 30, L"%s\\python\\pythonw.exe", module);
    swprintf_s(command, capacity, L"\"%s\" -I -B \"%s\\openrecomp_boot.py\" %s", python, module, arguments);
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    BOOL started = CreateProcessW(python, command, NULL, NULL, FALSE, 0, NULL, module, &startup, &process);
    free(command);
    free(python);
    if (!started) {
        MessageBoxW(NULL, startup_failure(GetUserDefaultUILanguage()),
                    L"OpenRecomp", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD result = 1;
    GetExitCodeProcess(process.hProcess, &result);
    CloseHandle(process.hProcess);
    return (int)result;
}
