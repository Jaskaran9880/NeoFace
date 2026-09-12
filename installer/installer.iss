; Inno Setup - NeoFace
[Setup]
AppName=NeoFace Unlock
AppVersion=0.1.0
DefaultDirName={pf}\NeoFace
PrivilegesRequired=admin

[Files]
Source: "dist\*"; DestDir: "{app}"; Flags: recursesubdirs

[Run]
Filename: "{app}\register_cp.bat"; Flags: runhidden
