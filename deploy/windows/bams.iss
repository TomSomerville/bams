; BAMS Windows installer (Inno Setup 6). Build it with `python deploy/build.py windows`, which stages the
; files and passes the /D defines below. See deploy/README.md.
;
; One installer does both jobs: a first install, and an update over an existing install (same AppId).
; An update stops the service, replaces the program files, keeps the service registration, the data dir
; (C:\ProgramData\BAMS: database, accounts, settings, artwork) and the earlier choices, then starts BAMS again.
; Database migrations run by themselves when the new version starts (backing the DB up first).

#ifndef AppVersion
  #error Build with: python deploy/build.py windows
#endif
#define Port "8484"
#define ServiceId "BAMS"
#define FirewallRule "BAMS Media Server"

[Setup]
AppId={{6B1D7C52-3E0A-4F7B-9B8E-2C4A1D5E9F30}
AppName=BAMS
AppVersion={#AppVersion}
AppVerName=BAMS {#AppVersion}
AppPublisher=BAMS
AppComments=Bad Ass Media Server
AppPublisherURL=https://github.com/TomSomerville/bams
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\BAMS
DisableDirPage=auto
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Windows 10 1809+: tar.exe (unpacks FFmpeg) and Python 3.13 need it
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=BAMS-Setup-{#AppVersion}
SetupIconFile=bams.ico
UninstallDisplayIcon={app}\bams.ico
UninstallDisplayName=BAMS - Bad Ass Media Server
WizardStyle=modern
WizardSmallImageFile=wizard-small.png
Compression=lzma2/max
SolidCompression=yes
; the service is stopped by our own code before files are replaced
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "network"; Description: "Let other devices on my home network watch BAMS (TVs, phones, tablets, other computers). Everyone signs in."; GroupDescription: "Sharing:"
Name: "desktopicon"; Description: "Put a BAMS shortcut on the desktop"; GroupDescription: "Shortcuts:"

[InstallDelete]
; program files only, so an update never mixes old and new modules. The data dir is elsewhere; FFmpeg is kept.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\lib"
Type: filesandordirs; Name: "{app}\app"

[Files]
Source: "{#Stage}\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Stage}\lib\*"; DestDir: "{app}\lib"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Stage}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Stage}\service\bams-service.exe"; DestDir: "{app}\service"; Flags: ignoreversion
Source: "{#Stage}\bams.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\bams.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[INI]
Filename: "{app}\BAMS.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:{#Port}/"
Filename: "{app}\BAMS.url"; Section: "InternetShortcut"; Key: "IconFile"; String: "{app}\bams.ico"
Filename: "{app}\BAMS.url"; Section: "InternetShortcut"; Key: "IconIndex"; String: "0"
Filename: "{app}\TMDB key guide.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:{#Port}/help/tmdb.html"
Filename: "{app}\TMDB key guide.url"; Section: "InternetShortcut"; Key: "IconFile"; String: "{app}\bams.ico"
Filename: "{app}\TMDB key guide.url"; Section: "InternetShortcut"; Key: "IconIndex"; String: "0"

[Icons]
Name: "{autoprograms}\BAMS"; Filename: "{app}\BAMS.url"; IconFilename: "{app}\bams.ico"; Comment: "Open BAMS in your web browser"
Name: "{autoprograms}\BAMS - How to get a TMDB key"; Filename: "{app}\TMDB key guide.url"; IconFilename: "{app}\bams.ico"
Name: "{autodesktop}\BAMS"; Filename: "{app}\BAMS.url"; IconFilename: "{app}\bams.ico"; Tasks: desktopicon

[UninstallDelete]
Type: files; Name: "{app}\BAMS.url"
Type: files; Name: "{app}\TMDB key guide.url"
Type: filesandordirs; Name: "{app}\ffmpeg"
Type: filesandordirs; Name: "{app}\service"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\lib"
Type: filesandordirs; Name: "{app}\app"
Type: dirifempty; Name: "{app}"

[Run]
Filename: "http://localhost:{#Port}/"; Description: "Open BAMS now"; Flags: postinstall shellexec nowait skipifsilent runasoriginaluser; Check: ServerIsUp

[Code]
var
  DownloadPage: TDownloadWizardPage;
  FFmpegDownloaded: Boolean;
  ServerUp: Boolean;
  PreviousVersion: String;

function DataDir: String;
begin
  Result := ExpandConstant('{commonappdata}\BAMS');
end;

function ServiceExe: String;
begin
  Result := ExpandConstant('{app}\service\bams-service.exe');
end;

function ServerIsUp: Boolean;
begin
  Result := ServerUp;
end;

function IsUpgrade: Boolean;
begin
  Result := PreviousVersion <> '';
end;

function ServiceRegistered: Boolean;
begin
  Result := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\{#ServiceId}');
end;

function RunHidden(const Exe, Params: String): Integer;
begin
  if not Exec(Exe, Params, '', SW_HIDE, ewWaitUntilTerminated, Result) then
    Result := -1;
  Log(Format('ran %s %s -> %d', [Exe, Params, Result]));
end;

function ServiceStopped: Boolean;
begin
  // find exits 0 when sc reports the service as STOPPED
  Result := RunHidden(ExpandConstant('{cmd}'), '/c ' + ExpandConstant('{sys}\sc.exe') +
    ' query {#ServiceId} | ' + ExpandConstant('{sys}\find.exe') + ' "STOPPED"') = 0;
end;

function FFmpegCurrent: Boolean;
var
  Installed: AnsiString;
begin
  Result := FileExists(ExpandConstant('{app}\ffmpeg\bin\ffmpeg.exe'))
    and LoadStringFromFile(ExpandConstant('{app}\ffmpeg\bams-ffmpeg-version.txt'), Installed)
    and (Trim(String(Installed)) = '{#FFmpegVersion}');
end;

function ServerAnswers: Boolean;
var
  Http: Variant;
begin
  Result := False;
  try
    Http := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    Http.SetTimeouts(2000, 2000, 2000, 2000);
    Http.Open('GET', 'http://127.0.0.1:{#Port}/api/auth/state', False);
    Http.Send('');
    Result := Http.Status = 200;
  except
    Result := False;
  end;
end;

function InitializeSetup: Boolean;
begin
  if not RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6B1D7C52-3E0A-4F7B-9B8E-2C4A1D5E9F30}_is1',
                             'DisplayVersion', PreviousVersion) then
    PreviousVersion := '';
  Result := True;
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Downloading FFmpeg',
    'BAMS uses FFmpeg to read and convert video. It is downloaded from its publisher (about {#FFmpegSizeMB} MB).',
    @OnDownloadProgress);
