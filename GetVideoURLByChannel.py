#!/usr/bin/env python3
"""
YouTube Video URL Extractor
This script extracts all video URLs from a YouTube channel or playlist.
"""

import yt_dlp
import sys
import re


def is_playlist_url(url):
    """
    Check if the URL is a playlist URL.
    
    Args:
        url: YouTube URL
    
    Returns:
        bool: True if it's a playlist URL
    """
    return 'list=' in url or '/playlist?' in url


def get_videos(url):
    """
    Extract all video URLs from a YouTube channel or playlist.
    
    Args:
        url: URL of the YouTube channel or playlist
    
    Returns:
        tuple: (list of video URLs, source type)
    """
    # Configure yt-dlp options
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,  # Don't download, just extract info
        'force_generic_extractor': False,
        'ignoreerrors': True,  # Continue on download errors
    }
    
    video_urls = []
    source_type = "playlist" if is_playlist_url(url) else "channel"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Fetching videos from {source_type}: {url}")
            print("This may take a moment...\n")
            
            # Extract info
            result = ydl.extract_info(url, download=False)
            
            # Get playlist/channel title if available
            title = result.get('title', 'Unknown')
            uploader = result.get('uploader', result.get('channel', ''))
            
            print(f"Source: {title}")
            if uploader:
                print(f"Uploader: {uploader}")
            print()
            
            # Check if we got entries (videos)
            if 'entries' in result:
                for entry in result['entries']:
                    if entry:
                        video_id = entry.get('id')
                        if video_id:
                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                            video_urls.append(video_url)
                            
        return video_urls, source_type
    
    except Exception as e:
        print(f"Error: {e}")
        return [], source_type


def main():
    # Check if URL is provided
    if len(sys.argv) < 2:
        print("Usage: python youtube_channel_videos.py <channel_url_or_playlist_url>")
        print("\nChannel Examples:")
        print("  python youtube_channel_videos.py https://www.youtube.com/@channelname")
        print("  python youtube_channel_videos.py https://www.youtube.com/c/channelname")
        print("  python youtube_channel_videos.py https://www.youtube.com/channel/UCxxxxxxxxx")
        print("  python youtube_channel_videos.py https://www.youtube.com/@channelname/videos")
        print("\nPlaylist Examples:")
        print("  python youtube_channel_videos.py https://www.youtube.com/playlist?list=PLxxxxxxxxx")
        print("  python youtube_channel_videos.py https://www.youtube.com/watch?v=xxxxx&list=PLxxxxxxxxx")
        sys.exit(1)
    
    url = sys.argv[1]
    
    # For channel URLs, ensure we're looking at the videos page
    if not is_playlist_url(url):
        if '/videos' not in url and not url.endswith('/videos'):
            # Try to append /videos to get all uploads
            if url.endswith('/'):
                url = url + 'videos'
            else:
                url = url + '/videos'
    
    # Get all video URLs
    video_urls, source_type = get_videos(url)
    
    if video_urls:
        print(f"Found {len(video_urls)} videos:\n")
        print("-" * 60)
        for i, url in enumerate(video_urls, 1):
            print(f"{i}. {url}")
        print("-" * 60)
        
        # Optionally save to file
        
    else:
        print(f"No videos found or an error occurred.")


if __name__ == "__main__":
    main()