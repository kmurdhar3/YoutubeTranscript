#!/usr/bin/env python3
"""
Robust YouTube transcript downloader with JSON output option.
Usage:
    python3 download_transcript_robust.py "https://www.youtube.com/watch?v=VIDEO_ID" --format json
Formats:
    txt  -> plain text (default)
    json -> JSON array of transcript items (keeps start/duration if available)
"""

import argparse
import json
import os
import re
import subprocess
from urllib.parse import urlparse, parse_qs
from typing import Any, Dict, List, Optional

def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.query:
        q = parse_qs(parsed.query)
        if "v" in q and q["v"]:
            return q["v"][0]
    path = (parsed.path or "").strip("/")
    parts = path.split("/")
    if parts:
        candidate = parts[-1]
        if re.match(r"^[A-Za-z0-9_-]{6,}$", candidate):
            return candidate
    raise ValueError(f"Could not extract video id from URL: {url}")

def normalize_transcript_obj(obj: Any) -> List[Dict[str, Any]]:
    """
    Convert the library-returned object into a list of dicts.
    Ensures every dict contains:
    text, start, duration, speaker, confidence
    (speaker & confidence are always included as None)
    """
    def to_item_dict(it):
        d = {}

        # Extract basic known fields
        if isinstance(it, dict):
            d["text"] = it.get("text")
            d["start"] = it.get("start")
            d["duration"] = it.get("duration")
        else:
            d["text"] = getattr(it, "text", None)
            d["start"] = getattr(it, "start", None)
            d["duration"] = getattr(it, "duration", None)

        # Default (unavailable) fields
        d["speaker"] = None
        d["confidence"] = None

        return d

    # If already a list
    if isinstance(obj, (list, tuple)):
        return [to_item_dict(it) for it in obj]

    # If iterable TranscriptList
    try:
        items_iter = list(obj)
        if items_iter:
            return [to_item_dict(it) for it in items_iter]
    except Exception:
        pass

    # Try common method names
    for method_name in ("fetch", "list", "to_list", "as_list", "get_transcript"):
        if hasattr(obj, method_name):
            try:
                res = getattr(obj, method_name)
                res = res() if callable(res) else res
                return normalize_transcript_obj(res)
            except Exception:
                pass

    raise RuntimeError("Unable to normalize transcript object returned by library.")

def transcript_items_to_text(items: List[Dict[str, Any]]) -> str:
    lines = []
    for it in items:
        txt = None
        if isinstance(it, dict):
            txt = it.get("text") or it.get("message") or it.get("snippet")
        elif hasattr(it, "text"):
            txt = getattr(it, "text")
        elif isinstance(it, str):
            txt = it
        if txt:
            lines.append(str(txt).strip())
    cleaned = [ln for ln in lines if ln]
    return "\n".join(cleaned)

def yt_dlp_subtitle_fallback(url: str, lang: str = "en") -> Optional[List[Dict[str, Any]]]:
    """
    Try using yt-dlp to download auto subtitles and return list of dicts.
    Each dict will have at least 'text' and may include 'start' if parseable.
    """
    try:
        from yt_dlp import YoutubeDL
    except Exception:
        YoutubeDL = None

    vid = extract_video_id(url)
    out_base = f"{vid}.subs"

    if YoutubeDL:
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': [lang],
            'subtitlesformat': 'vtt/srt/best',
            'outtmpl': out_base + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception:
            pass
    else:
        cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", lang,
            "--skip-download",
            "-o", out_base + ".%(ext)s",
            url,
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            return None

    # find files matching prefix
    candidates = [f for f in os.listdir(".") if f.startswith(out_base) and f.endswith((".vtt", ".srt", ".txt"))]
    if not candidates:
        return None

    # pick first candidate
    candidate = candidates[0]
    with open(candidate, "r", encoding="utf-8", errors="ignore") as fh:
        data = fh.read()

    # Try parsing VTT cues to extract start/duration/text
    cues = []
    # VTT timestamp pattern
    vtt_pattern = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d+)\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d+)\s*\n(.*?)\n\n", re.S)
    srt_pattern = re.compile(r"\d+\s*\n(\d{2}:\d{2}:\d{2},\d+)\s*-->\s*(\d{2}:\d{2}:\d{2},\d+)\s*\n(.*?)(?:\n{2,}|\Z)", re.S)

    m_vtt = list(vtt_pattern.finditer(data))
    if m_vtt:
        for mm in m_vtt:
            start_ts = mm.group(1).strip()
            end_ts = mm.group(2).strip()
            text = mm.group(3).strip().replace("\n", " ")
            # convert HH:MM:SS.mmm to seconds float
            def to_secs(t):
                h, m, s = t.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            try:
                start = to_secs(start_ts)
                duration = round(to_secs(end_ts) - start, 3)
            except Exception:
                start = None
                duration = None
            entry = {"text": text}
            if start is not None:
                entry["start"] = start
            if duration is not None:
                entry["duration"] = duration
            cues.append(entry)
    else:
        m_srt = list(srt_pattern.finditer(data))
        if m_srt:
            for mm in m_srt:
                start_ts = mm.group(1).strip().replace(",", ".")
                end_ts = mm.group(2).strip().replace(",", ".")
                text = mm.group(3).strip().replace("\n", " ")
                def to_secs(t):
                    h, m, s = t.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)
                try:
                    start = to_secs(start_ts)
                    duration = round(to_secs(end_ts) - start, 3)
                except Exception:
                    start = None
                    duration = None
                entry = {"text": text}
                if start is not None:
                    entry["start"] = start
                if duration is not None:
                    entry["duration"] = duration
                cues.append(entry)
        else:
            # fallback: split by blank lines or line breaks; create simple text-only items
            parts = [p.strip() for p in re.split(r"\n{2,}", data) if p.strip()]
            for p in parts:
                p_clean = re.sub(r"\d{2}:\d{2}:\d{2}\.\d+\s*-->\s*\d{2}:\d{2}:\d{2}\.\d+", "", p)
                p_clean = re.sub(r"\d+\n", "", p_clean)
                p_clean = p_clean.replace("\n", " ").strip()
                if p_clean:
                    cues.append({"text": p_clean})
    return cues if cues else None

