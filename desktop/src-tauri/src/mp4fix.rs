//! Turns a finished fragmented MP4 (what the recorders write, so a crash never costs the file) into
//! a regular MP4 with a full sample index at the front. Standard players (Windows «Films & TV»,
//! Media Player) cannot seek in fragmented files without an index; this makes them seekable.

use crate::record::{full_box, mp4_box, put_matrix};
use std::{
    fs::{self, File},
    io::{BufReader, BufWriter, Read, Seek, SeekFrom, Write},
    path::Path,
};

struct Sample {
    offset: u64,
    size: u32,
    duration: u32,
    sync: bool,
    composition_offset: i32,
}

struct Track {
    id: u32,
    timescale: u32,
    width: u32,
    height: u32,
    stsd: Vec<u8>,
    default_duration: u32,
    default_size: u32,
    default_flags: u32,
}

fn be32(bytes: &[u8], at: usize) -> Option<u32> {
    bytes.get(at..at + 4).map(|slice| u32::from_be_bytes(slice.try_into().unwrap()))
}

fn be64(bytes: &[u8], at: usize) -> Option<u64> {
    bytes.get(at..at + 8).map(|slice| u64::from_be_bytes(slice.try_into().unwrap()))
}

/// Child boxes of a container body: (type, body) pairs.
fn children(body: &[u8]) -> Vec<([u8; 4], &[u8])> {
    let mut boxes = Vec::new();
    let mut at = 0;
    while at + 8 <= body.len() {
        let size = be32(body, at).unwrap_or(0) as usize;
        let kind: [u8; 4] = body[at + 4..at + 8].try_into().unwrap();
        let (header, size) = match size {
            1 => (16, be64(body, at + 8).unwrap_or(0) as usize),
            0 => (8, body.len() - at),
            size => (8, size),
        };
        if size < header || at + size > body.len() {
            break;
        }
        boxes.push((kind, &body[at + header..at + size]));
        at += size;
    }
    boxes
}

fn child<'a>(body: &'a [u8], kind: &[u8; 4]) -> Option<&'a [u8]> {
    children(body).into_iter().find(|(found, _)| found == kind).map(|(_, body)| body)
}

fn video_track(moov: &[u8]) -> Option<Track> {
    for (kind, trak) in children(moov) {
        if &kind != b"trak" {
            continue;
        }
        let mdia = child(trak, b"mdia")?;
        let handler = child(mdia, b"hdlr")?;
        if handler.get(8..12) != Some(b"vide") {
            continue;
        }
        let tkhd = child(trak, b"tkhd")?;
        let v1 = tkhd[0] == 1;
        let id = be32(tkhd, if v1 { 20 } else { 12 })?;
        let width = be32(tkhd, tkhd.len() - 8)? >> 16;
        let height = be32(tkhd, tkhd.len() - 4)? >> 16;
        let mdhd = child(mdia, b"mdhd")?;
        let timescale = be32(mdhd, if mdhd[0] == 1 { 20 } else { 12 })?;
        let stbl = child(child(mdia, b"minf")?, b"stbl")?;
        let stsd_body = child(stbl, b"stsd")?;
        // Keep the whole stsd box (with header) so codec configuration is copied untouched.
        let mut stsd = Vec::with_capacity(stsd_body.len() + 8);
        stsd.extend_from_slice(&((stsd_body.len() + 8) as u32).to_be_bytes());
        stsd.extend_from_slice(b"stsd");
        stsd.extend_from_slice(stsd_body);
        let mut track = Track { id, timescale, width, height, stsd, default_duration: 0, default_size: 0, default_flags: 0 };
        if let Some(mvex) = child(moov, b"mvex") {
            for (kind, trex) in children(mvex) {
                if &kind == b"trex" && be32(trex, 4) == Some(id) {
                    track.default_duration = be32(trex, 12).unwrap_or(0);
                    track.default_size = be32(trex, 16).unwrap_or(0);
                    track.default_flags = be32(trex, 20).unwrap_or(0);
                }
            }
        }
        return Some(track);
    }
    None
}

const NON_SYNC: u32 = 0x0001_0000;

