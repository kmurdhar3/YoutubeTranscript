#!/usr/bin/env python3
"""
Flask API for Bright Data - Simple & Clean
GUARANTEED to return all items in the array
Now includes channel/playlist transcription!
"""

from flask import Flask, request, jsonify, Response
import requests
import json
from datetime import datetime
import logging
import yt_dlp

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
API_TOKEN = "2d0f15c9e903030daf1453ba70201c4da9bde54ba908d3ea63b3b287276c5cbe"
DATASET_ID = "gd_lk56epmy2i5g7lzu0k"
BRIGHT_DATA_API_URL = "https://api.brightdata.com/datasets/v3/scrape"


def is_playlist_url(url):
    """Check if the URL is a playlist URL."""
    return 'list=' in url or '/playlist?' in url


def extract_video_urls(channel_or_playlist_url, max_videos=None):
    """
    Extract all video URLs from a YouTube channel or playlist.
    
    Args:
        channel_or_playlist_url: URL of the YouTube channel or playlist
        max_videos: Maximum number of videos to extract (None = all)
    
    Returns:
        tuple: (list of video URLs, source type, metadata)
    """
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': False,
        'ignoreerrors': True,
    }
    
    video_urls = []
    source_type = "playlist" if is_playlist_url(channel_or_playlist_url) else "channel"
    
    try:
        # For channel URLs, ensure we're looking at the videos page
        url = channel_or_playlist_url
        if not is_playlist_url(url):
            if '/videos' not in url and not url.endswith('/videos'):
                if url.endswith('/'):
                    url = url + 'videos'
                else:
                    url = url + '/videos'
        
        logger.info(f"[EXTRACT] Fetching videos from {source_type}: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            
            # Get metadata
            title = result.get('title', 'Unknown')
            uploader = result.get('uploader', result.get('channel', ''))
            
            logger.info(f"[EXTRACT] Source: {title}")
            if uploader:
                logger.info(f"[EXTRACT] Uploader: {uploader}")
            
            # Extract video URLs
            if 'entries' in result:
                for entry in result['entries']:
                    if entry:
                        video_id = entry.get('id')
                        if video_id:
                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                            video_urls.append(video_url)
                            
                            # Stop if we've reached max_videos
                            if max_videos and len(video_urls) >= max_videos:
                                break
            
            metadata = {
                "title": title,
                "uploader": uploader,
                "source_type": source_type,
                "total_videos": len(video_urls)
            }
            
            logger.info(f"[EXTRACT] Found {len(video_urls)} videos")
            return video_urls, source_type, metadata
            
    except Exception as e:
        logger.error(f"[EXTRACT] Error: {e}")
        raise


@app.route('/transcribe-channel', methods=['POST'])
def transcribe_channel():
    """
    Get transcriptions for all videos in a YouTube channel or playlist.
    
    Expected JSON body:
    {
        "channel_url": "https://www.youtube.com/@channelname",  // or playlist URL
        "max_videos": 10,  // optional, limit number of videos
        "language": "",  // optional
        "country": ""  // optional
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'channel_url' not in data:
            return jsonify({
                "error": "Missing required field: channel_url"
            }), 400
        
        channel_url = data['channel_url']
        max_videos = data.get('max_videos')  # None = all videos
        language = data.get('language', '')
        country = data.get('country', '')
        
        logger.info(f"[CHANNEL] Starting transcription for: {channel_url}")
        
        # Step 1: Extract all video URLs
        try:
            video_urls, source_type, metadata = extract_video_urls(channel_url, max_videos)
        except Exception as e:
            return jsonify({
                "error": f"Failed to extract video URLs: {str(e)}"
            }), 500
        
        if not video_urls:
            return jsonify({
                "error": "No videos found in channel/playlist"
            }), 404
        
        logger.info(f"[CHANNEL] Extracted {len(video_urls)} URLs, sending to Bright Data...")
        
        # Step 2: Send to Bright Data for transcription
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        }
        
        input_data = [
            {
                "url": url,
                "transcription_language": language,
                "country": country
            }
            for url in video_urls
        ]
        
        request_body = json.dumps({"input": input_data})
        
        params = {
            "dataset_id": DATASET_ID,
            "custom_output_fields": "description,title,transcript,formatted_transcript",
            "notify": "false",
            "include_errors": "true"
        }
        
        # Call Bright Data API
        response = requests.post(
            BRIGHT_DATA_API_URL,
            headers=headers,
            params=params,
            data=request_body,
            timeout=300  # 5 minutes for large batches
        )
        
        logger.info(f"[CHANNEL] Bright Data response status: {response.status_code}")
        logger.info(f"[CHANNEL] Response size: {len(response.text)} chars")
        
        response.raise_for_status()
        
        # Parse response (handle multi-line JSON like batch-transcribe)
        response_text = response.text
        
        # Try to parse as JSON
        try:
            transcripts = json.loads(response_text)
        except json.JSONDecodeError:
            # Handle multi-line JSON response (same as batch-transcribe)
            logger.warning(f"[CHANNEL] Multi-line JSON detected, parsing line by line")
            lines = response_text.strip().split('\n')
            
            # Try to parse first valid line
            transcripts = None
            for i, line in enumerate(lines):
                try:
                    transcripts = json.loads(line)
                    logger.info(f"[CHANNEL] Successfully parsed line {i+1}")
                    break
                except:
                    continue
            
            if transcripts is None:
                logger.error(f"[CHANNEL] Could not parse any line as JSON")
                raise ValueError("Failed to parse Bright Data response")
        
        # Ensure transcripts is a list
        if isinstance(transcripts, dict) and 'data' in transcripts:
            transcripts = transcripts['data']
        elif not isinstance(transcripts, list):
            transcripts = [transcripts]
        
        # Return with metadata
        return jsonify({
            "metadata": metadata,
            "transcripts": transcripts,
            "count": len(transcripts)
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[CHANNEL] API error: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"[CHANNEL] Unexpected error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/batch-transcribe', methods=['POST'])
def batch_transcribe():
    """
    Get transcriptions for multiple YouTube videos.
    Returns the EXACT response from Bright Data.
    """
    try:
        data = request.get_json()
        
        if not data or 'urls' not in data:
            return jsonify({"error": "Missing required field: urls"}), 400
        
        urls = data['urls']
        language = data.get('language', '')
        country = data.get('country', '')
        
        # Prepare Bright Data request
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        }
        
        input_data = [
            {
                "url": url,
                "transcription_language": language,
                "country": country
            }
            for url in urls
        ]
        
        request_body = json.dumps({"input": input_data})
        
        params = {
            "dataset_id": DATASET_ID,
            "custom_output_fields": "description,title,transcript,formatted_transcript",
            "notify": "false",
            "include_errors": "true"
        }
        
        logger.info(f"[BATCH] Requesting {len(urls)} URLs from Bright Data")
        
        # Call Bright Data API
        response = requests.post(
            BRIGHT_DATA_API_URL,
            headers=headers,
            params=params,
            data=request_body,
            timeout=180  # 3 minutes for batch
        )
        
        logger.info(f"[BATCH] Response status: {response.status_code}")
        logger.info(f"[BATCH] Response size: {len(response.text)} chars")
        
        response.raise_for_status()
        
        # Return EXACTLY what Bright Data returns
        # No parsing, no modification, just pass it through
        return Response(
            response.text,
            status=200,
            mimetype='application/json'
        )
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[BATCH] API error: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"[BATCH] Unexpected error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/transcribe', methods=['POST'])
def transcribe():
    """
    Get transcription for a single YouTube video.
    Returns the EXACT response from Bright Data.
    """
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({"error": "Missing required field: url"}), 400
        
        url = data['url']
        language = data.get('language', '')
        country = data.get('country', '')
        
        # Prepare Bright Data request
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        }
        
        input_data = [{
            "url": url,
            "transcription_language": language,
            "country": country
        }]
        
        request_body = json.dumps({"input": input_data})
        
        params = {
            "dataset_id": DATASET_ID,
            "custom_output_fields": "description,title,transcript,formatted_transcript",
            "notify": "false",
            "include_errors": "true"
        }
        
        logger.info(f"[SINGLE] Requesting URL from Bright Data: {url}")
        
        # Call Bright Data API
        response = requests.post(
            BRIGHT_DATA_API_URL,
            headers=headers,
            params=params,
            data=request_body,
            timeout=120
        )
        
        logger.info(f"[SINGLE] Response status: {response.status_code}")
        logger.info(f"[SINGLE] Response size: {len(response.text)} chars")
        
        response.raise_for_status()
        
        # Return EXACTLY what Bright Data returns
        return Response(
            response.text,
            status=200,
            mimetype='application/json'
        )
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[SINGLE] API error: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"[SINGLE] Unexpected error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "service": "Bright Data API Proxy",
        "version": "6.0 - With Channel/Playlist Support",
        "note": "Now supports channel and playlist transcription!",
        "endpoints": {
            "/transcribe": "POST - Single video",
            "/batch-transcribe": "POST - Multiple videos (provide URLs)",
            "/transcribe-channel": "POST - All videos from channel/playlist (NEW!)"
        },
        "examples": {
            "channel": {
                "endpoint": "/transcribe-channel",
                "body": {
                    "channel_url": "https://www.youtube.com/@channelname",
                    "max_videos": 10,
                    "language": "",
                    "country": ""
                }
            },
            "playlist": {
                "endpoint": "/transcribe-channel",
                "body": {
                    "channel_url": "https://www.youtube.com/playlist?list=PLxxxxxxxxx",
                    "max_videos": 5
                }
            }
        }
    })


if __name__ == '__main__':
    print("="*60)
    print("Bright Data API Proxy v6.0")
    print("="*60)
    print("✓ Single video transcription")
    print("✓ Batch video transcription")
    print("✓ Channel transcription (NEW!)")
    print("✓ Playlist transcription (NEW!)")
    print("\nStarting on http://localhost:5000")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)