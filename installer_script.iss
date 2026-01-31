; Inno Setup 安装脚本 - 剪贴板历史应用
; 使用 Inno Setup 编译器编译此脚本以创建安装程序

#define MyAppName "ClipBook"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ClipBook Team"
#define MyAppExeName "ClipboardHistory.exe"

[Setup]
; 应用基本信息
AppId={{8A9B7C6D-5E4F-3A2B-1C0D-9E8F7A6B5C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=setup
OutputBaseFilename=ClipBook_Setup
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked
Name: "startup"; Description: "开机自动启动"; GroupDescription: "启动选项:"

[Files]
; 复制主程序文件
Source: "dist\ClipboardHistory.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
; 如果使用文件夹模式打包，使用以下配置（注释掉上面的Source行，取消注释下面的行）
; Source: "dist\ClipboardHistory\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
; 安装完成后提供运行选项
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Registry]
; 如果用户选择了开机自启，添加注册表项
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ClipboardHistory"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 安装完成后的自定义操作（如果需要）
  end;
end;

[UninstallDelete]
; 卸载时删除用户数据目录（可选，谨慎使用）
; Type: filesandordirs; Name: "{localappdata}\ClipboardHistory"