/// Reads the samples of one `moof`; `moof_offset` is its position in the file.
fn fragment_samples(track: &Track, moof: &[u8], moof_offset: u64, samples: &mut Vec<Sample>, decode_times: &mut Vec<(usize, u64)>) {
    for (kind, traf) in children(moof) {
        if &kind != b"traf" {
            continue;
        }
        let Some(tfhd) = child(traf, b"tfhd") else { continue };
        let flags = be32(tfhd, 0).unwrap_or(0) & 0x00ff_ffff;
        if be32(tfhd, 4) != Some(track.id) {
            continue;
        }
        let mut at = 8;
        let mut base = moof_offset;
        let mut default_duration = track.default_duration;
        let mut default_size = track.default_size;
        let mut default_flags = track.default_flags;
        if flags & 0x01 != 0 {
            base = be64(tfhd, at).unwrap_or(moof_offset);
            at += 8;
        }
        if flags & 0x02 != 0 {
            at += 4;
        }
        if flags & 0x08 != 0 {
            default_duration = be32(tfhd, at).unwrap_or(default_duration);
            at += 4;
        }
        if flags & 0x10 != 0 {
            default_size = be32(tfhd, at).unwrap_or(default_size);
            at += 4;
        }
        if flags & 0x20 != 0 {
            default_flags = be32(tfhd, at).unwrap_or(default_flags);
        }
        if let Some(tfdt) = child(traf, b"tfdt") {
            let time = if tfdt[0] == 1 { be64(tfdt, 4) } else { be32(tfdt, 4).map(u64::from) };
            if let Some(time) = time {
                decode_times.push((samples.len(), time));
            }
        }
        let mut cursor = base;
        for (kind, trun) in children(traf) {
            if &kind != b"trun" {
                continue;
            }
            let version = trun[0];
            let flags = be32(trun, 0).unwrap_or(0) & 0x00ff_ffff;
            let count = be32(trun, 4).unwrap_or(0) as usize;
            let mut at = 8;
            if flags & 0x01 != 0 {
                let offset = be32(trun, at).unwrap_or(0) as i32;
                cursor = base.wrapping_add_signed(i64::from(offset));
                at += 4;
            }
            let mut first_flags = None;
            if flags & 0x04 != 0 {
                first_flags = be32(trun, at);
                at += 4;
            }
            for index in 0..count {
                let mut read = |present: bool| -> Option<u32> {
                    if !present {
                        return None;
                    }
                    let value = be32(trun, at);
                    at += 4;
                    value
                };
                let duration = read(flags & 0x100 != 0).unwrap_or(default_duration);
                let size = read(flags & 0x200 != 0).unwrap_or(default_size);
                let sample_flags = read(flags & 0x400 != 0).or(if index == 0 { first_flags } else { None }).unwrap_or(default_flags);
                let cts = read(flags & 0x800 != 0).map_or(0, |raw| if version == 0 { raw as i32 } else { raw as i32 });
                samples.push(Sample { offset: cursor, size, duration, sync: sample_flags & NON_SYNC == 0, composition_offset: cts });
                cursor += u64::from(size);
            }
        }
    }
}

