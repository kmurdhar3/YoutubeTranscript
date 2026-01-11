# Google Cloud Run Deployment Guide

## Prerequisites
1. Install Google Cloud CLI: https://cloud.google.com/sdk/docs/install
2. Have a Google Cloud account with billing enabled
3. Create a new project (or use existing one)

## Files You Need
Place these files in the same directory:
- `simple_api_caller_async_download.py` (your API file)
- `requirements.txt`
- `Dockerfile`
- `.dockerignore` (optional but recommended)

## Deployment Steps

### 1. Authenticate with Google Cloud
```bash
gcloud auth login
```

### 2. Set Your Project
```bash
# List your projects
gcloud projects list

# Set your project ID
gcloud config set project YOUR_PROJECT_ID
```

### 3. Enable Required APIs
```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### 4. Deploy to Cloud Run
```bash
gcloud run deploy brightdata-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 600 \
  --max-instances 10
```

**Explanation of flags:**
- `--source .` - Deploy from current directory
- `--region us-central1` - Choose your preferred region
- `--allow-unauthenticated` - Make API publicly accessible
- `--memory 1Gi` - Allocate 1GB RAM (adjust if needed)
- `--cpu 1` - Allocate 1 CPU
- `--timeout 600` - 10 minute timeout (for long-running requests)
- `--max-instances 10` - Maximum concurrent instances

### 5. Get Your API URL
After deployment, Cloud Run will provide a URL like:
```
https://brightdata-api-xxxxxxxxxx-uc.a.run.app
```

## Testing Your API

Test the health endpoint:
```bash
curl https://YOUR_CLOUD_RUN_URL/health
```

Test the home endpoint:
```bash
curl https://YOUR_CLOUD_RUN_URL/
```

Test transcription:
```bash
curl -X POST https://YOUR_CLOUD_RUN_URL/transcribe \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtu.be/VIDEO_ID"}'
```

## Environment Variables (Optional)

If you need to change the API token without rebuilding:

```bash
gcloud run deploy brightdata-api \
  --update-env-vars API_TOKEN=your_new_token
```

## Monitoring & Logs

View logs:
```bash
gcloud run logs read brightdata-api --limit 50
```

View in Cloud Console:
```
https://console.cloud.google.com/run
```

## Cost Optimization

Cloud Run pricing:
- Free tier: 2M requests/month
- Pay-per-use after that
- Scales to zero when not in use (no cost when idle)

To reduce costs:
- Set `--min-instances 0` (default, scales to zero)
- Use `--cpu 1` and `--memory 512Mi` if sufficient
- Set appropriate `--max-instances` to prevent runaway costs

## Updating Your API

Simply redeploy with the same command:
```bash
gcloud run deploy brightdata-api --source .
```

## Common Issues

**Issue: Timeout errors**
Solution: Increase timeout (max 3600 seconds):
```bash
gcloud run deploy brightdata-api --timeout 900
```

**Issue: Memory errors**
Solution: Increase memory:
```bash
gcloud run deploy brightdata-api --memory 2Gi
```

**Issue: Cold start latency**
Solution: Keep minimum instances warm:
```bash
gcloud run deploy brightdata-api --min-instances 1
```
(Note: This will incur costs even when idle)

## Security Best Practices

1. **Don't hardcode API tokens** - Use environment variables or Secret Manager
2. **Add authentication** if your API should not be public
3. **Set up CORS properly** for your specific domains
4. **Monitor usage** to detect abuse

## Secret Manager (Recommended for API Token)

Instead of hardcoding your Bright Data token:

1. Create a secret:
```bash
echo -n "YOUR_API_TOKEN" | gcloud secrets create brightdata-token --data-file=-
```

2. Deploy with secret:
```bash
gcloud run deploy brightdata-api \
  --source . \
  --set-secrets=API_TOKEN=brightdata-token:latest
```

3. Update your Python code to read from environment:
```python
import os
API_TOKEN = os.environ.get('API_TOKEN', 'fallback_token')
```

## Alternative: Deploy from Container Registry

If you prefer building locally:

```bash
# Build the image
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/brightdata-api

# Deploy from registry
gcloud run deploy brightdata-api \
  --image gcr.io/YOUR_PROJECT_ID/brightdata-api \
  --region us-central1 \
  --allow-unauthenticated
```

## Need Help?
- Cloud Run docs: https://cloud.google.com/run/docs
- Pricing calculator: https://cloud.google.com/products/calculator
- Community: https://stackoverflow.com/questions/tagged/google-cloud-run
