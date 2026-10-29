#ifndef AppVersion
  #error AppVersion must be defined by the build script.
#endif
#ifndef SourceDir
  #error SourceDir must be defined by the build script.
#endif

[Setup]
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\Tubify.exe
AppId={{2A5D9328-CE8E-40E4-87D3-223FDEB1C821}
AppName=Tubify
AppVersion={#AppVersion}
AppPublisher=Nouvelle Lune Atelier
DefaultDirName={localappdata}\Programs\Tubify
DefaultGroupName=Tubify
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=.
OutputBaseFilename=Tubify-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=Tubify

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Tubify"; Filename: "{app}\Tubify.exe"
Name: "{autodesktop}\Tubify"; Filename: "{app}\Tubify.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\Tubify.exe"; Description: "Launch Tubify"; Flags: postinstall skipifsilent nowait; Check: not IsUpdate

Filename: "{app}\Tubify.exe"; Flags: nowait; Check: IsUpdate

[Code]
function OpenProcess(Access: LongWord; Inherit: Boolean; Pid: LongWord): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: LongWord): LongWord;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function IsUpdate: Boolean;
begin
  Result := ExpandConstant('{param:TUBIFYUPDATE|0}') = '1';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Pid: Integer;
  Handle: THandle;
begin
  Result := '';
  if IsUpdate then begin
    Pid := StrToIntDef(ExpandConstant('{param:UPDATEPID|0}'), 0);
    if Pid <= 0 then begin
      Result := 'Invalid update process. Close Tubify and run the installer manually.';
      exit;
    end;
    Handle := OpenProcess($00100000, False, Pid);
    if Handle <> 0 then begin
      if WaitForSingleObject(Handle, 60000) <> 0 then
        Result := 'Tubify is still running. Close it and retry the update.';
      CloseHandle(Handle);
    end;
  end;
end;
