# Packaging FlatCAM Plus

This document is for users who clone the repository and want to create their own local distributable build.

FlatCAM Plus is a Python/PyQt application. Build on the target operating system whenever possible:

- build macOS packages on macOS;
- build Linux packages on Linux;
- build Windows packages on Windows.

Cross-compiling GUI Python applications is fragile because PyQt, OpenGL/VisPy, GDAL, Rasterio, and native wheels are platform-specific.

## Shared Preparation

Start from a clean clone:

```bash
git clone https://github.com/thebestgoodguy/FlatCAM-Plus.git
cd FlatCAM-Plus
```

Create the runtime environment:

```bash
mamba env create -f environment.yml
mamba activate flatcam
```

Verify that the application starts before packaging:

```bash
python flatcam.py
```

Install PyInstaller in the same environment:

```bash
python -m pip install pyinstaller
```

Compile translation catalogs before building. The source repository keeps `.po` files, while runtime translation loading uses `.mo` files:

```bash
find locale -name "strings.po" -exec sh -c 'msgfmt "$1" -o "${1%.po}.mo"' sh {} \;
```

If `msgfmt` is not available, install GNU gettext first. On Ubuntu-like systems use `sudo apt install gettext`. On macOS, install it with Homebrew:

```bash
brew install gettext
export PATH="$(brew --prefix gettext)/bin:$PATH"
```

## Windows

Install Inno Setup 6 first. With `winget`:

```powershell
winget install JRSoftware.InnoSetup
```

For both GitHub release installers, prepare a 64-bit Python environment and a 32-bit Python environment with the project dependencies installed. PyInstaller must run under the same architecture it is packaging.

If both Python launchers are registered, install PyInstaller in each environment:

```powershell
py -3.11-64 -m pip install pyinstaller
py -3.11-32 -m pip install pyinstaller
```

Then build each installer from its own batch file:

```powershell
.\FlatCAMPlus_x64_installer_generator.bat
.\FlatCAMPlus_x32_installer_generator.bat
```

If a batch file fails, it keeps the window open and writes a timestamped log under:

```text
build\logs\
```

If the script cannot auto-detect one of the Python environments, pass the paths explicitly:

```powershell
.\FlatCAMPlus_x64_installer_generator.bat -PythonX64 "C:\Path\To\Python-64\python.exe"
.\FlatCAMPlus_x32_installer_generator.bat -PythonX86 "C:\Path\To\Python-32\python.exe"
```

The PyInstaller outputs are created at:

```text
dist\windows\x86\FlatCAMPlus\
dist\windows\x64\FlatCAMPlus\
```

The installer outputs are created at:

```text
dist\installer\FlatCAMPlus-Setup-<version>-x32.exe
dist\installer\FlatCAMPlus-Setup-<version>-x64.exe
```

The 32-bit build folder still uses the internal `x86` name, but the installer filename uses the user-facing `x32` label.

Upload both files to the GitHub release. The in-app auto updater reads the GitHub release body as the changelog and chooses the installer asset whose filename contains the running architecture (`x32`, `x86`, or `x64`).

The installer installs to:

```text
%ProgramFiles%\FlatCAMPlus
```

It also creates a Start Menu entry and a desktop shortcut for `FlatCAM Plus` by default. To build only one architecture:

```powershell
.\FlatCAMPlus_x64_installer_generator.bat
.\FlatCAMPlus_x32_installer_generator.bat
```

To only build the PyInstaller folders without creating installers:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows_installer.ps1 -SkipInstaller
```

## macOS

Install Apple command line tools first:

```bash
xcode-select --install
```

Build the `.app` bundle:

```bash
python -m PyInstaller flatcam.py \
  --name "FlatCAM-Plus" \
  --windowed \
  --clean \
  --noconfirm \
  --icon "assets/resources/app256.png" \
  --add-data "assets:assets" \
  --add-data "config:config" \
  --add-data "locale:locale" \
  --add-data "preprocessors:preprocessors" \
  --add-data "libs:libs" \
  --collect-submodules appCommon \
  --collect-submodules appEditors \
  --collect-submodules appGUI \
  --collect-submodules appHandlers \
  --collect-submodules appObjects \
  --collect-submodules appParsers \
  --collect-submodules appPlugins \
  --collect-submodules tclCommands \
  --collect-all PyQt6 \
  --collect-all vispy \
  --collect-all shapely \
  --collect-all rasterio
```

The app bundle is created at:

```text
dist/FlatCAM-Plus.app
```

For a local unsigned package, ad-hoc sign the bundle and create a DMG:

```bash
codesign --force --deep --sign - "dist/FlatCAM-Plus.app"
hdiutil create -volname "FlatCAM Plus" \
  -srcfolder "dist/FlatCAM-Plus.app" \
  -ov \
  -format UDZO \
  "FlatCAM-Plus-macOS.dmg"
```

For public macOS distribution, use an Apple Developer ID certificate and notarize the DMG with Apple:

```bash
codesign --force --deep --options runtime --sign "Developer ID Application: YOUR NAME" "dist/FlatCAM-Plus.app"
xcrun notarytool submit "FlatCAM-Plus-macOS.dmg" --apple-id "you@example.com" --team-id "TEAMID" --wait
xcrun stapler staple "FlatCAM-Plus-macOS.dmg"
```

## Linux

On Ubuntu-like systems, install common GUI/OpenGL runtime libraries:

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  libgl1 \
  libegl1 \
  libxkbcommon-x11-0 \
  libxcb-cursor0 \
  libxcb-xinerama0 \
  libspatialindex-dev \
  gdal-bin \
  libgdal-dev
```

Build the Linux folder distribution:

```bash
python -m PyInstaller flatcam.py \
  --name "FlatCAM-Plus" \
  --windowed \
  --clean \
  --noconfirm \
  --add-data "assets:assets" \
  --add-data "config:config" \
  --add-data "locale:locale" \
  --add-data "preprocessors:preprocessors" \
  --add-data "libs:libs" \
  --collect-submodules appCommon \
  --collect-submodules appEditors \
  --collect-submodules appGUI \
  --collect-submodules appHandlers \
  --collect-submodules appObjects \
  --collect-submodules appParsers \
  --collect-submodules appPlugins \
  --collect-submodules tclCommands \
  --collect-all PyQt6 \
  --collect-all vispy \
  --collect-all shapely \
  --collect-all rasterio
```

The Linux build is created at:

```text
dist/FlatCAM-Plus/
```

Create a compressed archive for sharing:

```bash
tar -C dist -czf FlatCAM-Plus-linux-x86_64.tar.gz FlatCAM-Plus
```

The repository also includes a basic Linux install helper in `Makefile` and desktop launcher files in `assets/linux/`. Those are useful for source-based Linux installs, but they are not a full AppImage, DEB, or RPM packaging system.

## Packaging Notes

- Always test import, project open/save, Gerber/Excellon rendering, CNCJob generation, and plugin startup from the packaged app.
- If a package starts but a plugin is missing, add the missing module with another `--collect-submodules` or `--hidden-import` entry and rebuild.
- If VisPy/OpenGL rendering fails on Linux, test on a machine with working OpenGL drivers and confirm the Qt/XCB libraries are installed.
- Do not include `doc/`, `flatcam-cnc-android/`, or development caches in desktop runtime packages unless you intentionally want to ship them.
- Review third-party licenses before distributing commercial packages. PyQt6, Qt, GDAL/Rasterio, and other native dependencies may have license or redistribution requirements.
