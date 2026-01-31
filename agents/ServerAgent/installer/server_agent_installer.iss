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
#define StorcliPath ""
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
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File '{app}\install_task.ps1' -InstallDir '{app}'"; Flags: runhidden
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Start-ScheduledTask -TaskName 'TechTracker Server Agent'"""; Description: "Запустить Server Agent (от имени администратора)"; Flags: postinstall runhidden nowait skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File '{app}\uninstall_task.ps1'"; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  ApiUrlPage: TInputQueryWizardPage;
  TokenPage: TInputQueryWizardPage;
  IdentityPage: TInputQueryWizardPage;
  TimingPage: TInputQueryWizardPage;
  MonitoringPage: TInputQueryWizardPage;
  SyncPage: TInputQueryWizardPage;

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

  IdentityPage := CreateInputQueryPage(TokenPage.ID,
    'Идентификация агента',
    'Серийный номер сервера',
    'Обычно AUTO — агент сам определит серийник.');
  IdentityPage.Add('SerialNumber (AUTO or value):', False);
  IdentityPage.Values[0] := ExpandConstant('{#SerialNumber}');

  TimingPage := CreateInputQueryPage(IdentityPage.ID,
    'Частота сбора',
    'Настройте периодичность',
    'Интервалы в секундах.');
  TimingPage.Add('LoopInterval (sec):', False);
  TimingPage.Values[0] := ExpandConstant('{#LoopInterval}');
  TimingPage.Add('MetricsBatchInterval (sec):', False);
  TimingPage.Values[1] := ExpandConstant('{#MetricsBatchInterval}');
  TimingPage.Add('MetricsQueueMax:', False);
  TimingPage.Values[2] := ExpandConstant('{#MetricsQueueMax}');

  MonitoringPage := CreateInputQueryPage(TimingPage.ID,
    'Мониторинг',
    'Параметры мониторинга',
    'StorCLI и хранение метрик.');
  MonitoringPage.Add('RetentionDays:', False);
  MonitoringPage.Values[0] := ExpandConstant('{#RetentionDays}');
  MonitoringPage.Add('PingTarget:', False);
  MonitoringPage.Values[1] := ExpandConstant('{#PingTarget}');
  MonitoringPage.Add('StorcliPath:', False);
  MonitoringPage.Values[2] := ExpandConstant('{#StorcliPath}');

  SyncPage := CreateInputQueryPage(MonitoringPage.ID,
    'Синхронизация',
    'Интервалы синхронизации',
    'Hyper-V и Debug.');
  SyncPage.Add('VmSyncInterval (sec):', False);
  SyncPage.Values[0] := ExpandConstant('{#VmSyncInterval}');
  SyncPage.Add('MetricsDebug (0/1):', False);
  SyncPage.Values[1] := ExpandConstant('{#MetricsDebug}');
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
      SetIniString('DEFAULT', 'SerialNumber', IdentityPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'LoopInterval', TimingPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'MetricsBatchInterval', TimingPage.Values[1], IniPath);
      SetIniString('DEFAULT', 'MetricsQueueMax', TimingPage.Values[2], IniPath);
      SetIniString('DEFAULT', 'RetentionDays', MonitoringPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'PingTarget', MonitoringPage.Values[1], IniPath);
      SetIniString('DEFAULT', 'StorcliPath', MonitoringPage.Values[2], IniPath);
      SetIniString('DEFAULT', 'VmSyncInterval', SyncPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'MetricsDebug', SyncPage.Values[1], IniPath);
    end;
  end;
end;
