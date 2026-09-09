"""
FastAPI Backend — Serves the Web UI and provides API endpoints
for the highlight generation pipeline.
"""

import logging
import shutil
import uuid
import asyncio
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body, Header
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.parser import parse_csv, parse_df, get_players
from backend.sync import apply_offset
from backend.events import score_and_filter, add_buffers
from backend.clipper import extract_clips
from backend.merger import merge_clips
from backend.api_fetch import fetch_events_as_df

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

VIDEO_DIR = DATA_DIR / "videos"
CSV_DIR = DATA_DIR / "csv"
MUSIC_DIR = DATA_DIR / "music"
CLIPS_DIR = OUTPUT_DIR / "clips"

from fastapi.middleware.cors import CORSMiddleware

# Ensure directories exist
for d in [VIDEO_DIR, CSV_DIR, MUSIC_DIR, OUTPUT_DIR, CLIPS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Player Clip Maker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# State (in-memory for MVP)
# ---------------------------------------------------------------------------
job_status: dict = {
    "state": "idle",        # idle | processing | done | error
    "progress": 0,
    "total": 0,
    "message": "",
    "output_file": None,
}


def _reset_status():
    job_status.update(state="idle", progress=0, total=0, message="", output_file=None)
    job_status.pop("clips_preview", None)

def _cleanup_old_sessions():
    """Attempt to delete old clip subdirectories and preview files. Gracefully skip if locked."""
    try:
        # Keep things tidy — try to delete any session folders in clips/
        for session_folder in CLIPS_DIR.iterdir():
            if session_folder.is_dir() and (session_folder.name.startswith("run_") or session_folder.name.startswith("custom_")):
                try:
                    shutil.rmtree(session_folder, ignore_errors=True)
                except Exception:
                    pass
        # Clean old preview files from output/
        for f in OUTPUT_DIR.iterdir():
            if f.is_file() and f.name.startswith("preview_") and f.name.endswith(".mp4"):
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Cleanup warning: {e}")


# ---------------------------------------------------------------------------
# API — File Upload
# ---------------------------------------------------------------------------
@app.get("/api/browse_folder")
async def browse_folder():
    """Open a native OS folder picker and return the selected path."""
    def _open_picker():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder_selected = filedialog.askdirectory()
        root.destroy()
        return folder_selected

    selected_path = await asyncio.to_thread(_open_picker)
    if not selected_path:
        return {"status": "cancelled", "path": ""}
    return {"status": "ok", "path": selected_path}

@app.post("/api/upload")
async def upload_files(
    video: Optional[UploadFile] = File(None),
    video_1h: Optional[UploadFile] = File(None),
    video_2h: Optional[UploadFile] = File(None),
    video_et1: Optional[UploadFile] = File(None),
    video_et2: Optional[UploadFile] = File(None),
    csv: Optional[UploadFile] = File(None),
):
    """Upload match video(s) (per half or full match) and/or CSV file."""
    results = {}

    uploads = [
        ("video", video),
        ("video_1h", video_1h),
        ("video_2h", video_2h),
        ("video_et1", video_et1),
        ("video_et2", video_et2),
    ]

    for key, f_obj in uploads:
        if f_obj and f_obj.filename:
            dest = VIDEO_DIR / f_obj.filename
            with open(dest, "wb") as f:
                shutil.copyfileobj(f_obj.file, f)
            results[key] = f_obj.filename
            logger.info(f"Uploaded {key}: {f_obj.filename}")

    if csv and csv.filename:
        dest = CSV_DIR / csv.filename
        with open(dest, "wb") as f:
            shutil.copyfileobj(csv.file, f)
        results["csv"] = csv.filename
        logger.info(f"Uploaded CSV: {csv.filename}")

    if not results:
        raise HTTPException(400, "No files uploaded")

    # If generic 'video' is uploaded, also set as default
    if "video" in results and "video_1h" not in results:
        results["video_default"] = results["video"]

    return {"status": "ok", **results}


# ---------------------------------------------------------------------------
# API — List uploaded files
# ---------------------------------------------------------------------------
@app.get("/api/files")
async def list_files():
    """List available videos and CSV files."""
    videos = sorted([f.name for f in VIDEO_DIR.iterdir() if f.is_file()])
    csvs = sorted([f.name for f in CSV_DIR.iterdir() if f.is_file()])
    return {"videos": videos, "csvs": csvs}


# ---------------------------------------------------------------------------
# API — List available music (Nudged)
# ---------------------------------------------------------------------------
@app.get("/api/music")
async def list_music():
    """List available background music files."""
    music_files = sorted([f.name for f in MUSIC_DIR.iterdir() if f.is_file() and f.suffix.lower() in [".mp3", ".wav", ".aac", ".m4a"]])
    return {"music": music_files}


# ---------------------------------------------------------------------------
# API — Scrape WhoScored Match Data
# ---------------------------------------------------------------------------
@app.post("/api/scrape_whoscored")
async def scrape_whoscored(url_or_id: str = Form(...)):
    """Scrape match events directly from WhoScored and generate a pipeline-ready CSV."""
    from backend.whoscored_scraper import scrape_whoscored_match

    try:
        df, filename = await asyncio.to_thread(scrape_whoscored_match, url_or_id)
        players = df["player"].dropna().unique().tolist()
        players = sorted([str(p).strip() for p in players if str(p).strip()], key=str.lower)

        teams = []
        team_players = {}
        if "team" in df.columns:
            teams = df["team"].dropna().unique().tolist()
            teams = sorted([str(t).strip() for t in teams if str(t).strip()], key=str.lower)
            if "player" in df.columns:
                for t in teams:
                    t_df = df[df["team"].astype(str).str.strip().str.lower() == str(t).strip().lower()]
                    p_list = t_df["player"].dropna().unique().tolist()
                    team_players[t] = sorted([str(p).strip() for p in p_list if str(p).strip()], key=str.lower)

        return {
            "status": "ok",
            "csv_filename": filename,
            "total_events": len(df),
            "players": players,
            "teams": teams,
            "team_players": team_players,
            "message": f"Successfully scraped {len(df)} events from WhoScored!"
        }
    except Exception as e:
        logger.exception("WhoScored scraping failed")
        raise HTTPException(400, f"WhoScored Scraping Error: {str(e)}")


# ---------------------------------------------------------------------------
# API — Scrape Scoresway Match Data
# ---------------------------------------------------------------------------
@app.post("/api/scrape_scoresway")
async def scrape_scoresway(url_or_id: str = Form(...)):
    """Scrape match events from Scoresway (PerformFeeds) and generate a pipeline-ready CSV."""
    from backend.scoresway_scraper import scrape_scoresway_match

    try:
        df, filename = await asyncio.to_thread(scrape_scoresway_match, url_or_id)
        players = df["player"].dropna().unique().tolist()
        players = sorted([str(p).strip() for p in players if str(p).strip()], key=str.lower)

        teams = []
        team_players = {}
        if "team" in df.columns:
            teams = df["team"].dropna().unique().tolist()
            teams = sorted([str(t).strip() for t in teams if str(t).strip()], key=str.lower)
            if "player" in df.columns:
                for t in teams:
                    t_df = df[df["team"].astype(str).str.strip().str.lower() == str(t).strip().lower()]
                    p_list = t_df["player"].dropna().unique().tolist()
                    team_players[t] = sorted([str(p).strip() for p in p_list if str(p).strip()], key=str.lower)

        return {
            "status": "ok",
            "csv_filename": filename,
            "total_events": len(df),
            "players": players,
            "teams": teams,
            "team_players": team_players,
            "message": f"Successfully scraped {len(df)} events from Scoresway!"
        }
    except Exception as e:
        logger.exception("Scoresway scraping failed")
        raise HTTPException(400, f"Scoresway Scraping Error: {str(e)}")


# ---------------------------------------------------------------------------
# API — Get players from CSV
# ---------------------------------------------------------------------------
@app.post("/api/players")
async def get_player_list(csv_filename: str = Form(""), match_id: str = Form("")):
    """Parse a CSV or Fetch API data and return unique player names."""
    
    if match_id:
        try:
            logger.info(f"Loading live players from API Match ID: {match_id}")
            df = await asyncio.to_thread(fetch_events_as_df, match_id)
            players = df["player"].dropna().unique().tolist()
            players = [str(p).strip() for p in players if str(p).strip()]
            
            teams = []
            if "team" in df.columns:
                teams = df["team"].dropna().unique().tolist()
                teams = [str(t).strip() for t in teams if str(t).strip()]

            return {
                "players": sorted(players, key=str.lower), 
                "teams": sorted(teams, key=str.lower),
                "single_player": False, 
                "fallback_name": f"Match {match_id}"
            }
        except Exception as e:
            logger.exception(f"Failed to fetch live API players for Match {match_id}")
            raise HTTPException(400, str(e))
            
    if not csv_filename:
        raise HTTPException(400, "Must provide either csv_filename or match_id")

    csv_path = CSV_DIR / csv_filename
    if not csv_path.exists():
        logger.error(f"CSV file not found at: {csv_path}")
        raise HTTPException(404, f"CSV file not found: {csv_filename}")

    try:
        logger.info(f"Loading players and teams from: {csv_path}")
        players, teams, single_player, fallback_name, team_players = get_players(csv_path)
        logger.info(f"Found {len(players)} players and {len(teams)} teams (single_player={single_player})")
    except Exception as e:
        logger.exception(f"Failed to parse CSV: {csv_path}")
        raise HTTPException(400, str(e))

    return {
        "players": players, 
        "teams": teams,
        "team_players": team_players,
        "single_player": single_player, 
        "fallback_name": fallback_name
    }


# ---------------------------------------------------------------------------
# API — Generate highlights (pipeline)
# ---------------------------------------------------------------------------
@app.post("/api/generate")
async def generate_highlights(
    video_filename: str = Form(""),
    video_1h_filename: str = Form(""),
    video_2h_filename: str = Form(""),
    video_et1_filename: str = Form(""),
    video_et2_filename: str = Form(""),
    csv_filename: str = Form(""),
    match_id: str = Form(""),
    player_name: str = Form(""),
    team_name: str = Form(""),
    halves_include: str = Form("both"),
    fh_kickoff: float = Form(0.0),
    sh_kickoff: float = Form(0.0),
    et1_kickoff: float = Form(0.0),
    et2_kickoff: float = Form(0.0),
    action_types: str = Form("all"),
    min_score: int = Form(1),
    min_xt: float = Form(0.0),
    top_x: int = Form(0),
    pre_buffer: float = Form(6.0),
    post_buffer: float = Form(4.0),
    merge_gap: float = Form(6.0),
    save_individual: bool = Form(False),
    dry_run: bool = Form(False),
    output_filename: str = Form("Highlights.mp4"),
    output_folder: str = Form(""),
    music_file: str = Form(""),
    mute_original: bool = Form(False)
):
    """Start the video generation pipeline with single or multi-half video support."""
    if job_status["state"] == "processing":
        raise HTTPException(409, "A job is already running")

    # Map available video source paths
    video_sources = {}
    if video_1h_filename:
        p = VIDEO_DIR / video_1h_filename
        if p.exists(): video_sources["first"] = p
    if video_2h_filename:
        p = VIDEO_DIR / video_2h_filename
        if p.exists(): video_sources["second"] = p
    if video_et1_filename:
        p = VIDEO_DIR / video_et1_filename
        if p.exists(): video_sources["et1"] = p
    if video_et2_filename:
        p = VIDEO_DIR / video_et2_filename
        if p.exists(): video_sources["et2"] = p

    primary_name = video_filename or video_1h_filename or video_2h_filename
    if not primary_name:
        raise HTTPException(400, "Please upload or select at least one match video.")

    primary_video_path = VIDEO_DIR / primary_name
    if not primary_video_path.exists():
        raise HTTPException(404, f"Video not found: {primary_name}")

    video_sources["default"] = primary_video_path
    if "first" not in video_sources and primary_video_path.exists():
        video_sources["first"] = primary_video_path

    # Fallback to None if neither provided
    csv_path = CSV_DIR / csv_filename if csv_filename else None

    # Run in background
    asyncio.create_task(
        _run_pipeline(
            primary_video_path, video_sources, csv_path, match_id, player_name, team_name,
            halves_include, fh_kickoff, sh_kickoff, et1_kickoff, et2_kickoff,
            action_types, min_score, min_xt, top_x,
            pre_buffer, post_buffer, merge_gap,
            save_individual, dry_run, output_filename, output_folder,
            music_file, mute_original
        )
    )
    return {"status": "started", "message": "Pipeline is running..."}


# ---------------------------------------------------------------------------
# API — Premiere Pro Timeline Studio Export
# ---------------------------------------------------------------------------
class TimelineClipItem(BaseModel):
    source: str # filename or relative path
    start: float = 0.0
    end: float = 0.0
    crop: Optional[dict] = None

class TimelineExportRequest(BaseModel):
    clips: list[TimelineClipItem]
    crop_mode: str = "original" # original, 16:9, 9:16, 1:1, 4:5
    music_file: str = ""
    music_volume: float = 0.8
    match_volume: float = 1.0
    mute_original: bool = False
    output_filename: str = "Timeline_Edit.mp4"
    output_folder: str = ""

@app.post("/api/editor_export")
async def export_timeline_project(req: TimelineExportRequest):
    """Render and export a timeline project from the Premiere Pro style studio."""
    if job_status["state"] == "processing":
        raise HTTPException(400, "A render job is already running")

    if not req.clips:
        raise HTTPException(400, "No clips in timeline to export")

    # Resolve clip source paths (check OUTPUT_DIR, CLIPS_DIR subfolders, and VIDEO_DIR)
    resolved_clips = []
    for c in req.clips:
        c_src = c.source
        p_out = OUTPUT_DIR / c_src
        p_vid = VIDEO_DIR / c_src
        
        target_path = None
        if p_out.exists():
            target_path = p_out
        elif p_vid.exists():
            target_path = p_vid
        else:
            # Search clips dir
            found = list(CLIPS_DIR.glob(f"**/{c_src}"))
            if found:
                target_path = found[0]

        if not target_path or not target_path.exists():
            # If absolute path passed
            if Path(c_src).exists():
                target_path = Path(c_src)
            else:
                raise HTTPException(404, f"Timeline clip source not found: {c_src}")

        resolved_clips.append({
            "source": str(target_path.resolve()),
            "start": c.start,
            "end": c.end,
            "crop": c.crop
        })

    asyncio.create_task(
        _run_timeline_render(
            resolved_clips, req.crop_mode, req.music_file,
            req.music_volume, req.match_volume, req.mute_original,
            req.output_filename, req.output_folder
        )
    )

    return {"status": "started", "message": "Timeline render started..."}


async def _run_timeline_render(
    clips: list[dict],
    crop_mode: str,
    music_file: str,
    music_volume: float,
    match_volume: float,
    mute_original: bool,
    output_filename: str,
    output_folder: str
):
    """Execute timeline studio rendering in the background."""
    try:
        _reset_status()
        job_status["state"] = "processing"
        job_status["message"] = "Rendering Premiere Pro timeline project..."
        job_status["total"] = len(clips)

        effective_output_dir = Path(output_folder) if output_folder and Path(output_folder).is_dir() else OUTPUT_DIR
        effective_output_dir.mkdir(parents=True, exist_ok=True)

        if not output_filename.lower().endswith(".mp4"):
            output_filename = output_filename.rsplit('.', 1)[0] + ".mp4" if '.' in output_filename else output_filename + ".mp4"

        output_path = effective_output_dir / output_filename
        music_path = MUSIC_DIR / music_file if music_file else None

        from backend.merger import render_timeline_project
        await asyncio.to_thread(
            render_timeline_project,
            clips,
            output_path,
            crop_mode,
            music_path,
            music_volume,
            match_volume,
            mute_original
        )

        job_status.update(
            state="done",
            progress=len(clips),
            message="Timeline export complete! Video ready to download.",
            output_file=output_filename,
            actual_path=str(output_path.resolve())
        )

        if output_path.resolve() != (OUTPUT_DIR / output_filename).resolve():
            try:
                shutil.copy2(output_path, OUTPUT_DIR / output_filename)
            except Exception as e:
                logger.warning(f"Dual-save copy failed: {e}")

        logger.info(f"Timeline rendering complete: {output_path}")

    except Exception as e:
        logger.exception("Timeline rendering error")
        job_status.update(state="error", message=f"Timeline Render Error: {str(e)}")


# ---------------------------------------------------------------------------
# API — Custom Render (from Timeline Editor)
# ---------------------------------------------------------------------------
class CustomClip(BaseModel):
    clip_start: float
    clip_end: float
    source_video: Optional[str] = None

class CustomRenderRequest(BaseModel):
    video_filename: str
    player_name: str
    save_individual: bool
    output_folder: str = ""
    music_file: str = ""
    mute_original: bool = False
    clips: list[CustomClip]

@app.post("/api/render_custom")
async def render_custom(req: CustomRenderRequest):
    """Render a highlight video using manually provided timestamp boundaries."""
    if job_status["state"] == "processing":
        raise HTTPException(400, "A job is already running")

    video_path = VIDEO_DIR / req.video_filename
    if not video_path.exists():
        raise HTTPException(404, f"Video not found: {req.video_filename}")

    # Convert Pydantic clips to dicts for extract_clips (requires clip_index and optional source_video)
    clip_dicts = []
    for i, c in enumerate(req.clips):
        c_src = VIDEO_DIR / c.source_video if (c.source_video and (VIDEO_DIR / c.source_video).exists()) else video_path
        clip_dicts.append({
            "clip_index": i + 1,
            "clip_start": c.clip_start,
            "clip_end": c.clip_end,
            "source_video": c_src,
            "events": []
        })

    asyncio.create_task(
        _run_render_only(video_path, req.player_name, clip_dicts, req.save_individual, req.output_folder, req.music_file, req.mute_original)
    )

    return {"status": "started", "message": "Custom rendering started..."}


async def _run_render_only(video_path: Path, player_name: str, clips: list[dict], save_individual: bool, output_folder: str = "", music_file: str = "", mute_original: bool = False):
    """Execute only the extraction and merging steps asynchronously."""
    try:
        _reset_status()
        job_status["state"] = "processing"

        # Determine effective output directory
        effective_output_dir = Path(output_folder) if output_folder and Path(output_folder).is_dir() else OUTPUT_DIR
        effective_output_dir.mkdir(parents=True, exist_ok=True)

        # Step 5: Clean old clips (Robustly)
        _cleanup_old_sessions()
        
        # Create a unique session directory for this run
        session_id = f"custom_{uuid.uuid4().hex[:8]}"
        session_dir = CLIPS_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Step 6: Extract clips
        job_status["message"] = "Extracting edited clips..."
        job_status["total"] = len(clips)

        def on_progress(done, total):
            job_status["progress"] = done
            job_status["message"] = f"Extracting clip {done}/{total}..."

        from backend.clipper import extract_clips
        from backend.merger import merge_clips

        clip_paths = await asyncio.to_thread(
            extract_clips, video_path, clips, session_dir, on_progress
        )

        if not clip_paths:
            job_status.update(state="error", message="No clips could be extracted")
            return

        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in player_name).strip()

        # Output Mode: Save Individual ZIP vs Faded Merged Highlight
        if save_individual:
            job_status["message"] = "Zipping individual clips..."
            output_name = f"clips_edited_{safe_name}_{uuid.uuid4().hex[:6]}.zip"
            output_path = effective_output_dir / output_name

            import zipfile
            def _create_zip():
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for idx, cp in enumerate(clip_paths):
                        zipf.write(cp, arcname=f"{safe_name}_clip_{idx+1}.mp4")

            await asyncio.to_thread(_create_zip)
            finish_msg = "Individual clips ZIP ready!"
            
        else:
            job_status["message"] = "Merging extracted clips into final highlight..."
            output_name = f"highlight_edited_{safe_name}_{uuid.uuid4().hex[:6]}.mp4"
            output_path = effective_output_dir / output_name
            
            music_path = MUSIC_DIR / music_file if music_file else None
            await asyncio.to_thread(merge_clips, clip_paths, output_path, music_path, mute_original)
            finish_msg = "Highlight video ready!"

        job_status.update(
            state="done",
            progress=len(clips),
            message=finish_msg,
            output_file=output_name,
            actual_path=str(output_path.resolve())
        )

        # Dual-save: Copy to default OUTPUT_DIR for browser playback if custom folder was used
        if output_path.resolve() != (OUTPUT_DIR / output_name).resolve():
            try:
                shutil.copy2(output_path, OUTPUT_DIR / output_name)
                logger.info(f"Dual-save: Copied {output_name} to {OUTPUT_DIR}")
            except Exception as e:
                logger.warning(f"Dual-save copy failed: {e}")

        logger.info(f"Custom rendering complete: {output_path}")

    except Exception as e:
        logger.exception("Custom rendering error")
        job_status.update(state="error", message=str(e))


