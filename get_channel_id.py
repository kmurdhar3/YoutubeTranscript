import sys
from yt_dlp import YoutubeDL

def get_channel_id(url: str) -> str:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        channel_id = info.get("channel_id") or info.get("uploader_id")
        return channel_id

def get_uploads_playlist_url(channel_id: str) -> str:
    if not channel_id.startswith("UC") or len(channel_id) < 3:
        raise ValueError("Invalid YouTube Channel ID format")

    # Replace leading UC → UU but KEEP the rest unchanged
    uploads_playlist_id = "UU" + channel_id[2:]

    return f"https://www.youtube.com/playlist?list={uploads_playlist_id}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 get_channel_info.py <YOUTUBE_CHANNEL_URL>")
        sys.exit(1)

    url = sys.argv[1]

    try:
        cid = get_channel_id(url)
        print("Channel ID:", cid)

        playlist_url = get_uploads_playlist_url(cid)
        print("Uploads Playlist URL:", playlist_url)

    except Exception as e:
        print("Error:", e)

