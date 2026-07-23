# App Time Guard — Inno Setup 安装脚本
# 需先运行 scripts/build_exe.ps1 生成 dist\app_time_guard.exe
# 再用 Inno Setup Compiler 编译本文件，产出 AppTimeGuard_Setup_x.x.x.exe

#define MyAppName "App Time Guard"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "AI_SYS"
#define MyAppExeName "app_time_guard.exe"
#define MyAppURL "http://127.0.0.1:8765/"

[Setup]
AppId={{8F3C2A91-6B4E-4D71-9C2A-ATGTIMEGUARD01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\AppTimeGuard
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=AppTimeGuard_Setup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=
InfoBeforeFile=
LicenseFile=

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked
Name: "autostart"; Description: "登录时自动启动"; GroupDescription: "开机:"; Flags: unchecked

[Files]
Source: "..\dist\app_time_guard.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\打开管理界面"; Filename: "{#MyAppURL}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--no-browser"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\AppTimeGuard\icon_cache"
