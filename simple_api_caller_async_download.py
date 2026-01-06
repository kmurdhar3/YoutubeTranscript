#!/usr/bin/env python3
"""
Flask API for Bright Data - Async File Download Version
All endpoints now poll and return downloadable files!
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import json
from datetime import datetime
import logging
import yt_dlp
import time

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
API_TOKEN = "2d0f15c9e903030daf1453ba70201c4da9bde54ba908d3ea63b3b287276c5cbe"
DATASET_ID = "gd_lk56epmy2i5g7lzu0k"
BRIGHT_DATA_API_URL = "https://api.brightdata.com/datasets/v3/scrape"
SNAPSHOT_API_URL = "https://api.brightdata.com/datasets/v3/snapshot"
SNAPSHOT_DOWNLOAD_URL = "https://api.brightdata.com/datasets/v3/progress"


def is_playlist_url(url):
    """Check if the URL is a playlist URL."""
    return 'list=' in url or '/playlist?' in url


def extract_video_urls(channel_or_playlist_url, max_videos=None):
    """
    Extract all video URLs from a YouTube channel or playlist.
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
            
            title = result.get('title', 'Unknown')
            uploader = result.get('uploader', result.get('channel', ''))
            
            logger.info(f"[EXTRACT] Source: {title}")
            if uploader:
                logger.info(f"[EXTRACT] Uploader: {uploader}")
            
            if 'entries' in result:
                for entry in result['entries']:
                    if entry:
                        video_id = entry.get('id')
                        if video_id:
                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                            video_urls.append(video_url)
                            
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


def poll_until_ready(snapshot_id, max_wait_minutes=30):
    """
    Poll a snapshot until it's ready.
    
    Args:
        snapshot_id: Bright Data snapshot ID
        max_wait_minutes: Maximum time to wait
        
    Returns:
        tuple: (success, data_or_error)
    """
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
    }
    
    max_attempts = max_wait_minutes * 2  # Check every 30 seconds
    attempt = 0
    
    logger.info(f"[POLL] Starting to poll snapshot: {snapshot_id}")
    
    while attempt < max_attempts:
        attempt += 1
        
        try:
            # Check status
            status_response = requests.get(
                f"{SNAPSHOT_API_URL}/{snapshot_id}",
                headers=headers,
                timeout=30
            )
            
            status_response.raise_for_status()
            
            # Try to parse response
            response_text = status_response.text
            
            try:
                status_data = json.loads(response_text)
            except json.JSONDecodeError:
                # Handle multi-line JSON - each line is a separate video result
                logger.info(f"[POLL] Multi-line JSON detected, parsing all lines")
                lines = response_text.strip().split('\n')
                status_data = []
                
                for i, line in enumerate(lines):
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        status_data.append(item)
                    except Exception as parse_error:
                        logger.warning(f"[POLL] Could not parse line {i+1}: {parse_error}")
                        continue
                
                if not status_data:
                    logger.error(f"[POLL] Could not parse any lines as JSON")
                    return False, {"error": "Failed to parse Bright Data response"}
                
                logger.info(f"[POLL] Parsed {len(status_data)} items from multi-line JSON")
            
            # Check if ready
            if isinstance(status_data, list):
                # Multi-line JSON response - already ready!
                logger.info(f"[POLL] Snapshot ready! Got {len(status_data)} items")
                return True, status_data
            
            # Get status from response
            status = status_data.get('status', 'unknown')
            logger.info(f"[POLL] Attempt {attempt}/{max_attempts} - Status: {status}")
            
            # Check if ready
            if status == 'ready':
                logger.info(f"[POLL] Snapshot ready!")
                
                # Return the data
                if 'data' in status_data:
                    return True, status_data['data']
                else:
                    return True, status_data
            
            # Check if failed
            elif status in ['failed', 'error', 'cancelled']:
                logger.error(f"[POLL] Snapshot failed with status: {status}")
                return False, {
                    "error": f"Snapshot processing failed: {status}",
                    "details": status_data
                }
            
            # All other statuses mean "still processing"
            # (starting, running, pending, processing, etc.)
            else:
                if attempt < max_attempts:
                    logger.info(f"[POLL] Status '{status}' - Still processing... waiting 30 seconds")
                    time.sleep(30)
                else:
                    logger.error(f"[POLL] Timeout with status: {status}")
                    return False, {
                        "error": f"Timeout while waiting for snapshot (last status: {status})",
                        "snapshot_id": snapshot_id
                    }
        
        except Exception as e:
            logger.error(f"[POLL] Error during polling: {e}")
            if attempt >= max_attempts:
                return False, {"error": str(e)}
            time.sleep(30)
    
    # Timeout
    logger.error(f"[POLL] Timeout after {max_wait_minutes} minutes")
    return False, {
        "error": f"Polling timeout after {max_wait_minutes} minutes",
        "snapshot_id": snapshot_id,
        "suggestion": "Snapshot may still be processing. Check manually later."
    }


