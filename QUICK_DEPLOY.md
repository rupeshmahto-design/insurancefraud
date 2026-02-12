# 🚀 Deploy FraudShield AI to Railway

## Quick Deploy in 3 Steps

### Step 1: Push Code to GitHub ✅ (Your repo is ready!)

Your code is at: https://github.com/rupeshmahto-design/insurancefraud

If you need to update the code, run:

```powershell
cd C:\Users\INTEL\fraudshield-ai

# Initialize git (if not already done)
git init

# Add your GitHub repo
git remote add origin https://github.com/rupeshmahto-design/insurancefraud.git

# Stage all files
git add .

# Commit
git commit -m "Railway deployment ready - Enterprise UI with ML fraud detection"

# Push to GitHub
git push -u origin main
# If main doesn't work, try: git push -u origin master
```

---

### Step 2: Deploy on Railway 🚂

1. **Visit Railway:**
   - Go to https://railway.app
   - Click "Start a New Project"

2. **Connect GitHub:**
   - Click "Deploy from GitHub repo"
   - Sign in with GitHub
   - Select: **rupeshmahto-design/insurancefraud**

3. **Railway Auto-Detects:**
   - Sees Python project
   - Installs from `requirements.txt`
   - Uses `Procfile` for startup
   - Starts with Gunicorn

4. **Wait 2-3 minutes** for build to complete

---

### Step 3: Generate Domain 🌐

1. In Railway dashboard, click **"Settings"**
2. Click **"Generate Domain"**
3. Get your URL: `fraudshield-ai-production.up.railway.app`
4. **Done!** Share the link! 🎉

---

## 🔗 Your Live URLs

After deployment:

```
Main Page:     https://[your-domain].up.railway.app/
Demo:          https://[your-domain].up.railway.app/demo
Executive:     https://[your-domain].up.railway.app/executive
API Endpoint:  https://[your-domain].up.railway.app/api/analyze
```

---

## ✅ What's Deployed

- ✅ **Frontend**: All 3 interfaces (Main, Demo, Executive)
- ✅ **Backend**: Flask API with ML models
- ✅ **ML Models**: Random Forest + Isolation Forest
- ✅ **Database**: 5000 sample claims in SQLite
- ✅ **UI Features**: Toast notifications, activity feed, confidence gauge
- ✅ **Security**: HTTPS enabled automatically
- ✅ **Server**: Production Gunicorn (4 workers)

---

## 📊 Monitoring

In Railway dashboard:

- **Logs**: View real-time application logs
- **Metrics**: CPU, Memory, Network usage
- **Deployments**: Rollback if needed
- **Variables**: Add environment variables

---

## 💡 Tips

- **Free Tier**: $5 credit/month (enough for demos)
- **Auto-Deploy**: Push to GitHub → Railway auto-deploys
- **Custom Domain**: Add in Railway settings
- **Environment Variables**: Use for sensitive data

---

## 🎯 Next Steps

1. Push code to GitHub (commands above)
2. Deploy on Railway (3 clicks)
3. Share URL with team/clients
4. Enjoy 24/7 uptime! 🚀

**Total Time:** 5 minutes from start to deployed! ⚡
