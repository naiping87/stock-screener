; Inno Setup script for Stock Screener Pro
; Download Inno Setup from https://jrsoftware.org/isinfo.php
; Run this .iss file through Inno Setup Compiler to generate the installer

[Setup]
AppName=Stock Screener Pro
AppVersion=1.2.10
AppPublisher=StockScreenerPro
DefaultDirName={autopf}\StockScreenerPro
DefaultGroupName=Stock Screener Pro
OutputDir=installer
OutputBaseFilename=StockScreenerPro_Setup
SetupIconFile=resources\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Files]
Source: "dist\StockScreenerPro.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "resources\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\Stock Screener Pro"; Filename: "{app}\StockScreenerPro.exe"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autoprograms}\Stock Screener Pro\Stock Screener Pro"; Filename: "{app}\StockScreenerPro.exe"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autoprograms}\Stock Screener Pro\Uninstall"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\StockScreenerPro.exe"; Description: "Launch Stock Screener Pro"; Flags: nowait postinstall skipifsilent