def call_brightdata_and_poll(urls, language="", country="", output_fields="description,title,transcript,formatted_transcript", endpoint_name="API"):
    """
    Call Bright Data API and poll until results are ready.
    
    Returns:
        tuple: (success, data_or_error, snapshot_id)
    """
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
        "custom_output_fields": output_fields,
        "notify": "false",
        "include_errors": "true"
    }
    
    logger.info(f"[{endpoint_name}] Calling Bright Data for {len(urls)} URL(s)")
    
    try:
        # Call Bright Data API
        response = requests.post(
            BRIGHT_DATA_API_URL,
            headers=headers,
            params=params,
            data=request_body,
            timeout=180
        )
        
        response.raise_for_status()
        response_text = response.text
        
        logger.info(f"[{endpoint_name}] Response status: {response.status_code}")
        logger.info(f"[{endpoint_name}] Response size: {len(response_text)} chars")
        
        # Parse response
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Handle multi-line JSON - each line is a separate item
            logger.info(f"[{endpoint_name}] Multi-line JSON detected, parsing all lines")
            lines = response_text.strip().split('\n')
            result = []
            
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    result.append(item)
                except Exception as parse_error:
                    logger.warning(f"[{endpoint_name}] Could not parse line {i+1}: {parse_error}")
                    continue
            
            if not result:
                return False, {"error": "Failed to parse Bright Data response"}, None
            
            logger.info(f"[{endpoint_name}] Parsed {len(result)} items from multi-line JSON")
        
        # Check if it's a snapshot response
        snapshot_id = None
        
        # Case 1: List with snapshot_id in first item
        if isinstance(result, list) and len(result) > 0:
            if 'snapshot_id' in result[0]:
                snapshot_id = result[0]['snapshot_id']
        
        # Case 2: Dict with snapshot_id directly
        elif isinstance(result, dict) and 'snapshot_id' in result:
            snapshot_id = result['snapshot_id']
        
        # If we have a snapshot_id, poll until ready
        if snapshot_id:
            logger.info(f"[{endpoint_name}] Got snapshot_id: {snapshot_id}")
            logger.info(f"[{endpoint_name}] Status: {result.get('status', result[0].get('status') if isinstance(result, list) else 'unknown')}")
            logger.info(f"[{endpoint_name}] Polling for results...")
            
            # Poll until ready
            success, data = poll_until_ready(snapshot_id, max_wait_minutes=30)
            return success, data, snapshot_id
        
        # No snapshot_id - immediate results
        if isinstance(result, list):
            return True, result, None
        elif isinstance(result, dict) and 'data' in result:
            return True, result['data'], None
        else:
            return True, result, None
    
    except Exception as e:
        logger.error(f"[{endpoint_name}] Error: {e}")
        return False, {"error": str(e)}, None