async def _run_pipeline(
    video_path: Path,
    video_sources: dict,
    csv_path: Optional[Path],
    match_id: str,
    player_name: str,
    team_name: str,
    halves_include: str,
    fh_kickoff: float,
    sh_kickoff: float,
    et1_kickoff: float,
    et2_kickoff: float,
    action_types: str,
    min_score: int,
    min_xt: float,
    top_x: int,
    pre_buffer: float,
    post_buffer: float,
    merge_gap: float,
    save_individual: bool,
    dry_run: bool,
    output_filename: str,
    output_folder: str = "",
    music_file: str = "",
    mute_original: bool = False,
):
    """Background task to run the complete highlighting pipeline with multi-video support."""
    try:
        _reset_status()
        job_status["state"] = "processing"
        
        # Determine effective output directory
        effective_output_dir = Path(output_folder) if output_folder and Path(output_folder).is_dir() else OUTPUT_DIR
        effective_output_dir.mkdir(parents=True, exist_ok=True)
        
        has_csv = csv_path and csv_path.exists() and not csv_path.is_dir()
        has_api = bool(match_id.strip())
        
        if not has_csv and not has_api:
            job_status.update(
                state="error", 
                message="Cannot generate clips without data! You must either upload a match CSV or enter a Match ID to auto-fetch the data."
            )
            return

        # Step 1: Parse Data (CSV or API)
        if has_csv:
            job_status["message"] = "Parsing local CSV..."
            target_label = player_name if player_name else (team_name if team_name else "Full Match")
            logger.info(f"Parsing CSV for: {target_label}")
            events = await asyncio.to_thread(parse_csv, csv_path, player_name, team_name)
        else:
            job_status["message"] = f"Fetching live API data for Match #{match_id}..."
            logger.info(f"Fetching API Data for match: {match_id}")
            df = await asyncio.to_thread(fetch_events_as_df, match_id)
            events = await asyncio.to_thread(parse_df, df, player_name, team_name)

        if not events:
            target_label = player_name if player_name else (team_name if team_name else "Match")
            job_status.update(state="error", message=f"No events found for {target_label}")
            return

        logger.info(f"Found {len(events)} raw events")

        # Step 2: Apply offset (with explicit kickoff times and multi-video source assignment)
        job_status["message"] = "Applying time synchronization..."
        events = apply_offset(
            events, halves_include, fh_kickoff, sh_kickoff,
            et1_kickoff, et2_kickoff, video_sources=video_sources
        )

        # Step 3: Score and filter
        job_status["message"] = "Calculating scores and filtering..."
        events = score_and_filter(events, action_types, min_score, min_xt, top_x)

        if not events:
            job_status.update(state="error", message="No events passed the filters. Try lowering the minimum score or xT value.")
            return

        logger.info(f"{len(events)} events after filtering")

        # Step 4: Add buffers and merge overlaps
        job_status["message"] = "Calculating clip boundaries..."
        clips = add_buffers(events, pre_sec=pre_buffer, post_sec=post_buffer, merge_gap=merge_gap)
        logger.info(f"{len(clips)} clips after overlap merging")

        # Step 4.5: DRY RUN
        if dry_run:
            logger.info("Dry run requested — returning preview timeline")
            job_status.update(
                state="done_preview",
                message="Timeline preview ready!",
                clips_preview=clips
            )
            return

        # Step 5: Clean old clips (Robustly)
        _cleanup_old_sessions()

        # Create a unique session directory for this run
        session_id = f"run_{uuid.uuid4().hex[:8]}"
        session_dir = CLIPS_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Step 6: Extract clips
        job_status["message"] = "Extracting clips from video..."
        job_status["total"] = len(clips)

        def on_progress(done, total):
            job_status["progress"] = done
            job_status["message"] = f"Extracting clip {done}/{total}..."

        clip_paths = await asyncio.to_thread(
            extract_clips, video_path, clips, session_dir, on_progress
        )

        if not clip_paths:
            job_status.update(state="error", message="No clips could be extracted")
            return

        display_label = player_name if player_name else (team_name if team_name else "Match")
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in display_label).strip()

        formatted_clips_preview = []
        running_offset = 0.0
        for i, c in enumerate(clips):
            c_start = float(c.get("clip_start", 0.0))
            c_end = float(c.get("clip_end", 0.0))
            c_dur = round(max(0.1, c_end - c_start), 2)
            c_events = c.get("events", [])
            primary_event = c_events[0].get("event", "Action") if c_events else c.get("event_summary", "Action")
            summary_text = c.get("event_summary", primary_event)
            player = c_events[0].get("player", player_name) if c_events else player_name
            event_tags = list(set([e.get("event", "Action") for e in c_events if e.get("event")]))
            if not event_tags:
                event_tags = [primary_event]

            raw_src = c.get("source_video")
            if raw_src:
                src_file_name = Path(raw_src).name
            else:
                src_file_name = video_path.name

            clip_file_name = f"clip_{i+1:04d}.mp4"
            clip_rel_url = f"/api/clips/{session_id}/{clip_file_name}"

            formatted_clips_preview.append({
                "id": f"clip_{i+1}_{int(c_start)}",
                "index": i,
                "clip_index": i + 1,
                "start_sec": round(c_start, 2),
                "end_sec": round(c_end, 2),
                "duration": c_dur,
                "reel_start": round(running_offset, 2),
                "reel_end": round(running_offset + c_dur, 2),
                "event": primary_event,
                "tags": event_tags,
                "summary": summary_text,
                "player": player,
                "clip_file": clip_file_name,
                "clip_url": clip_rel_url,
                "highlight_url": f"/api/download/{output_filename}",
                "source_video": src_file_name,
                "source_video_url": f"/api/videos/{src_file_name}",
                "period": c.get("period", "FirstHalf")
            })
            running_offset += c_dur

        # Output Mode: Save Individual ZIP vs Faded Merged Highlight
        if save_individual:
            job_status["message"] = "Zipping individual clips..."
            # Ensure name ends with zip
            if not output_filename.lower().endswith(".zip"):
                output_filename = output_filename.rsplit('.', 1)[0] + ".zip" if '.' in output_filename else output_filename + ".zip"
                
            output_path = effective_output_dir / output_filename

            import zipfile
            def _create_zip():
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for idx, cp in enumerate(clip_paths):
                        zipf.write(cp, arcname=f"{safe_name}_clip_{idx+1}.mp4")

            await asyncio.to_thread(_create_zip)
            
            job_status.update(
                state="done",
                progress=len(clips),
                message="ZIP Archive created successfully!",
                output_file=output_path.name,
                actual_path=str(output_path.resolve()),
                clips_preview=formatted_clips_preview,
                highlight_url=f"/api/download/{output_path.name}",
                video_filename=video_path.name,
                source_video_url=f"/api/videos/{video_path.name}"
            )
        else:
            job_status["message"] = "Merging extracted clips into final highlight..."
            # Ensure name ends with mp4
            if not output_filename.lower().endswith(".mp4"):
                output_filename = output_filename.rsplit('.', 1)[0] + ".mp4" if '.' in output_filename else output_filename + ".mp4"
                
            output_path = effective_output_dir / output_filename
            
            music_path = MUSIC_DIR / music_file if music_file else None
            await asyncio.to_thread(merge_clips, clip_paths, output_path, music_path, mute_original)

            job_status.update(
                state="done",
                progress=len(clips),
                message="Highlight video generation complete!",
                output_file=output_filename,
                actual_path=str(output_path.resolve()),
                clips_preview=formatted_clips_preview,
                highlight_url=f"/api/download/{output_filename}",
                video_filename=video_path.name,
                source_video_url=f"/api/videos/{video_path.name}"
            )

            # Dual-save: Copy to default OUTPUT_DIR for browser playback if custom folder was used
            if output_path.resolve() != (OUTPUT_DIR / output_filename).resolve():
                try:
                    shutil.copy2(output_path, OUTPUT_DIR / output_filename)
                    logger.info(f"Dual-save: Copied {output_filename} to {OUTPUT_DIR}")
                except Exception as e:
                    logger.warning(f"Dual-save copy failed: {e}")

        logger.info(f"Pipeline complete: {output_path}")

    except Exception as e:
        logger.exception("Pipeline error")
        job_status.update(state="error", message=f"Error: {str(e)}")


