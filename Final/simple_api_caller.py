#!/usr/bin/env python3
"""
Flask API for Bright Data - Simple & Clean
GUARANTEED to return all items in the array
"""

from flask import Flask, request, jsonify, Response
import requests
import json
from datetime import datetime
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
API_TOKEN = "2d0f15c9e903030daf1453ba70201c4da9bde54ba908d3ea63b3b287276c5cbe"
DATASET_ID = "gd_lk56epmy2i5g7lzu0k"
BRIGHT_DATA_API_URL = "https://api.brightdata.com/datasets/v3/scrape"


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
        "version": "5.0 - Pass-through",
        "note": "Returns EXACT Bright Data response with no modifications",
        "endpoints": {
            "/transcribe": "POST - Single video",
            "/batch-transcribe": "POST - Multiple videos"
        }
    })


if __name__ == '__main__':
    print("="*60)
    print("Bright Data API Proxy v5.0")
    print("="*60)
    print("This version returns the EXACT response from Bright Data")
    print("No parsing, no modification, just pass-through")
    print("\nStarting on http://localhost:5000")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)