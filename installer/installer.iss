; Inno Setup - NeoFace Unlock
;
; Builds NeoFace-Setup-<version>.exe from ..\dist (assembled by
; installer\build_dist.ps1: app source + bundled Python runtime + CP DLL).
;
; Layout on the target machine:
;   {localappdata}\Programs\NeoFace   app + runtime + models (user-writable)
;   {commonpf64}\NeoFace              FaceUnlockCP.dll + tile bitmaps
;   C:\ProgramData\NeoFace            vault, face gallery, logs (kept on uninstall)

#ifndef MyAppVersion
  #define MyAppVersion "0.5.0"
#endif

[Setup]
AppId={{6E2F0C4A-9B7D-4E18-A3C5-8D1F5B2A7E90}
AppName=NeoFace Unlock
AppVersion={#MyAppVersion}
AppPublisher=NeoFace contributors
DefaultDirName={localappdata}\Programs\NeoFace
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=NeoFace-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=NeoFace Unlock
UninstallDisplayIcon={commonpf64}\NeoFace\FaceUnlockCP.dll
LicenseFile=..\LICENSE
; Install runs elevated for the CP DLL/tasks, but the app itself lives in
; the invoking user's LocalAppData (dashboard/settings write there) - same
; user on both sides of UAC is the supported case.
UsedUserAreasWarning=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Full app payload (face_unlock, tools, templates, static, dashboard,
; runtime\, cp\, installer_scripts\, launchers\) from the dist tree.
; Keep the user's config across updates: Inno uses the FIRST matching
; [Files] entry, so this must precede the wildcard below. The wildcard's
; ignoreversion would otherwise overwrite {app}\config.toml on every update.
Source: "..\dist\config.toml"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "..\dist\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\NeoFace\Dashboard"; Filename: "{app}\launchers\Dashboard.bat"; WorkingDir: "{app}"; Comment: "Open the NeoFace status dashboard"
Name: "{userprograms}\NeoFace\Setup Wizard"; Filename: "{app}\launchers\Setup Wizard.bat"; WorkingDir: "{app}"; Comment: "Set password vault, enroll your face, run a test scan"
Name: "{userprograms}\NeoFace\Test Unlock"; Filename: "{app}\launchers\Test Unlock.bat"; WorkingDir: "{app}"; Comment: "Run a one-off face scan test"
Name: "{userprograms}\NeoFace\Uninstall"; Filename: "{uninstallexe}"

[Registry]
; CP tile CLSID is registered by regsvr32 in post_install.ps1; this entry
; only publishes the provider to Windows and is removed on uninstall.
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{{8F3B2C1D-4E5A-4B7C-9D1F-2A3B4C5D6E7F}"; ValueType: string; ValueName: ""; ValueData: "NeoFace Unlock"; Flags: uninsdeletekey

[Run]
; Runs during install (progress page): models from cloud, DLL registration,
; scheduled tasks. The wizard below is the interactive first-run step.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer_scripts\post_install.ps1"" -AppDir ""{app}"" -Version {#MyAppVersion}"; StatusMsg: "Downloading models and registering the unlock tile..."; Flags: runhidden waituntilterminated
Filename: "{app}\runtime\python.exe"; Parameters: """{app}\tools\setup_wizard.py"""; WorkingDir: "{app}"; Description: "Run setup wizard now (enroll your face)"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{sys}\regsvr32.exe"; Parameters: "/s /u ""{commonpf64}\NeoFace\FaceUnlockCP.dll"""; RunOnceId: "UnregCP"; Flags: runhidden waituntilterminated
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -Command ""Unregister-ScheduledTask -TaskName 'NeoFace-Daemon','NeoFace-UpdateCheck','NeoFaceDaemon','NeoFace-UpdateNotifier' -Confirm:$false -ErrorAction SilentlyContinue"""; RunOnceId: "UnregTasks"; Flags: runhidden waituntilterminated

[UninstallDelete]
; Machine-wide leftovers. C:\ProgramData\NeoFace (vault + face gallery) is
; intentionally kept; wipe it with:  powershell -File uninstall_data.ps1
Type: filesandordirs; Name: "{commonpf64}\NeoFace"
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
begin
  if GetWindowsVersion < $0A000000 then
  begin
    MsgBox('NeoFace Unlock requires Windows 10 or later.', mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;
