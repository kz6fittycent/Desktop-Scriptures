; Inno Setup script for the Windows installer - built by
; .github/workflows/desktop-builds.yml after PyInstaller:
;   iscc /DAppVersion=2.3.0 /DSourceDir="dist\Desktop Scriptures" packaging\windows\installer.iss
;
; Installs per user (no administrator prompt) and supports silent installs
; (/VERYSILENT) for Winget and Chocolatey. Uninstalling leaves the user's
; notes and highlights in %APPDATA%\Desktop Scriptures.

#ifndef AppVersion
  #error AppVersion must be defined
#endif
#ifndef SourceDir
  #error SourceDir must be defined
#endif

[Setup]
AppId={{6F1C2E4A-8B7D-4F3E-9A21-5C0D7E8B9F14}
AppName=Desktop Scriptures
AppVersion={#AppVersion}
AppPublisher=kz6fittycent
AppPublisherURL=https://github.com/kz6fittycent/Desktop-Scriptures
AppSupportURL=https://github.com/kz6fittycent/Desktop-Scriptures/issues
DefaultDirName={autopf}\Desktop Scriptures
DefaultGroupName=Desktop Scriptures
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=Desktop-Scriptures-{#AppVersion}-windows-x64-setup
SetupIconFile=desktop-scriptures.ico
UninstallDisplayIcon={app}\Desktop Scriptures.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Desktop Scriptures"; Filename: "{app}\Desktop Scriptures.exe"
Name: "{autodesktop}\Desktop Scriptures"; Filename: "{app}\Desktop Scriptures.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Desktop Scriptures.exe"; Description: "{cm:LaunchProgram,Desktop Scriptures}"; Flags: nowait postinstall skipifsilent
