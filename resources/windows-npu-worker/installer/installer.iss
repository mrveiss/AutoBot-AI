; AutoBot NPU Worker - Inno Setup Installer Script
; Professional Windows installer with service integration

#define MyAppName "AutoBot NPU Worker"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AutoBot Development Team"
#define MyAppURL "https://github.com/autobot/autobot"
#define MyAppExeName "AutoBotNPUWorker.exe"
#define MyServiceName "AutoBotNPUWorker"
#define MyServiceDisplayName "AutoBot NPU Worker (Windows)"
#define MyServiceDescription "AutoBot optional NPU worker for hardware-accelerated AI processing"

[Setup]
; Basic application information
AppId={{8A9B1C2D-3E4F-5A6B-7C8D-9E0F1A2B3C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\AutoBot\NPU
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
InfoBeforeFile=..\README.md
OutputDir=.\output
OutputBaseFilename=AutoBot-NPU-Worker-Setup-{#MyAppVersion}
SetupIconFile=.\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; Installer UI
WizardImageFile=.\assets\banner.bmp
WizardSmallImageFile=.\assets\icon.ico
DisableWelcomePage=no
DisableProgramGroupPage=yes
DisableReadyPage=no

; Uninstaller
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "installservice"; Description: "Install as Windows Service (recommended)"; GroupDescription: "Service Installation:"; Flags: checked
Name: "autostartservice"; Description: "Start service automatically at Windows startup"; GroupDescription: "Service Configuration:"; Flags: checked
Name: "configurefirewall"; Description: "Configure Windows Firewall (required for network access)"; GroupDescription: "Network Configuration:"; Flags: checked
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main application files (from PyInstaller dist)
Source: "..\dist\AutoBotNPUWorker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Configuration files
Source: "..\config\npu_worker.yaml"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\config\*.yaml"; DestDir: "{app}\config"; Flags: ignoreversion

; Management scripts
Source: "..\scripts\*.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion

; Documentation
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\DEPLOYMENT_SUMMARY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\INSTALLATION.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\BUILDING.md"; DestDir: "{app}"; Flags: ignoreversion

; NSSM (Service manager) - downloaded during install
Source: ".\resources\nssm\nssm.exe"; DestDir: "{app}\nssm"; Flags: ignoreversion

; Python embedded (optional - include if bundled)
; Source: ".\resources\python-embed\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\models"; Permissions: users-modify
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\config"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Start NPU Worker Service"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\start-service.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Stop NPU Worker Service"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\stop-service.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Check Health"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\check-health.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\View Logs"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\view-logs.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Install VC++ Redistributables if needed
Filename: "{tmp}\vcredist_x64.exe"; Parameters: "/quiet /norestart"; StatusMsg: "Installing Visual C++ Redistributables..."; Flags: skipifdoesntexist

; Download NSSM if not included
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""if (-not (Test-Path '{app}\nssm\nssm.exe')) {{ Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile '{tmp}\nssm.zip'; Expand-Archive -Path '{tmp}\nssm.zip' -DestinationPath '{tmp}\nssm' -Force; Copy-Item '{tmp}\nssm\nssm-2.24\win64\nssm.exe' -Destination '{app}\nssm\' -Force }}"""; StatusMsg: "Downloading NSSM service manager..."; Flags: runhidden

; Configure firewall rule
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""New-NetFirewallRule -DisplayName 'AutoBot NPU Worker' -Direction Inbound -Protocol TCP -LocalPort 8082 -Action Allow -Profile Any -ErrorAction SilentlyContinue"""; StatusMsg: "Configuring Windows Firewall..."; Flags: runhidden; Tasks: configurefirewall

; Install Windows service
Filename: "{app}\nssm\nssm.exe"; Parameters: "install {#MyServiceName} ""{app}\{#MyAppExeName}"""; StatusMsg: "Installing Windows Service..."; Flags: runhidden; Tasks: installservice
Filename: "{app}\nssm\nssm.exe"; Parameters: "set {#MyServiceName} DisplayName ""{#MyServiceDisplayName}"""; Flags: runhidden; Tasks: installservice
Filename: "{app}\nssm\nssm.exe"; Parameters: "set {#MyServiceName} Description ""{#MyServiceDescription}"""; Flags: runhidden; Tasks: installservice
Filename: "{app}\nssm\nssm.exe"; Parameters: "set {#MyServiceName} Start SERVICE_AUTO_START"; Flags: runhidden; Tasks: installservice autostartservice
Filename: "{app}\nssm\nssm.exe"; Parameters: "set {#MyServiceName} AppDirectory ""{app}"""; Flags: runhidden; Tasks: installservice
Filename: "{app}\nssm\nssm.exe"; Parameters: "set {#MyServiceName} AppStdout ""{app}\logs\service.log"""; Flags: runhidden; Tasks: installservice
Filename: "{app}\nssm\nssm.exe"; Parameters: "set {#MyServiceName} AppStderr ""{app}\logs\error.log"""; Flags: runhidden; Tasks: installservice
Filename: "{app}\nssm\nssm.exe"; Parameters: "set {#MyServiceName} AppRotateFiles 1"; Flags: runhidden; Tasks: installservice
Filename: "{app}\nssm\nssm.exe"; Parameters: "set {#MyServiceName} AppRotateBytes 10485760"; Flags: runhidden; Tasks: installservice

; Start service
Filename: "{app}\nssm\nssm.exe"; Parameters: "start {#MyServiceName}"; StatusMsg: "Starting NPU Worker Service..."; Flags: runhidden; Tasks: installservice autostartservice

; Show README
Filename: "{app}\README.md"; Description: "{cm:LaunchProgram,README}"; Flags: postinstall shellexec skipifsilent

; Open health check URL
Filename: "http://localhost:8082/health"; Description: "Check NPU Worker Health"; Flags: postinstall shellexec skipifsilent

[UninstallRun]
; Stop and remove service
Filename: "{app}\nssm\nssm.exe"; Parameters: "stop {#MyServiceName}"; Flags: runhidden
Filename: "{app}\nssm\nssm.exe"; Parameters: "remove {#MyServiceName} confirm"; Flags: runhidden

; Remove firewall rule
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Remove-NetFirewallRule -DisplayName 'AutoBot NPU Worker' -ErrorAction SilentlyContinue"""; Flags: runhidden

[UninstallDelete]
Type: files; Name: "{app}\logs\*.log"
Type: dirifempty; Name: "{app}\logs"
Type: dirifempty; Name: "{app}\models"
Type: dirifempty; Name: "{app}\data"

[Code]
var
  DataDirPage: TInputDirWizardPage;
  KeepDataCheckbox: TNewCheckBox;

procedure InitializeWizard;
begin
  // Add custom page for data directory preservation
  DataDirPage := CreateInputDirPage(wpSelectDir,
    'Data Directory Options', 'Choose data directory handling',
    'The installer can preserve or remove data directories during uninstall.' + #13#10 +
    'Choose how you want to handle existing data:',
    False, '');
  DataDirPage.Add('Data directory:');
  DataDirPage.Values[0] := ExpandConstant('{app}\data');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Create initial directories
    if not DirExists(ExpandConstant('{app}\logs')) then
      CreateDir(ExpandConstant('{app}\logs'));
    if not DirExists(ExpandConstant('{app}\models')) then
      CreateDir(ExpandConstant('{app}\models'));
    if not DirExists(ExpandConstant('{app}\data')) then
      CreateDir(ExpandConstant('{app}\data'));
  end;
end;

function InitializeUninstall(): Boolean;
var
  Response: Integer;
begin
  Response := MsgBox('Do you want to keep the data and log directories?' + #13#10 +
    'Select Yes to preserve your data, No to remove everything.',
    mbConfirmation, MB_YESNOCANCEL);

  if Response = IDCANCEL then
  begin
    Result := False;
    Exit;
  end;

  if Response = IDYES then
  begin
    // Keep data - handled by UninstallDelete conditional
    Result := True;
  end
  else
  begin
    // Remove all data
    Result := True;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    MsgBox('AutoBot NPU Worker has been successfully uninstalled.' + #13#10 +
      'Thank you for using AutoBot!', mbInformation, MB_OK);
  end;
end;

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nAutoBot NPU Worker provides optional hardware-accelerated AI processing using Intel OpenVINO NPU.%n%nIt is recommended that you close all other applications before continuing.
FinishedLabel=Setup has finished installing [name] on your computer. The application may be launched by selecting the installed shortcuts.

[CustomMessages]
LaunchProgram=Open README file
