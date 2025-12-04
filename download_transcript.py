#!/usr/bin/env python3
"""
Robust YouTube transcript downloader.
Handles both older youtube-transcript-api (get_transcript)
and newer versions (YouTubeTranscriptApi().fetch / .list).
If that fails, falls back to yt-dlp subtitle download (if yt-dlp installed).
Usage:
    python3 download_transcript_robust.py "https://www.youtube.com/watch?v=VIDEO_ID"
"""

import argparse
import os
import re
import subprocess
from urllib.parse import urlparse, parse_qs

def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    # common watch?v=VIDEO
    if parsed.query:
        q = parse_qs(parsed.query)
        if "v" in q and q["v"]:
            return q["v"][0]
    # youtu.be/VIDEO or /embed/VIDEO
    path = parsed.path or ""
    path = path.strip("/")
    # if path contains "embed/VIDEO" or "shorts/VIDEO"
    parts = path.split("/")
    if parts:
        # choose last segment if it looks like an id
        candidate = parts[-1]
        # basic sanity: video ids are alphanumeric, - and _
        if re.match(r"^[A-Za-z0-9_-]{6,}$", candidate):
            return candidate
    raise ValueError(f"Could not extract video id from URL: {url}")

def normalize_transcript_obj(obj):
    """
    Try to convert the returned object from the library into a list of dicts
    with keys that include 'text'. Returns list of items like {'text': ...}
    """
    # If it's already list-like of dicts, return it
    if isinstance(obj, (list, tuple)):
        return list(obj)

    # If it's an iterable (like TranscriptList), try iterating
    try:
        items = list(obj)
        if items:
            return items
    except TypeError:
        pass

    # Try common method names on the object
    for method_name in ("fetch", "list", "to_list", "as_list", "get_transcript"):
        if hasattr(obj, method_name):
            try:
                m = getattr(obj, method_name)
                res = m() if callable(m) else m
                if isinstance(res, (list, tuple)):
                    return list(res)
                # try to iterate
                try:
                    return list(res)
                except TypeError:
                    pass
            except Exception:
                pass

    # last resort: try treating object's repr as text (poor fallback)
    raise RuntimeError("Unable to normalize transcript object returned by library.")

def transcript_items_to_text(items):
    # items expected to be list of dicts with key 'text' or objects with attribute 'text'
    lines = []
    for it in items:
        # dict-like
        if isinstance(it, dict):
            txt = it.get("text") or it.get("message") or it.get("snippet")
            if txt:
                lines.append(txt)
                continue
        # object-like
        if hasattr(it, "text"):
            lines.append(str(getattr(it, "text")))
            continue
        # fallback: string-like
        if isinstance(it, str):
            lines.append(it)
            continue
        # try converting to string
        lines.append(str(it))
    # remove empty lines and dedupe whitespace
    cleaned = [ln.strip() for ln in lines if ln and ln.strip()]
    return "\n".join(cleaned)

def yt_dlp_subtitle_fallback(url, lang="en"):
    """
    Try using yt-dlp to download auto subtitles and convert to plain text.
    Requires yt-dlp to be installed and available in PATH or as python package.
    Returns path to saved text file or None.
    """
    # prefer python package if available
    try:
        from yt_dlp import YoutubeDL
    except Exception:
        YoutubeDL = None

    vid = extract_video_id(url)
    out_base = f"{vid}.subs"
    out_txt = f"{vid}_transcript.txt"

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
        # try CLI yt-dlp
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

    # find downloaded subtitle file
    for ext in (".vtt", ".srt", ".vtt.srt", ".srt.vtt"):
        candidate = f"{out_base}{ext}"
        if os.path.exists(candidate):
            # convert vtt/srt cues to plain text
            with open(candidate, "r", encoding="utf-8", errors="ignore") as fh:
                txt = fh.read()
            # remove cue timestamps and numbers
            txt = re.sub(r"\d+\n", "", txt)                       # cue numbers
            txt = re.sub(r"\d{2}:\d{2}:\d{2}\.\d+ --> .*?\n", "", txt)  # vtt timestamps
            txt = re.sub(r"\d{2}:\d{2}:\d{2},\d+ --> .*?\n", "", txt)  # srt timestamps
            txt = re.sub(r"\n{2,}", "\n", txt)
            txt = txt.strip()
            with open(out_txt, "w", encoding="utf-8") as wf:
                wf.write(txt)
            return out_txt
    # attempt to find any file matching prefix
    for f in os.listdir("."):
        if f.startswith(out_base) and f.endswith((".vtt", ".srt", ".txt")):
            with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                txt = fh.read()
            txt = re.sub(r"\d+\n", "", txt)
            txt = re.sub(r"\d{2}:\d{2}:\d{2}\.\d+ --> .*?\n", "", txt)
            txt = re.sub(r"\n{2,}", "\n", txt)
            txt = txt.strip()
            with open(out_txt, "w", encoding="utf-8") as wf:
                wf.write(txt)
            return out_txt
    return None

def download_transcript(url: str, prefer_lang=None) -> str:
    """
    Attempts multiple strategies; returns filepath of saved transcript or raises.
    """
    vid = extract_video_id(url)

    # 1) try to import library and use old static API first, then instance variants
    try:
        import youtube_transcript_api
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception as e:
        youtube_transcript_api = None
        YouTubeTranscriptApi = None

    if YouTubeTranscriptApi is not None:
        # try old static method (older versions)
        try:
            if hasattr(YouTubeTranscriptApi, "get_transcript"):
                # old API
                if prefer_lang:
                    items = YouTubeTranscriptApi.get_transcript(vid, languages=[prefer_lang])
                else:
                    items = YouTubeTranscriptApi.get_transcript(vid)
            else:
                raise AttributeError("no static get_transcript")
        except Exception:
            # fallback to instance-based API (newer versions)
            try:
                api = YouTubeTranscriptApi()
                # try fetch then list
                if prefer_lang:
                    try:
                        items = api.fetch(vid, languages=[prefer_lang])
                    except TypeError:
                        items = api.fetch(vid)
                else:
                    try:
                        items = api.fetch(vid)
                    except Exception:
                        items = api.list(vid)
            except Exception as e:
                items = None
                fetch_error = e
        else:
            fetch_error = None

        if items:
            try:
                norm = normalize_transcript_obj(items)
                text = transcript_items_to_text(norm)
                fname = f"{vid}_transcript.txt"
                with open(fname, "w", encoding="utf-8") as fh:
                    fh.write(text)
                return fname
            except Exception as e:
                # continue to fallback
                fetch_error = e

    # 2) fallback to yt-dlp subtitles
    out = yt_dlp_subtitle_fallback(url, lang=prefer_lang or "en")
    if out:
        return out

    # 3) nothing worked -> raise
    raise RuntimeError(f"Failed to retrieve transcript. Last error: {locals().get('fetch_error', None)}")

def main():
    p = argparse.ArgumentParser(description="Download YouTube transcript (robust).")
    p.add_argument("url", help="YouTube video URL")
    p.add_argument("--lang", help="language code (e.g. en)", default=None)
    args = p.parse_args()

    print("Downloading transcript...")
    try:
        out = download_transcript(args.url, prefer_lang=args.lang)
        print("Saved transcript:", out)
    except Exception as e:
        print("ERROR: could not download transcript:", e)
        print("Try installing yt-dlp (pip install yt-dlp) or check the video for subtitles disabled.")

if __name__ == "__main__":
    main()

