# E87/L8 Badge Writer (Svelte + Web Bluetooth)

Small Svelte app to send image/video files to a BLE badge over:

- Service: `0xFD00`
- Characteristic: `0xAE01`

No Tailwind is used.

## Run

```bash
npm install
npm run dev
```

Then open the local Vite URL in Chrome/Edge (Web Bluetooth required).

## App features

- Connect/disconnect BLE device
- Select multiple image/video files
- Transfer in BLE chunks
- Three protocol modes:
	- `e87-upload`: capture-matched protocol (recommended)
	- `raw`: sends plain file bytes in chunks
	- `framed-v1`: sends simple start/data/end packets
- Adjustable chunk size and inter-chunk delay
- Progress bar + transfer log

### E87 mode details

- Uses FE/DC/BA framed control + data packets observed in capture.
- Subscribes to notify characteristic (`AE02`) and waits for protocol acknowledgements.
- Converts image files to centered/cropped JPEG at **368x368** before upload.
- Video transfer protocol is still not fully reversed.

## Notes

- Web Bluetooth usually requires HTTPS or localhost.
- iOS Safari does not support Web Bluetooth.
- Real badge protocol may differ from `raw` / `framed-v1`; these are practical starting modes for reverse-engineering.
