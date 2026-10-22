; ============================================================
;  转发管理器 · 安装包脚本（Inno Setup 6）
;
;  构建：pwsh -File scripts\build-installer.ps1
;  产物：dist\installer\TrafficForwarding-Setup-<版本>.exe
; ============================================================

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "转发管理器"
#define MyAppNameEn "Traffic Forwarding Manager"
#define MyAppPublisher "网络运维"
#define MyAppExeName "traffic-forwarding.exe"
; AppId 是升级/卸载的锚点，一旦发布就不要再改
#define MyAppId "{{9E2A1F0C-6B4D-4F2A-9C71-2D5E8A3B7C41}"
#define MyLangDir AddBackslash(SourcePath) + "languages\"
#define DistDir AddBackslash(SourcePath) + "..\dist\"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments=Windows 端口转发与防火墙规则管理工具（需要管理员权限运行）
DefaultDirName={autopf}\TrafficForwarding
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

; 产物
OutputDir={#DistDir}installer
OutputBaseFilename=TrafficForwarding-Setup-{#MyAppVersion}
SetupIconFile={#DistDir}..\launcher\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; 权限与平台
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; 升级体验
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

; 文件版本信息（资源管理器里能看到）
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppNameEn} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#MyLangDir}ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#DistDir}{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#DistDir}..\README.md"; DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "端口转发与防火墙管理"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
{ 卸载时提示用户数据位置（%LOCALAPPDATA%\TrafficForwarding 里的规则名称/备注不会被删除） }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\TrafficForwarding');
    if DirExists(DataDir) then
      MsgBox('程序已卸载。' + #13#10 + #13#10 +
             '规则名称、备注与审计日志仍保留在：' + #13#10 + DataDir + #13#10 + #13#10 +
             '如需彻底清除，请手动删除该目录。',
             mbInformation, MB_OK);
  end;
end;