fn build_moov(track: &Track, samples: &[Sample], chunk_offsets: &[u64]) -> Vec<u8> {
    let media_duration: u64 = samples.iter().map(|sample| u64::from(sample.duration)).sum();
    let movie_duration = media_duration * 1000 / u64::from(track.timescale.max(1));
    let mut out = Vec::new();
    mp4_box(&mut out, b"moov", |out| {
        full_box(out, b"mvhd", 1, 0, |out| {
            out.extend_from_slice(&[0; 16]);
            out.extend_from_slice(&1000_u32.to_be_bytes());
            out.extend_from_slice(&movie_duration.to_be_bytes());
            out.extend_from_slice(&0x0001_0000_u32.to_be_bytes());
            out.extend_from_slice(&0x0100_u16.to_be_bytes());
            out.extend_from_slice(&[0; 10]);
            put_matrix(out);
            out.extend_from_slice(&[0; 24]);
            out.extend_from_slice(&2_u32.to_be_bytes());
        });
        mp4_box(out, b"trak", |out| {
            full_box(out, b"tkhd", 1, 3, |out| {
                out.extend_from_slice(&[0; 16]);
                out.extend_from_slice(&1_u32.to_be_bytes());
                out.extend_from_slice(&[0; 4]);
                out.extend_from_slice(&movie_duration.to_be_bytes());
                out.extend_from_slice(&[0; 16]);
                put_matrix(out);
                out.extend_from_slice(&(track.width << 16).to_be_bytes());
                out.extend_from_slice(&(track.height << 16).to_be_bytes());
            });
            mp4_box(out, b"mdia", |out| {
                full_box(out, b"mdhd", 1, 0, |out| {
                    out.extend_from_slice(&[0; 16]);
                    out.extend_from_slice(&track.timescale.to_be_bytes());
                    out.extend_from_slice(&media_duration.to_be_bytes());
                    out.extend_from_slice(&0x55c4_u16.to_be_bytes());
                    out.extend_from_slice(&[0; 2]);
                });
                full_box(out, b"hdlr", 0, 0, |out| {
                    out.extend_from_slice(&[0; 4]);
                    out.extend_from_slice(b"vide");
                    out.extend_from_slice(&[0; 12]);
                    out.extend_from_slice(b"MKIS100TEST video\0");
                });
                mp4_box(out, b"minf", |out| {
                    full_box(out, b"vmhd", 0, 1, |out| out.extend_from_slice(&[0; 8]));
                    mp4_box(out, b"dinf", |out| {
                        full_box(out, b"dref", 0, 0, |out| {
                            out.extend_from_slice(&1_u32.to_be_bytes());
                            full_box(out, b"url ", 0, 1, |_| {});
                        });
                    });
                    mp4_box(out, b"stbl", |out| {
                        out.extend_from_slice(&track.stsd);
                        // Durations, run-length encoded.
                        let mut runs: Vec<(u32, u32)> = Vec::new();
                        for sample in samples {
                            match runs.last_mut() {
                                Some((count, duration)) if *duration == sample.duration => *count += 1,
                                _ => runs.push((1, sample.duration)),
                            }
                        }
                        full_box(out, b"stts", 0, 0, |out| {
                            out.extend_from_slice(&(runs.len() as u32).to_be_bytes());
                            for (count, duration) in &runs {
                                out.extend_from_slice(&count.to_be_bytes());
                                out.extend_from_slice(&duration.to_be_bytes());
                            }
                        });
                        if samples.iter().any(|sample| sample.composition_offset != 0) {
                            full_box(out, b"ctts", 1, 0, |out| {
                                out.extend_from_slice(&(samples.len() as u32).to_be_bytes());
                                for sample in samples {
                                    out.extend_from_slice(&1_u32.to_be_bytes());
                                    out.extend_from_slice(&sample.composition_offset.to_be_bytes());
                                }
                            });
                        }
                        if samples.iter().any(|sample| !sample.sync) {
                            let sync: Vec<u32> = samples.iter().enumerate().filter(|(_, sample)| sample.sync).map(|(index, _)| index as u32 + 1).collect();
                            full_box(out, b"stss", 0, 0, |out| {
                                out.extend_from_slice(&(sync.len() as u32).to_be_bytes());
                                for number in sync {
                                    out.extend_from_slice(&number.to_be_bytes());
                                }
                            });
                        }
                        // One sample per chunk keeps the tables simple and exact.
                        full_box(out, b"stsc", 0, 0, |out| {
                            out.extend_from_slice(&1_u32.to_be_bytes());
                            out.extend_from_slice(&1_u32.to_be_bytes());
                            out.extend_from_slice(&1_u32.to_be_bytes());
                            out.extend_from_slice(&1_u32.to_be_bytes());
                        });
                        full_box(out, b"stsz", 0, 0, |out| {
                            out.extend_from_slice(&0_u32.to_be_bytes());
                            out.extend_from_slice(&(samples.len() as u32).to_be_bytes());
                            for sample in samples {
                                out.extend_from_slice(&sample.size.to_be_bytes());
                            }
                        });
                        full_box(out, b"co64", 0, 0, |out| {
                            out.extend_from_slice(&(chunk_offsets.len() as u32).to_be_bytes());
                            for offset in chunk_offsets {
                                out.extend_from_slice(&offset.to_be_bytes());
                            }
                        });
                    });
                });
            });
        });
    });
    out
}

