# 🚀 Get Started - YouTube Release Sync

## Step 1: Get Your ONCE Token

1. Go to: https://beta.once.app/settings/api
2. Click **"Create token"**
3. Name it: `YouTube Release Sync`
4. Copy the token (starts with `once_pat_...`)

## Step 2: Set Your Token

```bash
# Replace 'your_token_here' with your actual token
export ONCE_PAT='once_pat_your_token_here'

# Test it
source venv/bin/activate && python quick_test.py
```

## Step 3: Run Your First Sync

```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Run the sync
python youtube_release_sync.py --mode fetch
```

## Step 4: Check the Results

```bash
# See if kissingface.html was updated
head -50 kissingface.html | grep -A 10 "const albums"
```

## 🔧 Troubleshooting

### "ONCE_PAT not set"

```bash
# Make sure you exported the token
export ONCE_PAT='your_token_here'

# Verify it's set
echo $ONCE_PAT
```

### "No releases found"

- You might not have any releases in ONCE yet
- Check your ONCE dashboard
- The script will still work when you add releases

### "Template not found"

- The script auto-creates it from your existing kissingface.html
- If it fails, manually copy kissingface.html to kissingface_template.html

## 🎯 What's Next?

Once local testing works:

1. **Set up cron job** for daily automation
2. **Push to GitHub** for GitHub Actions
3. **Set up webhooks** for real-time updates

## 💡 Pro Tips

- Always activate the virtual environment: `source venv/bin/activate`
- The script creates `kissingface_template.html` automatically
- Your original `kissingface.html` is backed up as a template
- You can run this as many times as you want - it's safe

## 🆘 Need Help?

Run the diagnostic:

```bash
source venv/bin/activate && python quick_test.py
```

This will tell you exactly what's missing!
