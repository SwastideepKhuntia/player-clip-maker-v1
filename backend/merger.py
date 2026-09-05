"""
Highlight Composer — Merges individual clips into a single highlight video
with fade-in/fade-out transitions between clips.
"""

import subprocess
import logging
import uuid
from pathlib import Path
import imageio_ffmpeg

logger = logging.getLogger(__name__)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

FADE_DURATION = 0.8  # seconds for each fade transition


def merge_clips(clip_paths: list[str], output_path: str | Path, music_path: Path = None, mute_original: bool = False) -> str:
    """
    Merge a list of clip files into one final highlight video with
    cut transitions (direct cuts) between clips using FFmpeg.
    Optionally adds background music and/or mutes original audio.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Filter valid non-empty files
    valid_clips = []
    for p in clip_paths:
        pp = Path(p)
        if pp.exists() and pp.stat().st_size > 1000:
            valid_clips.append(pp)

    if not valid_clips:
        raise ValueError("No valid video clips were extracted to merge. Check match kickoff synchronization times.")

    clip_paths = [str(p) for p in valid_clips]

    initial_merge_path = output_path.parent / f"temp_initial_{uuid.uuid4().hex[:6]}_{output_path.name}"

    if len(clip_paths) == 1:
        # Single clip — just copy (cut transition / no fades)
        import shutil
        shutil.copy2(clip_paths[0], initial_merge_path)
    else:
        # Write concat file list
        concat_file = output_path.parent / f"clips_list_{uuid.uuid4().hex[:6]}.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for path in clip_paths:
                safe_path = Path(path).resolve().as_posix()
                f.write(f"file '{safe_path}'\n")

        # Concat all clips with timestamp regeneration and clean stream copy
        cmd = [
            FFMPEG,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            "-movflags", "+faststart",
            str(initial_merge_path),
        ]

        logger.info(f"Merging {len(clip_paths)} clips with cuts → {initial_merge_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.warning("Stream-copy concat failed, re-encoding...")
            cmd_reencode = [
                FFMPEG,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                "-async", "1",
                "-avoid_negative_ts", "make_zero",
                "-movflags", "+faststart",
                str(initial_merge_path),
            ]
            result2 = subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=600)
            if result2.returncode != 0:
                concat_file.unlink(missing_ok=True)
                raise RuntimeError(f"FFmpeg merge failed:\n{result2.stderr[-1000:]}")

        concat_file.unlink(missing_ok=True)

    def _safe_replace(src: Path, dst: Path):
        import time, shutil
        for attempt in range(5):
            try:
                if dst.exists():
                    try:
                        dst.unlink()
                    except Exception:
                        pass
                src.replace(dst)
                return
            except (PermissionError, OSError) as pe:
                if attempt < 4:
                    time.sleep(0.3)
                else:
                    try:
                        shutil.copy2(src, dst)
                        src.unlink(missing_ok=True)
                        return
                    except Exception:
                        raise pe

    # Now handle Audio (Music / Muting)
    if music_path or mute_original:
        try:
            _apply_audio_processing(initial_merge_path, output_path, music_path, mute_original)
            if initial_merge_path.exists():
                initial_merge_path.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Audio processing failed, falling back to original merge: {e}")
            if initial_merge_path.exists():
                _safe_replace(initial_merge_path, output_path)
    else:
        if initial_merge_path.exists():
            _safe_replace(initial_merge_path, output_path)

    logger.info(f"Highlight video saved: {output_path}")
    return str(output_path)


def _apply_audio_processing(video_path: Path, output_path: Path, music_path: Path = None, mute_original: bool = False):
    """Apply music overlay and/or mute original audio using FFmpeg."""
    if not music_path and not mute_original:
        return

    duration = _get_duration(video_path) or 10.0
    
    cmd = [FFMPEG, "-y", "-i", str(video_path)]
    
    filter_complex = ""
    
    if music_path:
        cmd.extend(["-stream_loop", "-1", "-i", str(music_path)])
        
        if mute_original:
            # Only music
            filter_complex = f"[1:a]volume=1.0,afade=t=out:st={duration-1}:d=1[outa]"
        else:
            # Mix both
            filter_complex = f"[0:a]volume=0.4[a0];[1:a]volume=0.8[a1];[a0][a1]amix=inputs=2:duration=first[mixed];[mixed]afade=t=out:st={duration-1}:d=1[outa]"
    elif mute_original:
        # Just mute (actually remove audio stream or set volume to 0)
        filter_complex = "[0:a]volume=0[outa]"

    if filter_complex:
        cmd.extend(["-filter_complex", filter_complex, "-map", "0:v", "-map", "[outa]"])
    else:
        cmd.extend(["-map", "0:v", "-map", "0:a"])

    # Encoding settings
    cmd.extend([
        "-c:v", "copy",  # Keep video stream as is
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(output_path)
    ])

    logger.info(f"Applying audio processing: music={music_path.name if music_path else 'None'}, mute={mute_original}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        # If copy fails because of bitstream issues, try re-encoding video too
        logger.warning("Audio processing with -c:v copy failed, trying full re-encode...")
        cmd_re = [FFMPEG, "-y", "-i", str(video_path)]
        if music_path: cmd_re.extend(["-stream_loop", "-1", "-i", str(music_path)])
        if filter_complex: cmd_re.extend(["-filter_complex", filter_complex, "-map", "0:v", "-map", "[outa]"])
        cmd_re.extend([
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(output_path)
        ])
        result2 = subprocess.run(cmd_re, capture_output=True, text=True, timeout=600)
        if result2.returncode != 0:
            raise RuntimeError(f"Audio processing failed: {result2.stderr[-500:]}")


def _add_fades_single(input_path: str | Path, output_path: str | Path) -> str:
    """Add fade-in at start and fade-out at end of a single clip."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    # Get clip duration first
    duration = _get_duration(input_path)
    if duration is None or duration < FADE_DURATION * 2:
        # Clip too short for fades, just copy
        import shutil
        shutil.copy2(input_path, output_path)
        return str(output_path)

    fade_out_start = max(0, duration - FADE_DURATION)

    # Apply video and audio fades
    vf = f"fade=t=in:st=0:d={FADE_DURATION},fade=t=out:st={fade_out_start:.2f}:d={FADE_DURATION}"
    af = f"afade=t=in:st=0:d={FADE_DURATION},afade=t=out:st={fade_out_start:.2f}:d={FADE_DURATION}"

    cmd = [
        FFMPEG,
        "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-g", "60",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.warning(f"Fade failed for {input_path}: {result.stderr[-300:]}")
        import shutil
        shutil.copy2(input_path, output_path)

    return str(output_path)


def _get_duration(path: Path) -> float | None:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        FFMPEG.replace("ffmpeg", "ffprobe") if "ffmpeg" in FFMPEG else FFMPEG,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    # Try ffprobe, fall back to ffmpeg-based probe
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass

    # Fallback: use ffmpeg to get duration
    try:
        cmd2 = [FFMPEG, "-i", str(path)]
        result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=10)
        # Parse duration from stderr: " Duration: 00:00:10.50,"
        import re
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result2.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass

    return None


