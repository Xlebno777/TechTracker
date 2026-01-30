; Inno Setup installer for TechTracker Server Printer Agent
; Build: open in Inno Setup and Compile

#define AppName "TechTracker Server Printer Agent"
#define AppVersion "1.0.0"
#define AppPublisher "TechTracker"
#define AppExeName "ServerPrinterAgent.exe"

; ---- Wizard input defaults ----
#define ApiUrl "http://127.0.0.1:8000/api/"
#define Token ""
#define SyncInterval "300"
#define ExcludePrinters "adobe pdf, microsoft print to pdf, microsoft xps document writer"

[Setup]
AppId={{9E2B7C19-1E7B-4C4A-A5C9-7A3B25B3C61A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={pf}\TechTracker\ServerPrinterAgent
DefaultGroupName={#AppName}
OutputBaseFilename=server-printer-agent-setup
OutputDir=.
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "printer_agent.ini.template"; DestDir: "{app}"; DestName: "printer_agent.ini"; Flags: overwritereadonly
Source: "install_task.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall_task.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "remove_agent.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File '{app}\install_task.ps1' -InstallDir '{app}'"; Flags: runhidden
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Start-ScheduledTask -TaskName 'TechTracker Server Printer Agent'"""; Description: "Запустить Server Printer Agent (от имени администратора)"; Flags: postinstall runhidden nowait skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File '{app}\uninstall_task.ps1'"; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  ApiUrlPage: TInputQueryWizardPage;
  TokenPage: TInputQueryWizardPage;
  SyncPage: TInputQueryWizardPage;
  FilterPage: TInputQueryWizardPage;

procedure InitializeWizard();
begin
  ApiUrlPage := CreateInputQueryPage(wpWelcome,
    'Настройка API',
    'Укажите адрес API сервера',
    'Введите адрес API сервера, например http://server:8000/api/.');
  ApiUrlPage.Add('ApiUrl:', False);
  ApiUrlPage.Values[0] := ExpandConstant('{#ApiUrl}');

  TokenPage := CreateInputQueryPage(ApiUrlPage.ID,
    'Настройка токена',
    'Укажите токен агента',
    'Введите токен доступа агента (Token).');
  TokenPage.Add('Token:', True);
  TokenPage.Values[0] := ExpandConstant('{#Token}');

  SyncPage := CreateInputQueryPage(TokenPage.ID,
    'Интервал синхронизации',
    'Как часто синхронизировать принтеры',
    'Интервал в секундах.');
  SyncPage.Add('SyncInterval (sec):', False);
  SyncPage.Values[0] := ExpandConstant('{#SyncInterval}');

  FilterPage := CreateInputQueryPage(SyncPage.ID,
    'Фильтр принтеров',
    'Исключаемые принтеры',
    'Ключевые слова через запятую (нижний регистр).');
  FilterPage.Add('ExcludePrinters:', False);
  FilterPage.Values[0] := ExpandConstant('{#ExcludePrinters}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  IniPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    IniPath := ExpandConstant('{app}\printer_agent.ini');
    if FileExists(IniPath) then
    begin
      SetIniString('DEFAULT', 'ApiUrl', ApiUrlPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'Token', TokenPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'SyncInterval', SyncPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'ExcludePrinters', FilterPage.Values[0], IniPath);
    end;
  end;
end;
