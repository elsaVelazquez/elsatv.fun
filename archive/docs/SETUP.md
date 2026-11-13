# YouTube Release Automation Setup

This system automates updating your `kissingface.html` music archive with new releases from ONCE Distribution.

## Quick Start

### 1. Get Your ONCE Personal Access Token

1. Go to https://beta.once.app/settings/api
2. Click "Create token"
3. Give it a name like "YouTube Release Sync"
4. Copy the token (starts with `once_pat_...`)

### 2. Set Environment Variable

```bash
export ONCE_PAT="once_pat_your_token_here"
```

### 3. Test the Script

```bash
# One-time fetch and update
python3 youtube_release_sync.py --mode fetch

# Test webhook mode (for real-time updates)
python3 youtube_release_sync.py --mode webhook --port 8080
```

### 4. Set Up Cron Job (Daily Sync)

```bash
# Edit your crontab
crontab -e

# Add this line to run daily at 2 AM
0 2 * * * cd /path/to/your/site && /usr/bin/python3 youtube_release_sync.py --mode cron >> sync.log 2>&1
```

### 5. Set Up Webhooks (Real-time Updates)

1. Install ngrok for local testing:

   ```bash
   brew install ngrok
   ngrok http 8080
   ```

2. Copy the ngrok URL (e.g., `https://abc123.ngrok.io`)

3. In ONCE settings, add webhook endpoint:
   - URL: `https://abc123.ngrok.io/webhook`
   - Events: `release.approved`, `release.status_changed`

4. Run the webhook server:
   ```bash
   python3 youtube_release_sync.py --mode webhook --port 8080
   ```

## Manual Trigger (Bypass YouTube Blocks)

If YouTube blocks automated requests, you can manually trigger updates:

```bash
# Create a simple trigger file
echo "manual_trigger" > .trigger_sync

# Add to your cron or run manually
python3 youtube_release_sync.py --mode fetch
```

## File Structure

- `youtube_release_sync.py` - Main automation script
- `kissingface_template.html` - Template with placeholder for album data
- `kissingface.html` - Generated output (auto-updated)
- `sync.log` - Cron job logs
- `.trigger_sync` - Manual trigger file

## How It Works

1. **ONCE API Integration**: Fetches release data using your Personal Access Token
2. **YouTube Extraction**: Parses YouTube video IDs and playlist IDs from release metadata
3. **Template System**: Uses a template file to generate updated HTML
4. **Multiple Modes**:
   - `fetch`: One-time sync
   - `webhook`: Real-time updates via ONCE webhooks
   - `cron`: Scheduled updates

## Customization

### Adding New Fields

Edit `YouTubeReleaseExtractor.extract_from_release()` to include more data:

```python
return {
    'title': release.get('title'),
    'date': release.get('release_date'),
    'video': youtube_data.get('video_id'),
    'list': youtube_data.get('playlist_id'),
    'artist': release.get('artist'),  # Add new fields
    'genre': release.get('genre'),
}
```

### Changing Update Frequency

Modify the cron schedule:

```bash
# Every 6 hours
0 */6 * * * cd /path/to/your/site && python3 youtube_release_sync.py --mode cron

# Every day at 9 AM
0 9 * * * cd /path/to/your/site && python3 youtube_release_sync.py --mode cron
```

## Troubleshooting

### "No releases found"

- Check your ONCE PAT is valid
- Verify releases exist in your ONCE dashboard
- Check the API response structure in `get_releases()`

### "Template not found"

- Run the script once to auto-create template from existing `kissingface.html`
- Or manually create `kissingface_template.html` with `{{ALBUMS_PLACEHOLDER}}`

### Webhook Not Working

- Ensure ngrok is running and URL is correct
- Check ONCE webhook configuration
- Verify server is listening on correct port

### YouTube Rate Limits

- Add delays between requests
- Use webhook mode instead of polling
- Consider caching release data locally

## Security Notes

- Never commit your ONCE PAT to version control
- Use environment variables for sensitive data
- Consider IP whitelisting for webhook endpoints
- Rotate PATs regularly

## Next Steps

1. **Add to CI/CD**: Include sync in your deployment pipeline
2. **Database Integration**: Store releases in a database instead of regenerating HTML
3. **Image Caching**: Download and cache album art locally
4. **Multi-platform**: Extend to sync with Spotify, Apple Music, etc.
5. **Analytics**: Track which releases get the most clicks

## Support

For ONCE API issues: tech@once.app
For script issues: Check the logs in `sync.log`
