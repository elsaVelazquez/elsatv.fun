# How to Get Real YouTube Thumbnails

The current solution uses placeholder images because:
1. ONCE cover art URLs require authentication and return 404
2. YouTube Data API requires an API key

## Option 1: YouTube Data API (Recommended)

1. Go to: https://console.developers.google.com/
2. Create a new project
3. Enable YouTube Data API v3
4. Create credentials (API key)
5. Add to your .env file:
   ```
   YOUTUBE_API_KEY=your_api_key_here
   ```

Then update the script to use the YouTube Data API to search for videos and get thumbnails.

## Option 2: Manual Upload

1. Create a `covers/` directory
2. Download album covers manually from YouTube
3. Name them: `album_title.jpg`
4. Update the script to use local files

## Option 3: Use a Different Placeholder Service

The current placeholders show album titles on green background. You can customize:
- Colors: Change `1a2b1a` (background) and `b8ff43` (text)
- Size: Change `300x300` to any size
- Text: Modify the title display

## Current Status

- ✅ 33 albums with correct titles
- ✅ Working YouTube Music links
- ✅ Placeholder images (reliable but not real artwork)
- ❌ Real album artwork (requires API key or manual work)

The placeholders are functional and look clean!
