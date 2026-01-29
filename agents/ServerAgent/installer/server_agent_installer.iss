; Inno Setup installer for TechTracker Server Agent
; Build: open in Inno Setup and Compile

#define AppName "TechTracker Server Agent"
#define AppVersion "1.0.0"
#define AppPublisher "TechTracker"
#define AppExeName "TechTrackerAgent.exe"

; ---- Wizard input defaults ----
#define ApiUrl "http://127.0.0.1:8000/api/"
#define Token ""
#define SerialNumber "AUTO"
#define LoopInterval "5"
#define MetricsBatchInterval "60"
#define RetentionDays "365"
#define PingTarget ""
#define SmartctlPath ""
#define PrinterSyncInterval "300"
#define VmSyncInterval "60"
#define MetricsQueueMax "5000"
#define MetricsDebug "0"

[Setup]
AppId={{A11D7B5E-4E2B-4C3B-9C58-0D0B0B7E9E10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={pf}\TechTracker\ServerAgent
DefaultGroupName={#AppName}
OutputBaseFilename=server-agent-setup
OutputDir=.
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "server_agent.ini.template"; DestDir: "{app}"; DestName: "config.ini"; Flags: overwritereadonly
Source: "install_task.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall_task.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "remove_agent.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File \"{app}\install_task.ps1\" -InstallDir \"{app}\""; Flags: runhidden
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command \"Start-ScheduledTask -TaskName 'TechTracker Server Agent'\""; Description: "Запустить Server Agent (от имени администратора)"; Flags: postinstall runhidden nowait skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File \"{app}\uninstall_task.ps1\""; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  ApiUrlPage: TInputQueryWizardPage;
  TokenPage: TInputQueryWizardPage;
  OptionsPage: TInputQueryWizardPage;

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

  OptionsPage := CreateInputQueryPage(TokenPage.ID,
    'Параметры агента',
    'Дополнительные параметры',
    'Настройте частоты и сбор метрик.');
  OptionsPage.Add('SerialNumber (AUTO or value):', False);
  OptionsPage.Values[0] := ExpandConstant('{#SerialNumber}');
  OptionsPage.Add('LoopInterval (sec):', False);
  OptionsPage.Values[1] := ExpandConstant('{#LoopInterval}');
  OptionsPage.Add('MetricsBatchInterval (sec):', False);
  OptionsPage.Values[2] := ExpandConstant('{#MetricsBatchInterval}');
  OptionsPage.Add('RetentionDays:', False);
  OptionsPage.Values[3] := ExpandConstant('{#RetentionDays}');
  OptionsPage.Add('PingTarget:', False);
  OptionsPage.Values[4] := ExpandConstant('{#PingTarget}');
  OptionsPage.Add('SmartctlPath:', False);
  OptionsPage.Values[5] := ExpandConstant('{#SmartctlPath}');
  OptionsPage.Add('PrinterSyncInterval (sec):', False);
  OptionsPage.Values[6] := ExpandConstant('{#PrinterSyncInterval}');
  OptionsPage.Add('VmSyncInterval (sec):', False);
  OptionsPage.Values[7] := ExpandConstant('{#VmSyncInterval}');
  OptionsPage.Add('MetricsQueueMax:', False);
  OptionsPage.Values[8] := ExpandConstant('{#MetricsQueueMax}');
  OptionsPage.Add('MetricsDebug (0/1):', False);
  OptionsPage.Values[9] := ExpandConstant('{#MetricsDebug}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  IniPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    IniPath := ExpandConstant('{app}\config.ini');
    if FileExists(IniPath) then
    begin
      SetIniString('DEFAULT', 'ApiUrl', ApiUrlPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'Token', TokenPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'SerialNumber', OptionsPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'LoopInterval', OptionsPage.Values[1], IniPath);
      SetIniString('DEFAULT', 'MetricsBatchInterval', OptionsPage.Values[2], IniPath);
      SetIniString('DEFAULT', 'RetentionDays', OptionsPage.Values[3], IniPath);
      SetIniString('DEFAULT', 'PingTarget', OptionsPage.Values[4], IniPath);
      SetIniString('DEFAULT', 'SmartctlPath', OptionsPage.Values[5], IniPath);
      SetIniString('DEFAULT', 'PrinterSyncInterval', OptionsPage.Values[6], IniPath);
      SetIniString('DEFAULT', 'VmSyncInterval', OptionsPage.Values[7], IniPath);
      SetIniString('DEFAULT', 'MetricsQueueMax', OptionsPage.Values[8], IniPath);
      SetIniString('DEFAULT', 'MetricsDebug', OptionsPage.Values[9], IniPath);
    end;
  end;
end;