/// Rewrites `path` in place as a regular, seekable MP4. A file without fragments is left as is.
pub fn defragment(path: &Path) -> Result<(), String> {
    let error = |message: String| format!("{}: {message}", path.display());
    let mut reader = BufReader::new(File::open(path).map_err(|e| error(e.to_string()))?);
    let length = reader.get_ref().metadata().map_err(|e| error(e.to_string()))?.len();

    let mut moov: Option<Vec<u8>> = None;
    let mut fragments: Vec<(u64, Vec<u8>)> = Vec::new();
    let mut position = 0_u64;
    while position + 8 <= length {
        reader.seek(SeekFrom::Start(position)).map_err(|e| error(e.to_string()))?;
        let mut header = [0_u8; 16];
        reader.read_exact(&mut header[..8]).map_err(|e| error(e.to_string()))?;
        let mut size = u64::from(u32::from_be_bytes(header[..4].try_into().unwrap()));
        let kind: [u8; 4] = header[4..8].try_into().unwrap();
        let mut header_len = 8;
        if size == 1 {
            reader.read_exact(&mut header[8..16]).map_err(|e| error(e.to_string()))?;
            size = u64::from_be_bytes(header[8..16].try_into().unwrap());
            header_len = 16;
        } else if size == 0 {
            size = length - position;
        }
        // A box cut off by a crash ends the usable part of the file.
        if size < header_len || position + size > length {
            break;
        }
        if &kind == b"moov" || &kind == b"moof" {
            let mut body = vec![0_u8; (size - header_len) as usize];
            reader.read_exact(&mut body).map_err(|e| error(e.to_string()))?;
            if &kind == b"moov" {
                moov = Some(body);
            } else {
                fragments.push((position, body));
            }
        }
        position += size;
    }
    if fragments.is_empty() {
        return Ok(());
    }
    let moov = moov.ok_or_else(|| error("нет moov".into()))?;
    let track = video_track(&moov).ok_or_else(|| error("нет видеодорожки".into()))?;

    let mut samples = Vec::new();
    let mut decode_times = Vec::new();
    for (offset, body) in &fragments {
        fragment_samples(&track, body, *offset, &mut samples, &mut decode_times);
    }
    // Fragment start times are authoritative: the sample before a fragment lasts until it starts,
    // so gaps (dropped frames, encoder pauses) keep the recording in real time.
    let starts: std::collections::HashMap<usize, u64> = decode_times.into_iter().collect();
    let mut decode_time = 0_u64;
    let mut previous: Option<u64> = None;
    for index in 0..samples.len() {
        if let Some(&start) = starts.get(&index) {
            if let Some(previous_time) = previous.filter(|&time| start > time) {
                samples[index - 1].duration = u32::try_from(start - previous_time).unwrap_or(samples[index - 1].duration);
            }
            decode_time = start;
        }
        if samples[index].duration == 0 {
            samples[index].duration = (track.timescale / 25).max(1);
        }
        previous = Some(decode_time);
        decode_time += u64::from(samples[index].duration);
    }
    // Only samples whose data really is in the file (the last fragment may be cut off).
    samples.retain(|sample| sample.size > 0 && sample.offset + u64::from(sample.size) <= length);
    if samples.is_empty() {
        return Ok(());
    }

    let mut ftyp = Vec::new();
    mp4_box(&mut ftyp, b"ftyp", |out| {
        out.extend_from_slice(b"isom");
        out.extend_from_slice(&0x200_u32.to_be_bytes());
        for brand in [b"isom", b"iso2", b"avc1", b"mp41"] {
            out.extend_from_slice(brand);
        }
    });
    let payload: u64 = samples.iter().map(|sample| u64::from(sample.size)).sum();
    // The moov size does not depend on the offset values, so measure it with zeros first.
    let moov_len = build_moov(&track, &samples, &vec![0; samples.len()]).len() as u64;
    let data_start = ftyp.len() as u64 + moov_len + 16;
    let mut offsets = Vec::with_capacity(samples.len());
    let mut cursor = data_start;
    for sample in &samples {
        offsets.push(cursor);
        cursor += u64::from(sample.size);
    }
    let moov_final = build_moov(&track, &samples, &offsets);

    let temporary = path.with_extension("mp4.part");
    let result = (|| -> std::io::Result<()> {
        let mut writer = BufWriter::with_capacity(1 << 20, File::create(&temporary)?);
        writer.write_all(&ftyp)?;
        writer.write_all(&moov_final)?;
        writer.write_all(&1_u32.to_be_bytes())?;
        writer.write_all(b"mdat")?;
        writer.write_all(&(payload + 16).to_be_bytes())?;
        let mut buffer = Vec::new();
        for sample in &samples {
            buffer.resize(sample.size as usize, 0);
            reader.seek(SeekFrom::Start(sample.offset))?;
            reader.read_exact(&mut buffer)?;
            writer.write_all(&buffer)?;
        }
        let file = writer.into_inner().map_err(|error| error.into_error())?;
        file.sync_all()
    })();
    drop(reader);
    if let Err(problem) = result {
        let _ = fs::remove_file(&temporary);
        return Err(error(problem.to_string()));
    }
    fs::rename(&temporary, path).map_err(|e| {
        let _ = fs::remove_file(&temporary);
        error(format!("не заменён (файл открыт?): {e}"))
    })
}

