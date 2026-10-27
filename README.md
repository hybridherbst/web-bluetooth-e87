# E87 Studio

**English** · [Русский](README.ru.md) · [BLE protocol reference](docs/PROTOCOL.md) · [Original web editor](https://hybridherbst.github.io/web-bluetooth-e87/)

A lightweight **Tauri + Rust** app using native Bluetooth and the system WebView instead of bundling Chromium.

A compact, offline editor for circular E87 Bluetooth badges. Prepare an image, a scrolling message, a short video or a looping visual, preview it inside the badge's circle, and send it over Bluetooth.

Built on Felix Herbst's [web-bluetooth-e87](https://github.com/hybridherbst/web-bluetooth-e87). The original browser entry point, BLE transfer protocol, Jieli authentication and AVI writer are preserved; shared photo framing now retains the full source image. The desktop interface is a separate entry point and is currently in **Russian**; the documentation is available in English and Russian.

> Community preview, maintained in the contributor's fork while the upstream PR is under review. These downloads are not an official upstream release.

## Download

**[E87 Studio 1.0.0-beta.3 — installers and SHA-256 checksums](https://github.com/xor334/web-bluetooth-e87/releases/tag/studio-v1.0.0-beta.3)**

Includes the [JPEG compatibility and full-photo cropping fixes](docs/releases/1.0.0-beta.3.md).
If beta.2 produced stripes, regenerate and resend the content from the original files.

| Platform | Packages | Hardware validation |
| --- | --- | --- |
| macOS | Separate DMGs for Apple Silicon and Intel | Initial positive user feedback on Apple Silicon; Intel runtime testing pending |
| Windows x64 | NSIS setup installer | BLE connection and transfer still need testing on Windows |
| Linux x64 | DEB for Ubuntu 22.04+ / compatible Debian systems | BLE connection and transfer still need testing on Linux |

Release assets can be downloaded without a GitHub account. The release notes identify the source commit and distinguish build checks from hardware checks. These are unsigned community builds: macOS uses an ad hoc signature without Developer ID notarization; Windows has no Authenticode certificate. The OS may show a warning on first launch.

## What you can make

- **Images:** position and scale the full photo inside a circular preview, including portrait and panorama edges.
- **Scrolling text:** Cyrillic and Latin text, three font styles, size, speed, direction, colors and optional glow.
- **Studio effects:** Liquid chrome, Pearl, Crimson silk, Aurora, Dichroic, Gold eclipse, After dark and Contour. Generated locally as a still or a loop, alongside the 12 original patterns.
- **Slideshows and video:** ordered image sequences or short clips, converted locally to Motion JPEG AVI.
- **QR codes:** render a link as a badge image.
- **Multiple badges:** explicitly choose a device, give it a name, and keep its MAC/address information locally.

The default window is 920 × 720. Help and file-format guidance live behind `?`; diagnostic logs are collapsed. No account, cloud service, telemetry or runtime internet connection is required by the application.

## Connect a badge

1. Enable Bluetooth on your computer and open the badge's Bluetooth/QR screen.
2. Disconnect the badge from ZRun or an existing browser connection.
3. Click **Подключить** (Connect) and select the intended device. The app never automatically chooses the first E87 it sees.
4. Optionally save a name. If no hardware address is available, enter the address shown on the badge or paste the text decoded from its QR code. QR URLs are parsed locally, not opened.
5. Prepare content, inspect the preview and click **На значок ↗** (Send to badge). Keep the badge nearby until the transfer finishes.

The native module reads the actual MAC from supported E87 manufacturer advertisements (`0x6DB9`). On macOS, the CoreBluetooth UUID is shown separately and is never presented as a hardware MAC. Windows/Linux can additionally provide an OS Bluetooth address. Unknown firmware may require manual address entry; a saved address is a label, not a way to connect to an absent badge.

Names and addresses stay on the current computer. **Забыть** (Forget) removes a local record, not badge content. When upgrading from the Electron beta, enter names/settings again: the system WebView has a separate storage area. Old app data is not erased.

## File formats and limits

| Mode | Input | Badge payload |
| --- | --- | --- |
| Image | PNG, JPEG/JPG, WebP, BMP; GIF as one still frame | JPEG |
| Slideshow | Images, sorted by filename with numeric ordering | Motion JPEG AVI |
| Video | MP4/H.264 recommended; WebM depends on system codecs | Motion JPEG AVI without sound |
| Scrolling text | Up to 80 characters, subject to the duration limit | Motion JPEG AVI |
| Effects | Built-in procedural generators | JPEG or Motion JPEG AVI |
| QR | Link text | JPEG |

- Default output is **368 × 368** until a connected badge reports its screen dimensions. Important content should fit inside the circle.
- The prepared payload must be at most **2,000,000 bytes** (about 1.91 MiB). Source files may be larger.
- Video clips are limited to 10 seconds. Reduce duration or frame rate if the output exceeds the size limit.
- Text loops use 15 fps and at most 240 frames. Longer messages may require a faster speed, smaller type or fewer characters.
- Studio effects offer 3, 5, 6 or 8 seconds, or a single still frame. Some longer effects may exceed the payload limit.
- MOV, HEVC and other codecs depend on system WebView/OS decoders. The file extension alone does not guarantee support.
- **Сохранить** (Save) exports a prepared JPEG/AVI, not an editable project. Reimporting an AVI depends on decoder support.
- “Animations” are frames. ZIP archives, JSON, programs and executable scripts cannot be uploaded.

## Install and run

**macOS 12+:** choose the DMG for Apple Silicon or Intel and drag E87 Studio to Applications. Allow Bluetooth access when prompted. No bundled browser, Python or separate helper is required.

**Windows 10/11 x64:** run the setup installer. The app uses the system Microsoft Edge WebView2 runtime. If missing, the installer downloads it, requiring internet and additional disk space. The small installer size excludes a missing system runtime. A BLE adapter and driver are required.

**Linux x64:** install the DEB through your package manager to resolve dependencies. The app uses shared WebKitGTK 4.1, GTK 3, BlueZ and D-Bus. A minimal system may need a larger first-time dependency download, excluded from our package size. Ubuntu 22.04+ and compatible Debian systems are the packaging target; other distributions can build from source. Video support depends on GStreamer codecs. Chromium/Web Bluetooth flags are no longer needed.

Keep the badge's QR screen open, check OS Bluetooth permission and end other connections if it is missing. Search begins only on request and ends after two minutes. Expand **Журнал** (Log) for errors. Do not run the old and new desktop versions simultaneously.

## Build from source

Install Node.js **22.16+**, npm, stable Rust and the [Tauri platform prerequisites](https://v2.tauri.app/start/prerequisites/): Xcode Command Line Tools on Mac; MSVC C++ build tools/WebView2 on Windows; WebKitGTK 4.1/GTK 3/D-Bus development packages on Linux. Dependencies are locked in `package-lock.json` and `src-tauri/Cargo.lock`.

```sh
npm ci
npm run check
npm run build
cargo test --locked --manifest-path src-tauri/Cargo.toml
npm start
```

```sh
npm run dist:mac     # DMG for the current Mac architecture
npm run dist:win     # Windows NSIS installer
npm run dist:linux   # Linux DEB
```

Build on the corresponding OS. Output is in `src-tauri/target/release/bundle/`. To choose a target, install it with rustup and run `npx tauri build --target <target> --bundles <dmg|nsis|deb> -- --locked`. Target-specific builds include the target name in their output directory. CI builds separate Apple Silicon and Intel packages.

The original web app is available with `npm run dev --workspace web`. `npm run build:web` produces `web/dist/`, honoring `BASE_PATH`. The desktop entry is `web/desktop.html`, output is `web/dist-desktop/`. Assets are embedded in the native executable; the installed app needs no local server.

## Code map

| Area | Responsibility |
| --- | --- |
| `src-tauri/src/main.rs` | Native window, save dialog, transfer close guard and local navigation |
| `src-tauri/src/bluetooth.rs` | CoreBluetooth / WinRT / BlueZ discovery, advertised MACs, GATT, timeouts and MTU fragmentation |
| `web/src/studio/native-bluetooth.ts` | Web Bluetooth interface adapter for the unchanged protocol; explicit selection and notifications |
| `web/src/studio/native.ts` | Narrow native bridge and canvas compatibility for system WebViews |
| `web/src/studio/` | Compact editor, local badge identities, scrolling text and eight Studio effects |
| `web/src/lib/e87-protocol.ts` | Original BLE connection and transfer protocol, unchanged |
| `web/src/jl-auth.ts`, `web/src/avi-builder.ts` | Original authentication and AVI writer, unchanged |
| `.github/workflows/desktop.yml` | Native packages for Mac ARM64/x64, Windows x64 and Linux x64 |

The frontend has no generic filesystem, shell or remote-content access. Saving uses a native user-selected path. Bluetooth commands are restricted to the explicitly selected badge and known E87/battery services. Writes are serialized and fragmented to the negotiated ATT payload size. A local Content Security Policy and navigation restrictions constrain the WebView.

Svelte/TypeScript and regression tests cover search cancellation, stale results, notification delivery, byte boundaries, disconnection, MAC/QR parsing and text limits. Rust tests cover advertising addresses, allowed services and packet sizes. CI builds both browser and desktop entry points and packages all three OSes. These checks do not prove hardware compatibility: the native transport is new in beta.2, so earlier Electron hardware checks do not validate it.

## Credits and protocol reference

The project is based on **Felix Herbst's web-bluetooth-e87**, upstream revision `9e8ba39`. The original README's reverse-engineered BLE protocol reference is preserved in full at **[docs/PROTOCOL.md](docs/PROTOCOL.md)**. See [LICENSE](LICENSE) for the original MIT copyright and license. Native dependency versions are recorded in the Cargo/npm lockfiles; their respective licenses apply.
