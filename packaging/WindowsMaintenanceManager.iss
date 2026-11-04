; Windows Maintenance Manager setup (Inno Setup 6). Built by tools/build_installer.ps1:
;   ISCC /DAppVersion=2.6.0 /DSourceDir=<unzipped release folder> /DOutputDir=<folder> [/DSignToolCmd /Swmmsign=...] WindowsMaintenanceManager.iss
; With a code-signing certificate the setup and its uninstaller are both signed (SmartScreen and antivirus trust them);
; without one the build still works and the setup is simply unsigned.
; It installs into Program Files\WindowsMaintenanceManager, the protected folder the scheduled runs need, and keeps the
; data folder (dati) on uninstall and on upgrade.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\release\WindowsMaintenanceManager"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif

[Setup]
AppId={{6E0B8E52-3C7B-4C1E-9B8F-6A2D5C1F7E31}
AppName=Windows Maintenance Manager
AppVersion={#AppVersion}
AppVerName=Windows Maintenance Manager {#AppVersion}
AppPublisher=mrbot0
AppPublisherURL=https://github.com/mrbot0/WMMS
AppSupportURL=https://github.com/mrbot0/WMMS/issues
AppUpdatesURL=https://github.com/mrbot0/WMMS/releases
DefaultDirName={autopf}\WindowsMaintenanceManager
DisableDirPage=yes
DefaultGroupName=Windows Maintenance Manager
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=WindowsMaintenanceManager-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
UninstallDisplayName=Windows Maintenance Manager
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Windows Maintenance Manager setup
#ifdef SignToolCmd
SignTool=wmmsign
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "dati\*,__pycache__\*,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\dati"; Flags: uninsneveruninstall

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Icons]
Name: "{autoprograms}\Windows Maintenance Manager"; Filename: "{app}\start_wmm.bat"; WorkingDir: "{app}"; Comment: "Maintenance console for this PC"
Name: "{autodesktop}\Windows Maintenance Manager"; Filename: "{app}\start_wmm.bat"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\start_wmm.bat"; Description: "{cm:LaunchProgram,Windows Maintenance Manager}"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent shellexec

[Code]
{ The console runs on Python 3.9 or newer installed for all users. When it is missing the setup offers to install
  Python 3.12 with winget (the winget package declares the same dependency, so "winget install" brings it by itself). }
function PythonFound(): Boolean;
var
  Code: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/c python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"', '',
    SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if (CurStep = ssPostInstall) and not PythonFound() then
  begin
    if WizardSilent() or (MsgBox('Windows Maintenance Manager needs Python 3.9 or newer, installed for all users.' + #13#10 +
        'Install Python 3.12 now with winget?', mbConfirmation, MB_YESNO) = IDYES) then
      Exec('winget', 'install --id Python.Python.3.12 --scope machine --silent --accept-package-agreements --accept-source-agreements', '',
        SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;