/// Runs [`defragment`] in the background; failures leave the fragmented file, which VLC still plays.
pub fn defragment_later(path: std::path::PathBuf) {
    std::thread::spawn(move || match defragment(&path) {
        Ok(()) => eprintln!("[record] {}: индекс для перемотки записан", path.display()),
        Err(error) => eprintln!("[record] индекс не записан, файл остаётся фрагментированным: {error}"),
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::record::{fragment, init_segment, Sample as Frame};

    #[test]
    fn fragmented_recording_becomes_seekable() {
        let path = std::env::temp_dir().join(format!("mkis-defrag-{}.mp4", std::process::id()));
        let entry = [0, 0, 0, 8, b'a', b'v', b'c', b'1'];
        let mut file = init_segment(&entry, 640, 512, 90_000);
        let frames = |start: i64, key: bool, byte: u8| Frame { timestamp: start, key, data: vec![byte; 5] };
        file.extend(fragment(1, 0, &[frames(0, true, 1), frames(3600, false, 2)], 7200));
        file.extend(fragment(2, 7200, &[frames(7200, true, 3), frames(10_800, false, 4)], 14_400));
        fs::write(&path, &file).unwrap();

        defragment(&path).unwrap();
        let bytes = fs::read(&path).unwrap();
        let top: Vec<[u8; 4]> = children(&bytes).into_iter().map(|(kind, _)| kind).collect();
        assert_eq!(top, [*b"ftyp", *b"moov", *b"mdat"]);
        let moov = child(&bytes, b"moov").unwrap();
        let stbl = child(child(child(child(moov, b"trak").unwrap(), b"mdia").unwrap(), b"minf").unwrap(), b"stbl").unwrap();
        // Two sync samples out of four: frames 1 and 3.
        let stss = child(stbl, b"stss").unwrap();
        assert_eq!((be32(stss, 4), be32(stss, 8), be32(stss, 12)), (Some(2), Some(1), Some(3)));
        // Offsets point at the right bytes in mdat.
        let co64 = child(stbl, b"co64").unwrap();
        for (index, expected) in [1_u8, 2, 3, 4].into_iter().enumerate() {
            let offset = be64(co64, 8 + index * 8).unwrap() as usize;
            assert_eq!(&bytes[offset..offset + 5], &[expected; 5]);
        }
        // Duration: 4 frames × 3600 at 90 kHz = 160 ms.
        let mvhd = child(moov, b"mvhd").unwrap();
        assert_eq!(be64(mvhd, 24), Some(160));
        fs::remove_file(&path).unwrap();
    }
}

#[cfg(test)]
mod real_file {
    /// Manual check on a real recording: `MKIS_DEFRAG=<copy.mp4> cargo test real_file -- --ignored`.
    #[test]
    #[ignore]
    fn defragment_real_recording() {
        let path = std::path::PathBuf::from(std::env::var("MKIS_DEFRAG").expect("MKIS_DEFRAG"));
        super::defragment(&path).unwrap();
    }
}
