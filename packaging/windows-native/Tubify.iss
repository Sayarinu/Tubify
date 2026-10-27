#ifndef AppVersion
  #error AppVersion must be defined by the build script.
#endif
#ifndef SourceDir
  #error SourceDir must be defined by the build script.
#endif

[Setup]
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
Filename: "{app}\Tubify.exe"; Description: "Launch Tubify"; Flags: postinstall skipifsilent nowait
