# FraudShield AI - Database Viewer Guide

## How to Show Database to Clients

Your FraudShield AI application now has a comprehensive **Database Viewer** that allows clients to explore all the data in your system.

### 🌐 Access Methods

#### **Option 1: Web Browser (Recommended for Clients)**

1. **Start the application:**
   ```bash
   .\venv\Scripts\Activate.ps1
   python app.py
   ```

2. **Open in browser:**
   - Main App: http://localhost:5000
   - Database Viewer: http://localhost:5000/database.html

3. **Click the "🗄️ View Database" button** on the main page

### 📊 Available Views

The Database Viewer provides 5 interactive sections:

#### 1. **📊 Dashboard**
- Total claims count
- Fraud detection rate
- Provider statistics
- Decision analytics
- Fraud breakdown by type

#### 2. **📋 All Claims** 
- View all healthcare claims
- Filter by limit (50, 100, 500, 1000 records)
- See claim details: ID, provider, CPT code, amount, status
- Export to CSV

#### 3. **👨‍⚕️ Providers**
- View all healthcare providers
- Provider profiles with specialty, license status
- Risk flags and fraud history
- Average claim amounts
- Export to CSV

#### 4. **✅ Decisions**
- AI-generated fraud detection decisions
- Risk scores and classifications
- Timestamp tracking
- Decision history
- Export to CSV

#### 5. **🚨 Fraud Only**
- Filtered view of fraudulent claims
- Fraud type classification
- High-risk indicators
- Export to CSV

### 🔌 API Endpoints (for Developers)

If your client needs programmatic access:

```
GET /api/database-summary       # Overall database statistics
GET /api/claims?limit=100       # Get claims data
GET /api/claims?fraud_only=true # Get only fraudulent claims
GET /api/providers              # Get provider information
GET /api/decisions?limit=50     # Get recent decisions
```

**Example API Call:**
```bash
curl http://localhost:5000/api/database-summary
```

### 📥 Export Features

Each view includes a **"📥 Export CSV"** button that allows clients to:
- Download data for analysis
- Import into Excel/Google Sheets
- Create custom reports
- Share data with stakeholders

### 🗄️ Database Access Tools (Alternative)

For direct database access, you can use:

#### **DB Browser for SQLite** (Free Tool)
1. Download: https://sqlitebrowser.org/
2. Open file: `data/fraud_detection.db`
3. Browse all tables: providers, claims, claim_decisions

#### **DBeaver** (Universal Database Tool)
1. Download: https://dbeaver.io/
2. Connect to SQLite database
3. Full SQL query capabilities

### 📋 Database Schema

**Providers Table:**
- provider_id, provider_name, specialty, state
- tenure_years, license_status, past_fraud_flags
- avg_claim_amount, claims_per_month

**Claims Table:**
- claim_id, provider_id, patient_id
- service_date, submission_date, cpt_code
- claim_amount, units, patient_age
- is_fraud, fraud_type, days_to_submit

**Claim Decisions Table:**
- decision_id, claim_id, risk_score
- decision, fraud_probability, anomaly_score
- rule_violations, created_at

### 🎯 Client Presentation Tips

1. **Start with Dashboard** - Shows overall system performance
2. **Demo Fraud Detection** - Show fraud claims vs. legitimate
3. **Highlight Export** - Demonstrate CSV download capability
4. **Show Real-time Updates** - Analyze claims and see decisions saved
5. **Discuss Scalability** - Can handle thousands of claims

### 🚀 Production Deployment

For client deployment, consider:

1. **Replace SQLite** with PostgreSQL/MySQL for production
2. **Add authentication** for secure access
3. **Deploy on cloud** (AWS, Azure, Google Cloud)
4. **Add role-based access** for different user types
5. **Implement audit logging** for compliance

### 📞 Support

For issues or questions:
- Check that Flask server is running on port 5000
- Ensure database exists at `data/fraud_detection.db`
- Verify all dependencies are installed
- Check browser console for JavaScript errors
