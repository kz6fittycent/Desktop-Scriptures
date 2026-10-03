# Windows and macOS packaging

The snap remains the Linux package. Windows and macOS builds are made by
`.github/workflows/desktop-builds.yml` with PyInstaller:

- **Windows:** `Desktop-Scriptures-<version>-windows-x64-setup.exe`. It's an
  Inno Setup installer (`windows/installer.iss`). It installs per user, with
  no administrator prompt, and supports silent installs with `/VERYSILENT`
  for Winget and Chocolatey. It requires Windows 11.
- **macOS:** `Desktop-Scriptures-<version>-macos-arm64.dmg`, for Apple
  Silicon. Open it and drag the app into Applications.

Each comes with a `.sha256` checksum.

## Releasing

Push a tag matching `__version__`, e.g. `git tag v2.3.0 && git push origin v2.3.0`.
The workflow builds both, runs each packaged app's `--smoke-test`, and
publishes a GitHub Release. To try packaging changes without releasing,
push to the `desktop-builds-test` branch or run the workflow by hand. The
files are then kept as workflow artifacts.

## Unsigned builds

Neither build is code-signed, which costs an Apple Developer account
and a Windows certificate. So the first launch needs one extra step:

- **Windows:** "Windows protected your PC" → **More info** → **Run anyway**.
- **macOS:** the first open is refused. Go to **System Settings → Privacy &
  Security** → **Open Anyway**.

## Where data lives

Bundled files sit inside the app. The user's notes, highlights and study
index live in a writable copy of the database (see `src/scriptures/paths.py`):

- Windows: `%APPDATA%\Desktop Scriptures`
- macOS: `~/Library/Application Support/Desktop Scriptures`

Uninstalling keeps that folder.

## Building locally

```
pip install -r requirements.txt pyinstaller pillow
python scripts/download_tts_voices.py
pyinstaller packaging/desktop-scriptures.spec --noconfirm
"dist/Desktop Scriptures/Desktop Scriptures" --smoke-test
```

PyInstaller builds only for the system it runs on.