end;

// An update keeps the choices made the first time: no questions, just Install.
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := IsUpgrade and (PageID = wpSelectTasks);
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo,
  MemoGroupInfo, MemoTasksInfo: String): String;
begin
  if IsUpgrade then
    Result := 'BAMS ' + PreviousVersion + ' will be updated to {#AppVersion}.' + NewLine +
      'Your libraries, accounts, watch history and settings are kept. BAMS stops for a moment during the update.'
  else
    Result := 'BAMS {#AppVersion} will be installed in:' + NewLine + Space + ExpandConstant('{app}') + NewLine + NewLine +
      'It runs in the background as a Windows service and starts with the computer.';
  if MemoTasksInfo <> '' then
    Result := Result + NewLine + NewLine + MemoTasksInfo;
  if not FFmpegCurrent then
    Result := Result + NewLine + NewLine + 'FFmpeg {#FFmpegVersion} will be downloaded (about {#FFmpegSizeMB} MB).';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and not FFmpegCurrent then begin
    DownloadPage.Clear;
    DownloadPage.Add('{#FFmpegUrl}', 'ffmpeg.zip', '{#FFmpegSha256}');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        FFmpegDownloaded := True;
      except
        if DownloadPage.AbortedByUser then
          Result := False
        else
          SuppressibleMsgBox('FFmpeg could not be downloaded:' + #13#10 + GetExceptionMessage + #13#10#13#10 +
            'BAMS will be installed anyway, but it needs FFmpeg to play most videos. ' +
            'Run this installer again when the computer is online to get it.', mbError, MB_OK, IDOK);
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if ServiceRegistered then begin
    // `net stop` waits until the service has stopped (BAMS shuts down its FFmpeg processes)
    RunHidden(ExpandConstant('{sys}\net.exe'), 'stop {#ServiceId}');
    Sleep(1000);
  end;
end;

procedure InstallFFmpeg;
var
  Zip, Tmp: String;
begin
  WizardForm.StatusLabel.Caption := 'Unpacking FFmpeg...';
  Zip := ExpandConstant('{tmp}\ffmpeg.zip');
  Tmp := ExpandConstant('{app}\ffmpeg.new');
  DelTree(Tmp, True, True, True);
  ForceDirectories(Tmp);
  RunHidden(ExpandConstant('{sys}\tar.exe'), '-xf "' + Zip + '" -C "' + Tmp + '"');
  if not FileExists(Tmp + '\{#FFmpegFolder}\bin\ffmpeg.exe') then begin
    SuppressibleMsgBox('FFmpeg could not be unpacked. BAMS will be installed anyway; run this installer again to retry.',
      mbError, MB_OK, IDOK);
    DelTree(Tmp, True, True, True);
    exit;
  end;
  DelTree(ExpandConstant('{app}\ffmpeg'), True, True, True);
  RenameFile(Tmp + '\{#FFmpegFolder}', ExpandConstant('{app}\ffmpeg'));
  DelTree(Tmp, True, True, True);
  // headers and import libraries are for programmers; BAMS only runs bin\
  DelTree(ExpandConstant('{app}\ffmpeg\include'), True, True, True);
  DelTree(ExpandConstant('{app}\ffmpeg\lib'), True, True, True);
  DelTree(ExpandConstant('{app}\ffmpeg\doc'), True, True, True);
  SaveStringToFile(ExpandConstant('{app}\ffmpeg\bams-ffmpeg-version.txt'), '{#FFmpegVersion}', False);
end;

procedure WriteServiceConfig;
var
  Host, Xml: String;
