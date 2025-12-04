# YouTube Transcript Downloader (JSON / TXT)

A powerful, reliable Python CLI tool that downloads transcripts from any YouTube URL and saves them in **JSON** or **TXT** format.

This tool:
- Extracts transcripts using the `youtube-transcript-api`
- Supports both **plain text** and **structured JSON** output
- Allows specifying a **custom output filename** using `--output`
- Supports optional language selection via `--lang`
- Works for **normal videos, podcasts, interviews, shorts, livestreams**, etc.

---

## 🚀 Features

- ✔ Download YouTube transcript using a single command  
- ✔ Output formats: **JSON** or **TXT**  
- ✔ Custom output filename using `--output filename.json`  
- ✔ Auto-extracts video ID from any YouTube URL format  
- ✔ Works even for YouTube-generated auto transcripts  
- ✔ Light and no dependencies except transcript library  
- ✔ Clean JSON output structure including:
  ```json
  {
    "text": "some text",
    "start": 1.23,
    "duration": 4.56,
    "speaker": null,
    "confidence": null
  }

python3 download_transcript_formats.py "YOUTUBE_URL" --lang en
python3 download_transcript_formats.py "YOUTUBE_URL" --lang hi
python3 download_transcript_formats.py "YOUTUBE_URL" --lang de


python3 download_transcript_formats.py "YOUTUBE_URL" --format txt
python3 download_transcript_formats.py "YOUTUBE_URL" --format json
python3 download_transcript_formats.py "YOUTUBE_URL" --format srt
python3 download_transcript_formats.py "YOUTUBE_URL" --format vtt
python3 download_transcript_formats.py "YOUTUBE_URL" --format csv
python3 download_transcript_formats.py "YOUTUBE_URL" --format docx
python3 download_transcript_formats.py "YOUTUBE_URL" --format pdf


python3 download_transcript_formats.py "YOUTUBE_URL" --format json --output myfile.json


BATCH 

python3 download_transcript_formats.py \
  --batch jobs.csv \
  --outdir batch_results \
  --lang en \
  --zip


python3 download_transcript_formats.py --batch jobs.csv --outdir transcripts_out --zip


Your .csv should look like:
URL,format,outputfileName
https://youtu.be/abcd1234,json,podcast.json
https://youtube.com/watch?v=XYZ789,srt,episode1.srt
https://youtu.be/AABBCCDD,pdf,meeting.pdf
