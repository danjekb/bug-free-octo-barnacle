# Game Assistant APK Patcher (GitHub Actions)

This repository contains the Smali patcher and a manual GitHub Actions workflow that runs it on an original Oplus Game Assistant APK.

## Run it

1. Open **Actions → Game Assistant APK Patcher → Run workflow**.
2. Paste a **direct HTTPS URL** to the original `Game_Assistant*.apk` file.
3. Select patch groups. Defaults match the current Termux runner's `--gt --caps` configuration.
4. Start the workflow and download the artifact named `game-assistant-patcher-*`.

The artifact contains `Game_Assistant_MOD.apk` (unless `dry_run` is enabled) and diagnostic logs.

## Patch groups

| Input | Patcher flag | Purpose |
|---|---|---|
| GT | `--gt` | GT Mode support check |
| CAPS | `--caps` | OSR/SR, SDR→HDR, EDR, AI tool, MEMC and touch capability checks |
| 4D | `--4d` | 4D vibration feature checks |
| PING | `--ping` | Replaces Baidu ping targets with Google targets |
| TILE | `--tile` | Attempts to expose the System Usage tile; less certain |
| FEAT | `--feat` | Additional software feature checks |
| EXPORT | `--export` | Forces the export flag off; may affect region-dependent services/content |
| RISKY | `--risky` | Enables the optional cache-check patch |

The base patch set runs automatically. `allow_partial` is off by default: if required patch targets are missing or ambiguous, the workflow stops before building. Enable it only after reviewing `patch.log` and deciding that the partial result is acceptable.

`dry_run` decompiles and reports matches without building or signing an APK.

## Stable APK signing (recommended)

Create a keystore locally and store it as repository Actions secrets:

- `GA_KEYSTORE_BASE64`: base64-encoded keystore file
- `GA_KEYSTORE_PASSWORD`: keystore password
- `GA_KEY_ALIAS`: key alias
- `GA_KEY_PASSWORD`: key password (optional; defaults to the keystore password)

Example to encode a keystore without printing its contents:

```bash
base64 -w 0 ga-signing.keystore
```

If the secrets are absent, the workflow creates an ephemeral key. That is convenient for testing, but each run gets a different signing identity; Android will not accept it as an in-place update over an APK signed by another key.

## Toolchain

- Ubuntu 24.04
- Temurin Java 17
- Apktool 2.11.1
- Android Build Tools 35.0.0 (`zipalign`, `apksigner`)

## Important limitations

- Patches are based on Smali method signatures and log-string context. Oplus can change these between Game Assistant releases.
- A patched capability flag does not create missing hardware, vendor services, drivers, framework support, or permissions.
- Review `patch.log`, `build.log`, and signature verification output before installing.
- The original APK's signature is not preserved. Installing may require uninstalling the stock app first, which can remove app data.
