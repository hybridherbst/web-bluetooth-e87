use jpeg_encoder::{ColorType, Encoder, SamplingFactor};
use tauri::ipc::{InvokeBody, Request, Response};

fn encode_rgba(rgba: &[u8], width: u16, height: u16, quality: u8) -> Result<Vec<u8>, String> {
    if width == 0 || height == 0 || width > 1024 || height > 1024 || !(1..=100).contains(&quality) {
        return Err("Invalid JPEG dimensions or quality".into());
    }
    let pixels = usize::from(width) * usize::from(height);
    if rgba.len() != pixels * 4 {
        return Err("Invalid RGBA buffer length".into());
    }
    // Canvas JPEG export composites transparent pixels on black. Keep that behavior.
    let rgb: Vec<u8> = rgba
        .as_chunks::<4>()
        .0
        .iter()
        .flat_map(|p| {
            let alpha = u16::from(p[3]);
            [p[0], p[1], p[2]].map(|c| ((u16::from(c) * alpha + 127) / 255) as u8)
        })
        .collect();
    let mut jpeg = Vec::new();
    let mut encoder = Encoder::new(&mut jpeg, quality);
    // WebKit's macOS encoder inserts a restart marker at every MCU row. The E87
    // decoder shows the first row, then stripes. Use baseline 4:2:0 with no DRI/RST,
    // independent of WebView, OS, and quality (including qualities >= 90).
    encoder.set_sampling_factor(SamplingFactor::R_4_2_0);
    encoder.set_progressive(false);
    encoder.set_restart_interval(0);
    encoder
        .encode(&rgb, width, height, ColorType::Rgb)
        .map_err(|e| e.to_string())?;
    Ok(jpeg)
}

#[tauri::command]
pub fn encode_badge_jpeg(request: Request<'_>) -> Result<Response, String> {
    let InvokeBody::Raw(rgba) = request.body() else {
        return Err("Expected raw RGBA pixels".into());
    };
    let header = |name| {
        request
            .headers()
            .get(name)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.parse::<u16>().ok())
            .ok_or_else(|| format!("Invalid {name}"))
    };
    let width = header("x-e87-width")?;
    let height = header("x-e87-height")?;
    let quality = u8::try_from(header("x-e87-quality")?).map_err(|e| e.to_string())?;
    encode_rgba(rgba, width, height, quality).map(Response::new)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn badge_jpeg_is_baseline_420_without_restart_markers_at_every_quality() {
        let rgba: Vec<u8> = (0..368 * 368)
            .flat_map(|i| [(i % 256) as u8, ((i / 368) % 256) as u8, 80, 255])
            .collect();
        for (size, quality) in [360, 368]
            .into_iter()
            .flat_map(|size| [34, 82, 88, 90, 92, 100].map(|q| (size, q)))
        {
            let jpeg = encode_rgba(
                &rgba[..usize::from(size) * usize::from(size) * 4],
                size,
                size,
                quality,
            )
            .unwrap();
            assert_eq!(&jpeg[..2], &[0xff, 0xd8]);
            assert_eq!(&jpeg[jpeg.len() - 2..], &[0xff, 0xd9]);
            let mut pos = 2;
            let mut found_frame = false;
            while pos + 4 < jpeg.len() {
                assert_eq!(jpeg[pos], 0xff);
                let marker = jpeg[pos + 1];
                assert_ne!(marker, 0xdd, "JPEG must not contain a restart interval");
                assert_ne!(marker, 0xc2, "JPEG must not be progressive");
                let len = u16::from_be_bytes([jpeg[pos + 2], jpeg[pos + 3]]) as usize;
                if marker == 0xc0 {
                    let frame = &jpeg[pos + 4..pos + 2 + len];
                    assert_eq!(frame[0], 8);
                    assert_eq!(u16::from_be_bytes([frame[1], frame[2]]), size);
                    assert_eq!(u16::from_be_bytes([frame[3], frame[4]]), size);
                    assert_eq!(frame[5], 3);
                    assert_eq!([frame[7], frame[10], frame[13]], [0x22, 0x11, 0x11]);
                    found_frame = true;
                }
                if marker == 0xda {
                    break;
                }
                pos += len + 2;
            }
            assert!(found_frame);
            assert!(!jpeg
                .windows(2)
                .any(|b| b[0] == 0xff && (0xd0..=0xd7).contains(&b[1])));
        }
    }

    #[test]
    fn rejects_invalid_buffers_dimensions_and_quality() {
        for (w, h, q) in [
            (0, 1, 88),
            (1025, 1, 88),
            (1, 1025, 88),
            (1, 1, 0),
            (1, 1, 101),
        ] {
            assert!(encode_rgba(&[0; 4], w, h, q).is_err());
        }
        assert!(encode_rgba(&[0; 3], 1, 1, 88).is_err());
        assert!(encode_rgba(&[0; 8], 1, 1, 88).is_err());
    }
}
