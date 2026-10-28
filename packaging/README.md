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

Releases follow the snap: `/promote <revision> stable` on a call-for-testing
issue (promote-to-stable.yml) tags `v<version>` and starts the workflow on
that tag. It builds both, runs each packaged app's `--smoke-test`, and
publishes a GitHub Release. To try packaging changes without releasing,
push to the `desktop-builds-test` branch or run the workflow by hand. The
files are then kept as workflow artifacts.

Package managers pick up each release:

- **Winget** (`kz6fittycent.DesktopScriptures`): the workflow's `winget` job
  opens the winget-pkgs pull request, given the `WINGET_TOKEN` secret.
- **Homebrew:** the tap [kz6fittycent/homebrew-tap](https://github.com/kz6fittycent/homebrew-tap)
  checks daily for a new release and updates its cask.

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
pyinstaller packaging/desktop-scriptures.spec --noconfirm
"dist/Desktop Scriptures/Desktop Scriptures" --smoke-test
```

PyInstaller builds only for the system it runs on.