begin
  if WizardIsTaskSelected('network') then Host := '0.0.0.0' else Host := '127.0.0.1';
  // WinSW reads this at every service start, so an update only has to rewrite it
  Xml :=
    '<service>' + #13#10 +
    '  <id>{#ServiceId}</id>' + #13#10 +
    '  <name>BAMS Media Server</name>' + #13#10 +
    '  <description>BAMS - Bad Ass Media Server: your movies, shows and music at http://localhost:{#Port}</description>' + #13#10 +
    '  <executable>%BASE%\..\python\python.exe</executable>' + #13#10 +
    '  <arguments>-m bams serve --host ' + Host + ' --port {#Port}</arguments>' + #13#10 +
    '  <env name="BAMS_DATA_DIR" value="' + DataDir + '"/>' + #13#10 +
    '  <env name="PYTHONIOENCODING" value="utf-8"/>' + #13#10 +
    '  <startmode>Automatic</startmode>' + #13#10 +
    '  <onfailure action="restart" delay="10 sec"/>' + #13#10 +
    '  <onfailure action="restart" delay="30 sec"/>' + #13#10 +
    '  <resetfailure>1 hour</resetfailure>' + #13#10 +
    '  <stoptimeout>20 sec</stoptimeout>' + #13#10 +
    '  <logpath>' + DataDir + '\logs</logpath>' + #13#10 +
    '  <log mode="roll-by-size"><sizeThreshold>2048</sizeThreshold><keepFiles>2</keepFiles></log>' + #13#10 +
    '</service>' + #13#10;
  SaveStringToFile(ExpandConstant('{app}\service\bams-service.xml'), Xml, False);
end;

procedure SecureDataDir;
begin
  // the database holds password hashes, sessions and the TMDB key: SYSTEM and Administrators only
  // Only the folder gets explicit rights; everything in it inherits them. (Never `/inheritance:r /T`: on files
  // it strips the inherited rights and the (OI)(CI) grant doesn't apply to files, leaving them unreadable even
  // to SYSTEM. The /reset also repairs files an earlier installer left like that.)
  ForceDirectories(DataDir + '\logs');
  RunHidden(ExpandConstant('{sys}\icacls.exe'),
    '"' + DataDir + '" /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F /C /Q');
  RunHidden(ExpandConstant('{sys}\icacls.exe'), '"' + DataDir + '\*" /reset /T /C /Q');
end;

procedure SetFirewall;
var
  Netsh: String;
begin
  Netsh := ExpandConstant('{sys}\netsh.exe');
  RunHidden(Netsh, 'advfirewall firewall delete rule name="{#FirewallRule}"');
  if WizardIsTaskSelected('network') then
    RunHidden(Netsh, 'advfirewall firewall add rule name="{#FirewallRule}" dir=in action=allow protocol=TCP ' +
      'localport={#Port} profile=private,domain description="Lets devices on your home network watch BAMS"');
end;

procedure StartServer;
var
  i: Integer;
begin
  WizardForm.StatusLabel.Caption := 'Starting BAMS...';
  if not ServiceRegistered then
    RunHidden(ServiceExe, 'install');
  RunHidden(ServiceExe, 'start');
  // the first start after an update may migrate the database: give it up to a minute
  for i := 1 to 60 do begin
    if ServerAnswers then begin
      ServerUp := True;
      exit;
    end;
    // gave up (Windows has already stopped the service): no point waiting out the minute
    if (i mod 5 = 0) and ServiceStopped then
      exit;
    Sleep(1000);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    if FFmpegDownloaded then
      InstallFFmpeg;
    SecureDataDir;
    WriteServiceConfig;
    SetFirewall;
    StartServer;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Text: String;
begin
  if CurPageID <> wpFinished then exit;
  if not ServerUp then
    Text := 'BAMS was installed, but it did not answer yet. Restart the computer; if it still does not open, ' +
      'look at the log files in ' + DataDir + '\logs.'
  else if IsUpgrade then
    Text := 'BAMS is updated to {#AppVersion} and running again. Everything you set up is still there.'
  else begin
    Text := 'BAMS is running. It starts by itself whenever this computer starts.' + #13#10#13#10 +
      'Open BAMS on this computer first (http://localhost:{#Port}) to create your admin account, then add your ' +
      'TMDB key (the Start menu has a guide) and your folders.';
    if WizardIsTaskSelected('network') then
      Text := Text + #13#10#13#10 + 'Other devices on your network: http://' + GetComputerNameString + ':{#Port}';
  end;
  WizardForm.FinishedLabel.Caption := Text;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then begin
    if ServiceRegistered then begin
      RunHidden(ExpandConstant('{sys}\net.exe'), 'stop {#ServiceId}');
      RunHidden(ServiceExe, 'uninstall');
    end;
    RunHidden(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="{#FirewallRule}"');
  end;
  if (CurUninstallStep = usPostUninstall) and DirExists(DataDir) then
    if SuppressibleMsgBox('Also delete BAMS''s own data (accounts, libraries list, watch history, settings and ' +
        'downloaded artwork)?' + #13#10#13#10 + 'Your media files are never touched either way. Keep it if you ' +
        'might install BAMS again.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(DataDir, True, True, True);
end;
