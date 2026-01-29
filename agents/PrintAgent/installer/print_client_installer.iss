; Inno Setup installer for TechTracker Print Client
; Build: open in Inno Setup and Compile

#define AppName "TechTracker Print Client"
#define AppVersion "1.0.0"
#define AppPublisher "TechTracker"
#define AppExeName "print_client.exe"

; ---- Wizard input defaults ----
#define ApiUrl "http://127.0.0.1:8000/api/"
#define Token ""
#define SendSerial "0"
#define SerialNumber "AUTO"
#define PrinterMapRefreshSec "300"

[Setup]
AppId={{1F8E62E5-3DB3-4E0E-9E9E-6E6CE4A6D4E3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={pf}\TechTracker\PrintClient
DefaultGroupName={#AppName}
OutputBaseFilename=print-client-setup
OutputDir=.
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "print_client.ini.template"; DestDir: "{app}"; DestName: "print_client.ini"; Flags: overwritereadonly
Source: "install_task.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall_task.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "autostart"; Description: "Добавить в автозапуск (служба SYSTEM)"; Flags: checkedonce

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install_task.ps1"" -InstallDir ""{app}"""; Flags: runhidden
Filename: "{app}\{#AppExeName}"; Description: "Запустить Print Client"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\uninstall_task.ps1"""; Flags: runhidden

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
    'Параметры клиента',
    'Дополнительные параметры',
    'Настройте опции отправки.');
  OptionsPage.Add('SendSerial (0/1):', False);
  OptionsPage.Values[0] := ExpandConstant('{#SendSerial}');
  OptionsPage.Add('SerialNumber (AUTO or value):', False);
  OptionsPage.Values[1] := ExpandConstant('{#SerialNumber}');
  OptionsPage.Add('PrinterMapRefreshSec:', False);
  OptionsPage.Values[2] := ExpandConstant('{#PrinterMapRefreshSec}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  IniPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    IniPath := ExpandConstant('{app}\print_client.ini');
    if FileExists(IniPath) then
    begin
      SetIniString('DEFAULT', 'ApiUrl', ApiUrlPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'Token', TokenPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'SendSerial', OptionsPage.Values[0], IniPath);
      SetIniString('DEFAULT', 'SerialNumber', OptionsPage.Values[1], IniPath);
      SetIniString('DEFAULT', 'PrinterMapRefreshSec', OptionsPage.Values[2], IniPath);
    end;
  end;
end;
