# retina 0.4.20 — local patch

Copy of [retina](https://github.com/scottlamb/retina) 0.4.20 (MIT OR Apache-2.0) from crates.io, used through
`[patch.crates-io]` in `../../Cargo.toml`. Benchmarks and the published `Cargo.lock` were removed; the
source is otherwise unchanged except for one fix.

## The fix

`src/codec/h26x.rs`, Annex B scanner: upstream returns `invalid sequence 00 00 00 xx` when a NAL body
contains three zero bytes followed by anything other than `00`/`01`, and the whole RTSP session fails.
Emulation prevention makes that sequence impossible inside a real NAL, so the bytes that follow are
not picture data. The patch drops the rest of that NAL (`Mid::discarding`) and keeps the session.

Seen on a Beward B102S video server (thermal CAM 02): the last FU-A fragment of some IDR frames ends
in a zero run with a few stray bytes inside (`… 00 00 00 83 6b 01 00 00 …`), about 3 key frames in 30
over a minute of video. Without the patch the stream reconnected every few seconds.

To update retina: replace this directory with the new release and re-apply the change (search for
`MKIS100TEST patch`), or drop the patch once upstream tolerates the sequence.