@app.route('/transcribe', methods=['POST'])
def transcribe():
    """
    Transcribe single video - returns downloadable file.
    Polls in background until ready.
    
    Query params:
        ?download=true (default) - Force download
        ?download=false - Display in browser/Postman
    """
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({"error": "Missing required field: url"}), 400
        
        url = data['url']
        language = data.get('language', '')
        country = data.get('country', '')
        
        # Check if download is requested
        force_download = request.args.get('download', 'true').lower() == 'true'
        
        logger.info(f"[SINGLE] Request for URL: {url}, Download: {force_download}")
        
        # Call API and poll
        success, result, snapshot_id = call_brightdata_and_poll(
            [url],
            language,
            country,
            output_fields="description,title,transcript,formatted_transcript",
            endpoint_name="SINGLE"
        )
        
        if not success:
            return jsonify(result), 500
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_id = url.split('=')[-1][:11] if '=' in url else 'video'
        filename = f"transcript_{video_id}_{timestamp}.json"
        
        # Prepare response
        json_data = json.dumps(result, indent=2, ensure_ascii=False)
        
        if force_download:
            # Force download
            return Response(
                json_data,
                status=200,
                mimetype='application/octet-stream',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}',
                    'Content-Type': 'application/octet-stream',
                    'X-Download-Filename': filename
                }
            )
        else:
            # Display in browser/Postman
            return Response(
                json_data,
                status=200,
                mimetype='application/json',
                headers={
                    'Content-Type': 'application/json; charset=utf-8'
                }
            )
        
    except Exception as e:
        logger.error(f"[SINGLE] Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/batch-transcribe', methods=['POST'])
def batch_transcribe():
    """
    Transcribe multiple videos - returns downloadable file.
    Polls in background until ready.
    
    Query params:
        ?download=true (default) - Force download
        ?download=false - Display in browser/Postman
    """
    try:
        data = request.get_json()
        
        if not data or 'urls' not in data:
            return jsonify({"error": "Missing required field: urls"}), 400
        
        urls = data['urls']
        language = data.get('language', '')
        country = data.get('country', '')
        
        if not isinstance(urls, list) or len(urls) == 0:
            return jsonify({"error": "urls must be a non-empty array"}), 400
        
        # Check if download is requested
        force_download = request.args.get('download', 'true').lower() == 'true'
        
        logger.info(f"[BATCH] Request for {len(urls)} URLs, Download: {force_download}")
        
        # Call API and poll
        success, result, snapshot_id = call_brightdata_and_poll(
            urls,
            language,
            country,
            output_fields="description,title,transcript,formatted_transcript",
            endpoint_name="BATCH"
        )
        
        if not success:
            return jsonify(result), 500
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"batch_transcripts_{len(urls)}videos_{timestamp}.json"
        
        # Prepare response
        json_data = json.dumps(result, indent=2, ensure_ascii=False)
        
        if force_download:
            # Force download
            return Response(
                json_data,
                status=200,
                mimetype='application/octet-stream',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}',
                    'Content-Type': 'application/octet-stream',
                    'X-Download-Filename': filename
                }
            )
        else:
            # Display in browser/Postman
            return Response(
                json_data,
                status=200,
                mimetype='application/json',
                headers={
                    'Content-Type': 'application/json; charset=utf-8'
                }
            )
        
    except Exception as e:
        logger.error(f"[BATCH] Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/transcribe-channel', methods=['POST'])
def transcribe_channel():
    """
    Transcribe all videos from channel/playlist - returns downloadable file.
    Extracts URLs, polls in background until ready.
    
    Query params:
        ?download=true (default) - Force download
        ?download=false - Display in browser/Postman
    """
    try:
        data = request.get_json()
        
        if not data or 'channel_url' not in data:
            return jsonify({"error": "Missing required field: channel_url"}), 400
        
        channel_url = data['channel_url']
        max_videos = data.get('max_videos')
        language = data.get('language', '')
        country = data.get('country', '')
        
        # Check if download is requested
        force_download = request.args.get('download', 'true').lower() == 'true'
        
        logger.info(f"[CHANNEL] Request for: {channel_url}, Download: {force_download}")
        
        # Extract video URLs
        try:
            video_urls, source_type, metadata = extract_video_urls(channel_url, max_videos)
        except Exception as e:
            return jsonify({"error": f"Failed to extract video URLs: {str(e)}"}), 500
        
        if not video_urls:
            return jsonify({"error": "No videos found in channel/playlist"}), 404
        
        logger.info(f"[CHANNEL] Extracted {len(video_urls)} URLs")
        
        # Call API and poll
        success, result, snapshot_id = call_brightdata_and_poll(
            video_urls,
            language,
            country,
            output_fields="description,title,transcript,formatted_transcript",
            endpoint_name="CHANNEL"
        )
        
        if not success:
            return jsonify(result), 500
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_title = "".join(c for c in metadata['title'][:30] if c.isalnum() or c in (' ', '-', '_')).strip()
        clean_title = clean_title.replace(' ', '_')
        filename = f"channel_{clean_title}_{len(video_urls)}videos_{timestamp}.json"
        
        # Add metadata to result
        output = {
            "metadata": metadata,
            "transcripts": result,
            "count": len(result) if isinstance(result, list) else 1
        }
        
        # Prepare response
        json_data = json.dumps(output, indent=2, ensure_ascii=False)
        
        if force_download:
            # Force download
            return Response(
                json_data,
                status=200,
                mimetype='application/octet-stream',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}',
                    'Content-Type': 'application/octet-stream',
                    'X-Download-Filename': filename
                }
            )
        else:
            # Display in browser/Postman
            return Response(
                json_data,
                status=200,
                mimetype='application/json',
                headers={
                    'Content-Type': 'application/json; charset=utf-8'
                }
            )
        
    except Exception as e:
        logger.error(f"[CHANNEL] Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/transcribe-csv', methods=['POST'])
def transcribe_csv():
    """
    Upload CSV file with URLs and get transcripts as downloadable file.
    
    CSV Format:
        url
        https://youtu.be/VIDEO1
        https://youtu.be/VIDEO2
        https://youtu.be/VIDEO3
    
    Or with headers:
        url,language,country
        https://youtu.be/VIDEO1,English,US
        https://youtu.be/VIDEO2,Arabic,
    
    Query params:
        ?download=true (default) - Force download
        ?download=false - Display in browser/Postman
    
    Returns: Downloadable JSON file with all transcripts
    """
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({"error": "Missing required file: 'file'"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({"error": "File must be a CSV file"}), 400
        
        # Check if download is requested
        force_download = request.args.get('download', 'true').lower() == 'true'
        
        logger.info(f"[CSV] Processing file: {file.filename}")
        
        # Read CSV file
        import csv
        import io
        
        # Read file content
        file_content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(file_content))
        
        # Extract URLs and metadata
        urls = []
        url_metadata = []
        
        for row in csv_reader:
            if 'url' in row and row['url'].strip():
                url = row['url'].strip()
                urls.append(url)
                
                # Store metadata for each URL
                metadata = {
                    'url': url,
                    'language': row.get('language', '').strip(),
                    'country': row.get('country', '').strip()
                }
                url_metadata.append(metadata)
        
        if not urls:
            return jsonify({"error": "No valid URLs found in CSV file"}), 400
        
        logger.info(f"[CSV] Found {len(urls)} URLs in CSV")
        
        # For simplicity, use the same language/country for all
        # (You can modify this to handle per-URL settings)
        default_language = url_metadata[0]['language'] if url_metadata else ''
        default_country = url_metadata[0]['country'] if url_metadata else ''
        
        # Call API and poll
        success, result, snapshot_id = call_brightdata_and_poll(
            urls,
            default_language,
            default_country,
            output_fields="description,title,transcript,formatted_transcript",
            endpoint_name="CSV"
        )
        
        if not success:
            return jsonify(result), 500
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_filename = file.filename.rsplit('.', 1)[0]  # Remove .csv extension
        filename = f"transcripts_{original_filename}_{len(urls)}videos_{timestamp}.json"
        
        # Add metadata to result
        output = {
            "source": {
                "type": "csv_upload",
                "filename": file.filename,
                "total_urls": len(urls)
            },
            "transcripts": result,
            "count": len(result) if isinstance(result, list) else 1
        }
        
        # Prepare response
        json_data = json.dumps(output, indent=2, ensure_ascii=False)
        
        if force_download:
            # Force download
            return Response(
                json_data,
                status=200,
                mimetype='application/octet-stream',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}',
                    'Content-Type': 'application/octet-stream',
                    'X-Download-Filename': filename
                }
            )
        else:
            # Display in browser/Postman
            return Response(
                json_data,
                status=200,
                mimetype='application/json',
                headers={
                    'Content-Type': 'application/json; charset=utf-8'
                }
            )
        
    except Exception as e:
        logger.error(f"[CSV] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# Keep the manual snapshot endpoints for advanced users
@app.route('/check-snapshot/<snapshot_id>', methods=['GET'])
def check_snapshot(snapshot_id):
    """Check snapshot status manually."""
    try:
        headers = {"Authorization": f"Bearer {API_TOKEN}"}
        
        response = requests.get(
            f"{SNAPSHOT_API_URL}/{snapshot_id}",
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        return jsonify(response.json())
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/download-snapshot-file/<snapshot_id>', methods=['GET'])
def download_snapshot_file(snapshot_id):
    """Download snapshot as file (for manual workflow)."""
    try:
        headers = {"Authorization": f"Bearer {API_TOKEN}"}
        
        response = requests.get(
            f"{SNAPSHOT_API_URL}/{snapshot_id}",
            headers=headers,
            timeout=60
        )
        
        response.raise_for_status()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"transcripts_{snapshot_id}_{timestamp}.json"
        
        return Response(
            response.text,
            status=200,
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'application/json'
            }
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "service": "Bright Data API - Async File Download",
        "version": "10.0 - Now with CSV Upload!",
        "note": "All transcription endpoints now poll automatically and return downloadable files!",
        "endpoints": {
            "/transcribe": "POST - Single video → Auto-polls → Returns file",
            "/batch-transcribe": "POST - Multiple videos → Auto-polls → Returns file",
            "/transcribe-channel": "POST - Channel/playlist → Auto-polls → Returns file",
            "/transcribe-csv": "POST - Upload CSV file with URLs → Returns file (NEW!)",
            "/check-snapshot/<id>": "GET - Manual status check (advanced)",
            "/download-snapshot-file/<id>": "GET - Manual download (advanced)"
        },
        "how_it_works": {
            "step_1": "Send POST request to any endpoint",
            "step_2": "API calls Bright Data and gets snapshot_id",
            "step_3": "API automatically polls every 30 seconds",
            "step_4": "When ready, returns downloadable JSON file",
            "note": "May take several minutes for large requests"
        },
        "csv_format": {
            "simple": "url\nhttps://youtu.be/VIDEO1\nhttps://youtu.be/VIDEO2",
            "with_metadata": "url,language,country\nhttps://youtu.be/VIDEO1,English,US\nhttps://youtu.be/VIDEO2,Arabic,"
        },
        "examples": {
            "single": {
                "endpoint": "/transcribe",
                "body": {"url": "https://youtu.be/VIDEO_ID"},
                "returns": "transcript_VIDEO_ID_20260102_120000.json"
            },
            "batch": {
                "endpoint": "/batch-transcribe",
                "body": {"urls": ["url1", "url2", "url3"]},
                "returns": "batch_transcripts_3videos_20260102_120000.json"
            },
            "channel": {
                "endpoint": "/transcribe-channel",
                "body": {"channel_url": "https://www.youtube.com/@channel", "max_videos": 10},
                "returns": "channel_ChannelName_10videos_20260102_120000.json"
            },
            "csv": {
                "endpoint": "/transcribe-csv",
                "type": "multipart/form-data",
                "field": "file",
                "file": "urls.csv",
                "returns": "transcripts_urls_10videos_20260102_120000.json"
            }
        }
    })
         

if __name__ == '__main__':
    print("="*60)
    print("Bright Data API - Async File Download v10.0")
    print("="*60)
    print("🚀 ALL endpoints now:")
    print("   1. Submit to Bright Data")
    print("   2. Auto-poll until ready")
    print("   3. Return downloadable file")
    print("")
    print("✨ NEW: CSV Upload Support!")
    print("   Upload CSV file with URLs → Get transcripts")
    print("")
    print("⏱️  May take several minutes for large requests")
    print("📁 Files saved with automatic timestamped names")
    print("🌐 CORS enabled for browser requests")
    print("")
    print("Starting on http://localhost:5000")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)