def save_output(vid: str, items: List[Dict[str, Any]], fmt: str, custom_path: Optional[str]) -> str:
    # If user provided --output use that
    if custom_path:
        filename = custom_path
    else:
        filename = f"{vid}_transcript.{fmt}"

    # For TXT format
    if fmt == "txt":
        text = "\n".join([item["text"] for item in items if item.get("text")])
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)
        return filename

    # For JSON format
    if fmt == "json":
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return filename

    raise ValueError("Unknown format")

def download_transcript(url: str, prefer_lang: Optional[str], fmt: str, output_name: Optional[str]) -> str:
    vid = extract_video_id(url)
    items = None
    fetch_error = None

    # Try youtube-transcript-api library (support old and new APIs)
    try:
        import youtube_transcript_api
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception as e:
        YouTubeTranscriptApi = None
        fetch_error = e

    if YouTubeTranscriptApi is not None:
        # try old static API first
        try:
            if hasattr(YouTubeTranscriptApi, "get_transcript"):
                if prefer_lang:
                    raw = YouTubeTranscriptApi.get_transcript(vid, languages=[prefer_lang])
                else:
                    raw = YouTubeTranscriptApi.get_transcript(vid)
                items = normalize_transcript_obj(raw)
            else:
                raise AttributeError("no static get_transcript")
        except Exception:
            # instance-based API
            try:
                api = YouTubeTranscriptApi()
                if prefer_lang:
                    try:
                        raw = api.fetch(vid, languages=[prefer_lang])
                    except TypeError:
                        raw = api.fetch(vid)
                else:
                    try:
                        raw = api.fetch(vid)
                    except Exception:
                        raw = api.list(vid)
                items = normalize_transcript_obj(raw)
            except Exception as e:
                fetch_error = e
                items = None

    # fallback to yt-dlp if library didn't produce items
    if not items:
        try:
            items = yt_dlp_subtitle_fallback(url, lang=prefer_lang or "en")
        except Exception as e:
            fetch_error = e
            items = None

    if not items:
        raise RuntimeError(f"Failed to retrieve transcript. Last error: {fetch_error}")

    # If user requested json but items are plain text fragments, keep structure as list of dicts
    return save_output(vid, items, fmt, output_name)


def main():
    parser = argparse.ArgumentParser(description="Download YouTube transcript (robust) with JSON output.")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--lang", help="language code (e.g. en)", default=None)
    parser.add_argument("--format", choices=("txt", "json"), default="txt", help="output format (txt or json)")
    parser.add_argument("--output", help="Custom output filename (must end with .json or .txt)", default=None) 

    args = parser.parse_args()

    print("Downloading transcript...")
    try:
        out = download_transcript(url=args.url,prefer_lang=args.lang,fmt=args.format,output_name=args.output)

        print("Saved:", out)
    except Exception as e:
        print("ERROR:", e)
        print("If this persists, try: pip install youtube-transcript-api yt-dlp  OR check if subtitles are disabled for the video.")

if __name__ == "__main__":
    main()