# ---------------------------------------------------------------------------
# API — Job status
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def get_status():
    """Return current pipeline status."""
    return job_status


# ---------------------------------------------------------------------------
# API — Download / stream output
# ---------------------------------------------------------------------------
@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Download the generated highlight video."""
    path = OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="video/mp4", filename=filename)


@app.get("/api/clips/{session_id}/{filename}")
async def get_session_clip(session_id: str, filename: str):
    """Stream an individual extracted clip directly from session storage."""
    clip_path = CLIPS_DIR / session_id / filename
    if not clip_path.exists():
        # Check fallback in CLIPS_DIR root or OUTPUT_DIR
        if (CLIPS_DIR / filename).exists():
            clip_path = CLIPS_DIR / filename
        elif (OUTPUT_DIR / filename).exists():
            clip_path = OUTPUT_DIR / filename
        else:
            raise HTTPException(404, f"Clip not found: {filename}")
    return FileResponse(clip_path, media_type="video/mp4", filename=filename)


@app.get("/api/videos/{filename}")
async def get_input_video(filename: str):
    """Stream or download an uploaded match video from VIDEO_DIR."""
    path = VIDEO_DIR / filename
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path)


@app.post("/api/preview_clip")
async def preview_clip(
    video_filename: str = Form(...),
    start_time: float = Form(...),
    end_time: float = Form(...),
):
    """Generate a quick on-the-fly preview clip for the timeline editor."""
    video_path = VIDEO_DIR / video_filename
    if not video_path.exists():
        raise HTTPException(404, f"Video not found: {video_filename}")

    if end_time <= start_time:
        raise HTTPException(400, "End time must be after start time")

    duration = end_time - start_time
    if duration > 120.0:  # Safety cap at 2 minutes
        duration = 120.0

    # Ensure output name is unique
    output_name = f"preview_{uuid.uuid4().hex[:8]}.mp4"
    output_path = OUTPUT_DIR / output_name

    # Import FFMPEG from clipper
    from backend.clipper import FFMPEG
    import subprocess

    # 1. Try fast stream copy first (virtually instant, ~100ms)
    cmd_fast = [
        FFMPEG, "-y",
        "-ss", str(start_time),
        "-i", str(video_path),
        "-t", str(duration),
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        str(output_path)
    ]

    try:
        result = await asyncio.to_thread(
            lambda: subprocess.run(cmd_fast, capture_output=True, text=True, timeout=5)
        )
        # Check if the output file is valid and of reasonable size
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
            logger.info(f"Fast preview stream-copy succeeded: {output_name}")
            return {"output_file": output_name}
    except Exception as e:
        logger.warning(f"Fast preview stream-copy failed or timed out: {e}")

    # Remove failed/empty output file if it exists
    if output_path.exists():
        try:
            output_path.unlink()
        except Exception:
            pass

    # 2. Fallback to transcoding (lower resolution to 360p and crf 30 for speed)
    logger.info("Falling back to transcoding preview clip...")
    cmd_fallback = [
        FFMPEG, "-y",
        "-ss", str(start_time),
        "-i", str(video_path),
        "-t", str(duration),
        "-vf", "scale=-2:360",  # Downscale to 360p height for faster encoding
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-ac", "2",
        "-movflags", "+faststart",
        str(output_path)
    ]

    try:
        result = await asyncio.to_thread(
            lambda: subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=30)
        )
        if result.returncode != 0:
            raise HTTPException(500, f"FFmpeg error: {result.stderr[-300:]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "FFmpeg timed out")

    return {"output_file": output_name}


# ---------------------------------------------------------------------------
# API — Short Clip Cutter (manual timecode extraction)
# ---------------------------------------------------------------------------
@app.post("/api/cut_clip")
async def cut_clip(
    video_filename: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    clip_name: str = Form("short_clip"),
):
    """Extract a precise short clip between two timecodes using FFmpeg."""
    video_path = VIDEO_DIR / video_filename
    if not video_path.exists():
        raise HTTPException(404, f"Video not found: {video_filename}")

    def _parse_time(t: str) -> float:
        """Convert h:mm:ss or mm:ss string to seconds."""
        parts = t.strip().split(":")
        parts = [float(p) for p in parts]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return float(parts[0])

    try:
        t_start = _parse_time(start_time)
        t_end = _parse_time(end_time)
    except Exception:
        raise HTTPException(400, "Invalid time format. Use h:mm:ss or mm:ss")

    if t_end <= t_start:
        raise HTTPException(400, "End time must be after start time")

    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in clip_name).strip() or "short_clip"
    output_name = f"{safe_name}_{uuid.uuid4().hex[:6]}.mp4"
    output_path = OUTPUT_DIR / output_name

    duration = t_end - t_start

    from backend.clipper import FFMPEG
    import subprocess
    cmd = [
        FFMPEG, "-y",
        "-i", str(video_path),
        "-ss", str(t_start),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-c:a", "aac", "-movflags", "+faststart",
        str(output_path)
    ]

    try:
        result = await asyncio.to_thread(
            lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        )
        if result.returncode != 0:
            raise HTTPException(500, f"FFmpeg error: {result.stderr[-300:]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "FFmpeg timed out")

    logger.info(f"Short clip saved: {output_path}")
    return {"output_file": output_name, "message": "Clip extracted successfully!"}


# Static files — serve frontend
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