def render_timeline_project(
    tracks_data: list[dict],
    output_path: str | Path,
    crop_mode: str = "original",
    music_path: Path = None,
    music_volume: float = 0.8,
    match_volume: float = 1.0,
    mute_original: bool = False
) -> str:
    """
    Render a complex timeline project from the Premiere Pro style editor.
    tracks_data is a list of clip objects:
      [{"source": "/path/to/clip.mp4", "start": 0.0, "end": 5.2, "crop": {...}}, ...]
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = output_path.parent / f"timeline_temp_{uuid.uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        processed_clips = []
        base_dir = Path(__file__).resolve().parent.parent
        videos_dir = base_dir / "data" / "videos"
        output_dir = base_dir / "output"

        for i, item in enumerate(tracks_data):
            src_str = item.get("source", "")
            src = Path(src_str)
            if not src.exists():
                # Check inside data/videos
                if (videos_dir / src_str).exists():
                    src = videos_dir / src_str
                elif (output_dir / src_str).exists():
                    src = output_dir / src_str
                elif (base_dir / src_str).exists():
                    src = base_dir / src_str
                else:
                    logger.warning(f"Clip source not found: {src_str}")
                    continue

            start = float(item.get("start", 0.0))
            end = float(item.get("end", 0.0))
            duration = end - start if end > start else None

            out_segment = temp_dir / f"segment_{i:04d}.mp4"

            # Build video filter for crop / aspect ratio if specified
            vf_filters = []
            if crop_mode == "9:16": # Vertical Short / Reel / TikTok
                vf_filters.append("crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920")
            elif crop_mode == "1:1": # Square
                vf_filters.append("crop=min(iw\\,ih):min(iw\\,ih):(iw-min(iw\\,ih))/2:(ih-min(iw\\,ih))/2,scale=1080:1080")
            elif crop_mode == "4:5": # Instagram Portrait
                vf_filters.append("crop=ih*4/5:ih:(iw-ih*4/5)/2:0,scale=1080:1350")
            elif crop_mode == "16:9": # Standard Widescreen
                vf_filters.append("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2")

            # Custom crop coordinates or Premiere Pro Crop with Zoom
            custom_crop = item.get("crop")
            if custom_crop and isinstance(custom_crop, dict):
                # Check for Premiere Pro style Left, Top, Right, Bottom percentage crop
                c_left = float(custom_crop.get("left", 0.0))
                c_top = float(custom_crop.get("top", 0.0))
                c_right = float(custom_crop.get("right", 0.0))
                c_bottom = float(custom_crop.get("bottom", 0.0))
                zoom_enabled = custom_crop.get("zoom", True)

                # Ensure crop percentages leave at least 5% visible area
                rem_w_pct = max(5.0, 100.0 - c_left - c_right)
                rem_h_pct = max(5.0, 100.0 - c_top - c_bottom)

                if (c_left > 0 or c_top > 0 or c_right > 0 or c_bottom > 0):
                    crop_expr = (
                        f"crop=w=iw*{rem_w_pct/100.0}:h=ih*{rem_h_pct/100.0}:"
                        f"x=iw*{c_left/100.0}:y=ih*{c_top/100.0}"
                    )
                    if zoom_enabled:
                        # Step B: Scale to fill screen (inverse scaling factor 100/Width, 100/Height)
                        crop_expr += f",scale=1920:1080:flags=lanczos"
                    vf_filters.insert(0, crop_expr)
                else:
                    cw = custom_crop.get("w")
                    ch = custom_crop.get("h")
                    cx = custom_crop.get("x", 0)
                    cy = custom_crop.get("y", 0)
                    if cw and ch:
                        vf_filters.insert(0, f"crop={cw}:{ch}:{cx}:{cy}")

            cmd = [FFMPEG, "-y"]
            if start > 0:
                cmd.extend(["-ss", str(start)])
            cmd.extend(["-i", str(src)])
            if duration and duration > 0:
                cmd.extend(["-t", str(duration)])

            if vf_filters:
                cmd.extend(["-vf", ",".join(vf_filters)])

            cmd.extend([
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                str(out_segment)
            ])

            logger.info(f"Rendering timeline segment {i}: {src.name} [{start}s -> {end}s]")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0 and out_segment.exists() and out_segment.stat().st_size > 1000:
                processed_clips.append(str(out_segment))
            else:
                logger.error(f"Failed rendering segment {i}: {res.stderr[-400:]}")

        if not processed_clips:
            raise RuntimeError("No timeline clips could be rendered.")

        # Step 2: Merge the processed segments
        concat_file = temp_dir / "timeline_concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for cp in processed_clips:
                f.write(f"file '{Path(cp).resolve().as_posix()}'\n")

        initial_merged = temp_dir / f"merged_raw.mp4"
        cmd_merge = [
            FFMPEG, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(initial_merged)
        ]
        res_merge = subprocess.run(cmd_merge, capture_output=True, text=True, timeout=300)
        if res_merge.returncode != 0 or not initial_merged.exists():
            # Re-encode merge fallback
            cmd_re = [
                FFMPEG, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "128k",
                str(initial_merged)
            ]
            subprocess.run(cmd_re, capture_output=True, text=True, timeout=400)

        # Step 3: Audio mixing (music and master volume)
        final_video = initial_merged
        if music_path or mute_original or match_volume != 1.0:
            duration = _get_duration(final_video) or 10.0
            cmd_audio = [FFMPEG, "-y", "-i", str(final_video)]
            
            if music_path and Path(music_path).exists():
                cmd_audio.extend(["-stream_loop", "-1", "-i", str(music_path)])
                if mute_original or match_volume == 0:
                    filter_complex = f"[1:a]volume={music_volume:.2f},afade=t=out:st={max(0, duration-1)}:d=1[outa]"
                else:
                    filter_complex = f"[0:a]volume={match_volume:.2f}[a0];[1:a]volume={music_volume:.2f}[a1];[a0][a1]amix=inputs=2:duration=first[mixed];[mixed]afade=t=out:st={max(0, duration-1)}:d=1[outa]"
            elif mute_original or match_volume == 0:
                filter_complex = "[0:a]volume=0[outa]"
            else:
                filter_complex = f"[0:a]volume={match_volume:.2f}[outa]"

            cmd_audio.extend([
                "-filter_complex", filter_complex,
                "-map", "0:v", "-map", "[outa]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(output_path)
            ])
            res_aud = subprocess.run(cmd_audio, capture_output=True, text=True, timeout=300)
            if res_aud.returncode != 0:
                logger.warning("Audio copy failed, trying full re-encode...")
                cmd_aud_re = [FFMPEG, "-y", "-i", str(final_video)]
                if music_path and Path(music_path).exists():
                    cmd_aud_re.extend(["-stream_loop", "-1", "-i", str(music_path)])
                cmd_aud_re.extend([
                    "-filter_complex", filter_complex,
                    "-map", "0:v", "-map", "[outa]",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-c:a", "aac", "-b:a", "128k",
                    "-shortest",
                    str(output_path)
                ])
                subprocess.run(cmd_aud_re, capture_output=True, text=True, timeout=400)
        else:
            import shutil
            shutil.copy2(final_video, output_path)

        logger.info(f"Timeline project successfully exported to {output_path}")
        return str(output_path)

    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def _cleanup(concat_file: Path, temp_dir: Path):
    """Clean up temporary files."""
    import shutil
    try:
        concat_file.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except OSError:
        pass

