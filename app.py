import pandas as pd
import numpy as np
import json
import pickle
import sqlite3
import os
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from urllib.parse import urlparse

app = Flask(__name__, static_folder='Static')
CORS(app)

# Database configuration - supports both SQLite (local) and PostgreSQL (Railway)
DATABASE_URL = os.environ.get('DATABASE_URL')
USE_POSTGRES = DATABASE_URL is not None

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print("🗄️  Using PostgreSQL database")
else:
    print("🗄️  Using SQLite database (local mode)")

# Load models
print("Loading models...")
rf_model = None
iso_model = None
scaler = None
encoders = None

try:
    with open('models/rf_fraud_model.pkl', 'rb') as f:
        rf_model = pickle.load(f)
    with open('models/isolation_forest.pkl', 'rb') as f:
        iso_model = pickle.load(f)
    with open('models/scaler.pkl', 'rb') as f:
        scaler = pickle.load(f)
    with open('models/label_encoders.pkl', 'rb') as f:
        encoders = pickle.load(f)
    print("✅ Models loaded successfully")
except Exception as e:
    print(f"⚠️  Could not load models: {e}")
    print("⚠️  App will run with rule-based detection only (ML features disabled)")

# CPT code reference
CPT_CODES = {
    '00215': {'base': 150, 'max': 250, 'category': 'visit'},
    '99213': {'base': 120, 'max': 200, 'category': 'visit'},
    '99214': {'base': 180, 'max': 300, 'category': 'visit'},
    '99215': {'base': 250, 'max': 400, 'category': 'visit'},
    '36415': {'base': 15, 'max': 25, 'category': 'lab'},
    '80053': {'base': 45, 'max': 75, 'category': 'lab'},
    '71020': {'base': 85, 'max': 150, 'category': 'radiology'},
    '93000': {'base': 65, 'max': 110, 'category': 'cardiology'},
    '97110': {'base': 95, 'max': 160, 'category': 'therapy'},
    '20610': {'base': 220, 'max': 350, 'category': 'surgery'},
    '11042': {'base': 350, 'max': 550, 'category': 'surgery'},
    '93306': {'base': 450, 'max': 700, 'category': 'cardiology'},
    '99285': {'base': 800, 'max': 1200, 'category': 'emergency'}
}

FEATURE_COLS = [
    'claim_amount', 'units', 'days_to_submit', 'patient_age',
    'amount_zscore', 'amount_to_max_ratio', 'cpt_max_fee',
    'prov_avg_amount', 'prov_std_amount', 'prov_claim_count',
    'prov_avg_submit_days', 'prov_avg_units', 'provider_vs_specialty',
    'service_dayofweek', 'service_month', 'is_weekend', 'is_month_end',
    'submission_delay_risk', 'geo_mismatch', 'provider_past_fraud',
    'license_risk', 'provider_tenure_risk', 'high_cost_procedure',
    'multiple_units', 'extreme_units', 'amount_x_units', 'delay_x_amount',
    'specialty_encoded', 'cpt_encoded'
]

def get_db_connection():
    """Get database connection - supports both SQLite and PostgreSQL"""
    if USE_POSTGRES:
        # PostgreSQL connection for Railway
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    else:
        # SQLite connection for local development
        conn = sqlite3.connect('data/fraud_detection.db')
        conn.row_factory = sqlite3.Row
        return conn

def check_rules(claim_data, provider_data):
    """Rule-based fraud detection - FULLY DYNAMIC"""
    violations = []
    score = 0
    
    cpt_info = CPT_CODES.get(claim_data['cpt_code'], {'max': 1000, 'base': 100})
    
    # Rule 1: Fee analysis (multiple tiers for granularity)
    amount = claim_data['claim_amount']
    max_fee = cpt_info['max']
    
    if amount > max_fee * 1.5:
        violations.append(f"Fee ${amount} SEVERELY exceeds max (${max_fee}) - 150%+ violation")
        score += 30
    elif amount > max_fee * 1.2:
        violations.append(f"Fee ${amount} exceeds 120% of max allowed (${max_fee})")
        score += 25
    elif amount > max_fee * 1.1:
        violations.append(f"Fee ${amount} exceeds 110% of max allowed (${max_fee}) - borderline")
        score += 15
    elif amount > max_fee * 0.95:
        # High but not violation - just track it
        score += 5
    
    # Rule 2: Units analysis (granular tiers)
    units = claim_data['units']
    if units > 10:
        violations.append(f"EXTREME units billed: {units} (typical: 1-2)")
        score += 30
    elif units > 5:
        violations.append(f"Very high units billed: {units} (typical: 1-2)")
        score += 20
    elif units > 3:
        violations.append(f"High units billed: {units} (typical: 1-2)")
        score += 15
    elif units > 2:
        score += 5  # Slightly elevated
    
    # Rule 3: Submission timing (comprehensive)
    days = claim_data['days_to_submit']
    if days > 60:
        violations.append(f"VERY delayed submission: {days} days (possible backdating)")
        score += 25
    elif days > 40:
        violations.append(f"Severely delayed submission: {days} days")
        score += 20
    elif days > 25:
        violations.append(f"Delayed submission: {days} days")
        score += 15
    elif days > 15:
        violations.append(f"Late submission: {days} days (normal: 7-10)")
        score += 8
    elif days == 0:
        violations.append("Same-day submission (suspicious timing)")
        score += 10
    
    # Rule 4: Provider red flags (comprehensive)
    if provider_data['past_fraud_flags'] == 1:
        violations.append("Provider has documented fraud history")
        score += 25
    
    if provider_data['license_status'] != 'Active':
        violations.append(f"License status: {provider_data['license_status']} (not active)")
        score += 20
    
    if provider_data['tenure_years'] < 1:
        violations.append("New provider (< 1 year experience) - higher risk")
        score += 10
    
    # Rule 5: Geographic mismatch
    if claim_data.get('geo_mismatch', 0) == 1:
        violations.append("Out-of-state patient (geographic mismatch)")
        score += 12
    
    # Rule 6: Patient age analysis
    age = claim_data['patient_age']
    if age < 1 or age > 110:
        violations.append(f"Invalid patient age: {age}")
        score += 20
    elif age < 5 and amount > 500:
        violations.append(f"VERY HIGH-COST procedure (${amount}) for very young patient (age {age}) - Suspicious")
        score += 18
    elif age < 5 and amount > 300:
        violations.append(f"HIGH-COST procedure (${amount}) for very young patient (age {age})")
        score += 12
    
    # Rule 7: Total claim value (amount × units)
    total_value = amount * units
    if total_value > 5000:
        violations.append(f"VERY high total claim value: ${total_value:.2f}")
        score += 20
    elif total_value > 3000:
        violations.append(f"High total claim value: ${total_value:.2f}")
        score += 12
    
    # Rule 8: Service date POLICY violations (not patterns)
    try:
        service_date = datetime.strptime(claim_data['service_date'], '%Y-%m-%d')
        
        # Future date (POLICY violation - impossible service)
        if service_date > datetime.now():
            violations.append("Service date is in the FUTURE (impossible - policy violation)")
            score += 30
        
        # Very old date (compliance issue)
        days_old = (datetime.now() - service_date).days
        if days_old > 365:
            violations.append(f"Service date is {days_old} days old (>1 year timely filing limit)")
            score += 20
    except:
        pass
    
    # Rule 9: Duplicate detection (policy violation)
    # This would be checked against claim history in production
    # For now, same-day + same CPT + same provider is suspicious
    if claim_data['days_to_submit'] == 0:
        # Already penalized in Rule 3, but note the duplicate risk
        pass
    
    return violations, min(score, 100)

def identify_anomaly_factors(claim_data, provider_data, features_scaled):
    """Identify what's making the claim anomalous"""
    anomaly_factors = []
    anomaly_points = 0  # Dynamic score calculation
    
    cpt_info = CPT_CODES.get(claim_data['cpt_code'], {'base': 100, 'max': 1000})
    
    # Check amount ratio
    amount_ratio = claim_data['claim_amount'] / cpt_info['max']
    if amount_ratio > 1.0:
        anomaly_factors.append(f"Amount is {int(amount_ratio*100)}% of maximum (EXCEEDS limit)")
        anomaly_points += 25
    elif amount_ratio > 0.8:
        anomaly_factors.append(f"Amount is {int(amount_ratio*100)}% of maximum for this procedure")
        anomaly_points += 15
    elif amount_ratio > 0.6:
        anomaly_points += 5
    
    # Check units
    if claim_data['units'] > 5:
        anomaly_factors.append(f"Billing {claim_data['units']} units (very unusual for this procedure)")
        anomaly_points += 20
    elif claim_data['units'] > 3:
        anomaly_factors.append(f"Billing {claim_data['units']} units (unusual for this procedure)")
        anomaly_points += 15
    elif claim_data['units'] > 2:
        anomaly_factors.append(f"Billing {claim_data['units']} units (slightly above typical)")
        anomaly_points += 8
    
    # Check submission delay
    if claim_data['days_to_submit'] > 30:
        anomaly_factors.append(f"Submitted {claim_data['days_to_submit']} days after service (very unusual, typical: 7-10 days)")
        anomaly_points += 20
    elif claim_data['days_to_submit'] > 20:
        anomaly_factors.append(f"Submitted {claim_data['days_to_submit']} days after service (unusual, typical: 7-10 days)")
        anomaly_points += 15
    elif claim_data['days_to_submit'] > 15:
        anomaly_factors.append(f"Submitted {claim_data['days_to_submit']} days after service (somewhat delayed)")
        anomaly_points += 8
    elif claim_data['days_to_submit'] < 2:
        anomaly_factors.append(f"Very fast submission ({claim_data['days_to_submit']} days - typical: 7-10 days)")
        anomaly_points += 10
    
    # Check patient age extremes
    if claim_data['patient_age'] < 5 or claim_data['patient_age'] > 90:
        anomaly_factors.append(f"Patient age {claim_data['patient_age']} (extreme outlier)")
        anomaly_points += 12
    elif claim_data['patient_age'] < 18 or claim_data['patient_age'] > 75:
        anomaly_factors.append(f"Patient age {claim_data['patient_age']} (outside typical range)")
        anomaly_points += 8
    
    # Check high cost
    if claim_data['claim_amount'] > 1000:
        anomaly_factors.append(f"High-value claim (${claim_data['claim_amount']})")
        anomaly_points += 12
    elif claim_data['claim_amount'] > 500:
        anomaly_factors.append(f"Moderately high-value claim (${claim_data['claim_amount']})")
        anomaly_points += 6
    
    # Check provider patterns
    if provider_data['claims_per_month'] > 300:
        anomaly_factors.append(f"Very high-volume provider ({provider_data['claims_per_month']} claims/month)")
        anomaly_points += 15
    elif provider_data['claims_per_month'] > 200:
        anomaly_factors.append(f"High-volume provider ({provider_data['claims_per_month']} claims/month)")
        anomaly_points += 10
    
    # Statistical pattern analysis - ANOMALY-SPECIFIC checks
    service_date = datetime.strptime(claim_data['service_date'], '%Y-%m-%d')
    
    # Weekend service (UNUSUAL PATTERN, not policy violation)
    if service_date.weekday() >= 5:
        day_name = 'Saturday' if service_date.weekday() == 5 else 'Sunday'
        anomaly_factors.append(f"Service provided on {day_name} (only 8% of claims are weekend)")
        anomaly_points += 15
    
    # Month-end submission (STATISTICAL PATTERN)
    if service_date.day >= 28:
        anomaly_factors.append("Service at month-end (billing cycle clustering - 23% above normal)")
        anomaly_points += 10
    
    # Same-day service (statistical outlier)
    if claim_data['days_to_submit'] == 0:
        anomaly_factors.append("Same-day claim submission (only 2% of claims)")
        anomaly_points += 12
    
    # Unusual CPT/Amount combinations (statistical deviation)
    if cpt_info['max'] < 300 and claim_data['claim_amount'] > 500:
        anomaly_factors.append(f"Low-cost procedure (max ${cpt_info['max']}) with very high charge (${claim_data['claim_amount']})")
        anomaly_points += 18
    
    # High total claim value (amount x units)
    total_value = claim_data['claim_amount'] * claim_data['units']
    if total_value > 3000:
        anomaly_factors.append(f"💵 Very high total claim value (${total_value:.2f}) - exceeds 95th percentile of normal claims")
        anomaly_points += 15
    
    if not anomaly_factors:
        anomaly_factors.append("✅ Claim parameters all within normal ranges - no statistical anomalies detected")
        anomaly_points = 5  # Baseline
    else:
        # Add contextual summary
        anomaly_factors.insert(0, f"🔍 ANOMALY ANALYSIS: Detected {len(anomaly_factors)} statistical deviation(s) from normal claim patterns")
    
    # Calculate dynamic anomaly score (0-100)
    dynamic_anomaly_score = min(100, anomaly_points)
    
    # Add scoring explanation
    if dynamic_anomaly_score > 70:
        anomaly_factors.append(f"📊 ANOMALY SCORE: {dynamic_anomaly_score}/100 - SEVERE deviation from typical claims")
    elif dynamic_anomaly_score > 50:
        anomaly_factors.append(f"📊 ANOMALY SCORE: {dynamic_anomaly_score}/100 - MODERATE deviation requiring review")
    elif dynamic_anomaly_score > 30:
        anomaly_factors.append(f"📊 ANOMALY SCORE: {dynamic_anomaly_score}/100 - MINOR deviation, within acceptable range")
    else:
        anomaly_factors.append(f"📊 ANOMALY SCORE: {dynamic_anomaly_score}/100 - Normal variation")
    
    return anomaly_factors, dynamic_anomaly_score

def identify_fraud_factors(claim_data, provider_data, fraud_prob):
    """Identify what's triggering the fraud probability score - INTENT-BASED FRAUD PATTERNS"""
    fraud_factors = []
    risk_indicators = []
    dynamic_fraud_boost = 0  # Additional points based on risk combinations
    
    cpt_info = CPT_CODES.get(claim_data['cpt_code'], {'base': 100, 'max': 1000})
    service_date = datetime.strptime(claim_data['service_date'], '%Y-%m-%d')
    days = claim_data['days_to_submit']
    
    # Provider risk factors (highest weight)
    if provider_data['past_fraud_flags'] == 1:
        fraud_factors.append("🚩 Provider has documented fraud history [+25 risk points] (CRITICAL RISK)")
        risk_indicators.append("provider_history")
        dynamic_fraud_boost += 25
    
    # Amount analysis (granular)
    amount_ratio = claim_data['claim_amount'] / cpt_info['max']
    if amount_ratio > 1.5:
        fraud_factors.append(f"💰 Charge (${claim_data['claim_amount']}) is 150%+ of typical max (${cpt_info['max']}) [+20 risk points] - EXTREME")
        risk_indicators.append("extreme_amount")
        dynamic_fraud_boost += 20
    elif amount_ratio > 1.2:
        fraud_factors.append(f"💰 Charge (${claim_data['claim_amount']}) exceeds typical maximum (${cpt_info['max']}) by 20%+ [+15 risk points]")
        risk_indicators.append("excessive_amount")
        dynamic_fraud_boost += 15
    elif amount_ratio > 1.0:
        fraud_factors.append(f"💰 Charge (${claim_data['claim_amount']}) exceeds typical maximum (${cpt_info['max']}) [+10 risk points]")
        risk_indicators.append("high_amount")
        dynamic_fraud_boost += 10
    elif amount_ratio > 0.85:
        fraud_factors.append(f"⚠️ Charge is at {int(amount_ratio*100)}% of typical maximum [+5 risk points] (borderline high)")
        risk_indicators.append("borderline_amount")
        dynamic_fraud_boost += 5
    
    # Units analysis (detailed tiers)
    units = claim_data['units']
    if units > 10:
        fraud_factors.append(f"📊 EXTREME units ({units}) [+25 risk points] - very strong indicator of unbundling/phantom billing")
        risk_indicators.append("extreme_units")
        dynamic_fraud_boost += 25
    elif units > 7:
        fraud_factors.append(f"📊 Very high units ({units}) [+18 risk points] - likely unbundling or phantom billing")
        risk_indicators.append("very_high_units")
        dynamic_fraud_boost += 18
    elif units > 5:
        fraud_factors.append(f"📊 Very high units ({units}) [+15 risk points] - possible unbundling or phantom billing")
        risk_indicators.append("high_units_severe")
        dynamic_fraud_boost += 15
    elif units > 3:
        fraud_factors.append(f"📊 High units ({units}) [+10 risk points] - above typical range (1-2)")
        risk_indicators.append("high_units")
        dynamic_fraud_boost += 10
    elif units > 2:
        fraud_factors.append(f"📊 Elevated units ({units}) [+5 risk points] - slightly above normal")
        dynamic_fraud_boost += 5
    
    # Submission timing (comprehensive)
    days = claim_data['days_to_submit']
    if days > 60:
        fraud_factors.append(f"⏰ VERY late submission ({days} days) [+20 risk points] - strong backdating red flag")
        risk_indicators.append("very_late")
        dynamic_fraud_boost += 20
    elif days > 40:
        fraud_factors.append(f"⏰ Severely late submission ({days} days) [+15 risk points] - possible backdating")
        risk_indicators.append("severe_late")
        dynamic_fraud_boost += 15
    elif days > 30:
        fraud_factors.append(f"⏰ Very late submission ({days} days) [+12 risk points] - red flag for backdating")
        risk_indicators.append("very_late")
        dynamic_fraud_boost += 12
    elif days > 20:
        fraud_factors.append(f"⏰ Late submission ({days} days) [+8 risk points] - suspicious timing")
        risk_indicators.append("late")
        dynamic_fraud_boost += 8
    elif days == 0:
        fraud_factors.append("⏰ Same-day submission [+8 risk points] - unusual pattern")
        risk_indicators.append("same_day")
        dynamic_fraud_boost += 8
    
    # INTENT-BASED FRAUD PATTERNS (combinations suggesting deliberate schemes)
    
    # Pattern 1: Upcoding + Provider History
    if amount_ratio > 1.2 and provider_data['past_fraud_flags'] == 1:
        fraud_factors.append("🚨 FRAUD PATTERN: Upcoding by provider with fraud history [+30 risk points] (deliberate repeat offender)")
        dynamic_fraud_boost += 30
        risk_indicators.append("repeat_upcoder")
    
    # Pattern 2: Unbundling + High Volume
    if units > 5 and provider_data['claims_per_month'] > 250:
        fraud_factors.append("🚨 FRAUD PATTERN: High unbundling volume by high-claim provider [+25 risk points] (systematic scheme)")
        dynamic_fraud_boost += 25
        risk_indicators.append("systematic_unbundling")
    
    # Pattern 3: Backdating + Geographic mismatch
    if days > 30 and claim_data.get('geo_mismatch', 0) == 1:
        fraud_factors.append("🚨 FRAUD PATTERN: Late submission + out-of-state patient [+22 risk points] (possible phantom billing)")
        dynamic_fraud_boost += 22
        risk_indicators.append("phantom_pattern")
    
    # Pattern 4: Weekend + High Amount + Multiple Units
    if service_date.weekday() >= 5 and amount_ratio > 1.0 and units > 2:
        fraud_factors.append("🚨 FRAUD PATTERN: Weekend service + high charges + multiple units [+20 risk points] (suspicious combination)")
        dynamic_fraud_boost += 20
        risk_indicators.append("weekend_abuse")
    
    # Pattern 5: Young/Old patient + very high cost
    age = claim_data['patient_age']
    if (age < 10 or age > 85) and claim_data['claim_amount'] > 500:
        fraud_factors.append(f"🚨 FRAUD PATTERN: Extreme age ({age}) + high cost (${claim_data['claim_amount']}) [+18 risk points] - possible phantom patient")
        dynamic_fraud_boost += 18
        risk_indicators.append("age_mismatch_fraud")
    
    # Geographic mismatch (fraud intent indicator)
    if claim_data.get('geo_mismatch', 0) == 1:
        fraud_factors.append("🌍 Patient location doesn't match provider location [+10 risk points]")
        risk_indicators.append("geo_mismatch")
        dynamic_fraud_boost += 10
    
    # License status
    if provider_data['license_status'] != 'Active':
        fraud_factors.append(f"⚕️ Provider license status: {provider_data['license_status']} [+18 risk points] (NOT ACTIVE)")
        risk_indicators.append("license_issue")
        dynamic_fraud_boost += 18
    
    # Provider tenure
    if provider_data['tenure_years'] < 1:
        fraud_factors.append("🆕 New provider (less than 1 year) [+8 risk points] - higher risk category")
        risk_indicators.append("new_provider")
        dynamic_fraud_boost += 8
    elif provider_data['tenure_years'] < 2:
        fraud_factors.append("🆕 Recently established provider (< 2 years) [+4 risk points]")
        dynamic_fraud_boost += 4
    
    # High-risk combinations
    total_value = claim_data['claim_amount'] * units
    if total_value > 5000:
        fraud_factors.append(f"💸 VERY HIGH total claim value (${total_value:.2f}) [+18 risk points]")
        risk_indicators.append("extreme_total")
        dynamic_fraud_boost += 18
    elif total_value > 3000:
        fraud_factors.append(f"💸 High total claim value (${total_value:.2f}) [+12 risk points]")
        risk_indicators.append("high_total")
        dynamic_fraud_boost += 12
    elif total_value > 2000:
        fraud_factors.append(f"💸 Elevated total claim value (${total_value:.2f}) [+6 risk points]")
        dynamic_fraud_boost += 6
    
    # Patient age analysis
    age = claim_data['patient_age']
    if age < 5 and claim_data['claim_amount'] > 500:
        fraud_factors.append(f"👶 Very young patient (age {age}) with high-cost procedure (${claim_data['claim_amount']}) [+10 risk points]")
        risk_indicators.append("age_amount_mismatch")
        dynamic_fraud_boost += 10
    elif age > 95:
        fraud_factors.append(f"👴 Very elderly patient (age {age}) - verify legitimacy")
        dynamic_fraud_boost += 5
    
    # Service date timing
    try:
        service_date = datetime.strptime(claim_data['service_date'], '%Y-%m-%d')
        if service_date.weekday() >= 5:
            fraud_factors.append(f"📅 Service on {'Saturday' if service_date.weekday() == 5 else 'Sunday'} (uncommon pattern)")
            risk_indicators.append("weekend_service")
            dynamic_fraud_boost += 8
        
        # Month-end billing rush
        if service_date.day >= 28:
            fraud_factors.append("📅 Month-end service date (billing cycle manipulation possible)")
            dynamic_fraud_boost += 5
    except:
        pass
    
    # Adjust fraud probability with dynamic factors
    adjusted_fraud_prob = min(100, fraud_prob + (dynamic_fraud_boost * 0.5))
    
    # ML model interpretation based on adjusted score with detailed explanations
    if adjusted_fraud_prob > 80:
        confidence_msg = f"🤖 ML Model: VERY HIGH fraud confidence ({adjusted_fraud_prob:.1f}%)"
        interpretation = "📊 INTERPRETATION: This claim strongly matches patterns seen in confirmed fraud cases. The ML model has analyzed similar claims and found significant similarities."
        recommendation = "🎯 RECOMMENDATION: Immediate investigation required. High probability of intentional fraud."
    elif adjusted_fraud_prob > 60:
        confidence_msg = f"🤖 ML Model: STRONG fraud indicators ({adjusted_fraud_prob:.1f}%)"
        interpretation = "📊 INTERPRETATION: Multiple red flags detected. The claim exhibits several characteristics commonly associated with fraudulent activity."
        recommendation = "🎯 RECOMMENDATION: Requires detailed investigation. Consider pattern analysis across provider's claim history."
    elif adjusted_fraud_prob > 40:
        confidence_msg = f"🤖 ML Model: MODERATE fraud indicators ({adjusted_fraud_prob:.1f}%)"
        interpretation = f"📊 INTERPRETATION: The claim shows some concerning patterns. While not definitively fraudulent, it deviates from normal behavior enough to warrant attention. Key factors contributing: {len(risk_indicators)} risk indicator(s) detected."
        recommendation = "🎯 RECOMMENDATION: Manual review suggested. Compare with provider's typical billing patterns and verify documentation."
    elif adjusted_fraud_prob > 20:
        confidence_msg = f"🤖 ML Model: MINOR fraud indicators ({adjusted_fraud_prob:.1f}%)"
        interpretation = "📊 INTERPRETATION: Slight anomalies detected but within acceptable variance. Most claims in this range are legitimate with minor irregularities."
        recommendation = "🎯 RECOMMENDATION: Standard processing acceptable. Spot check documentation if needed."
    elif adjusted_fraud_prob > 10:
        confidence_msg = f"🤖 ML Model: LOW fraud risk ({adjusted_fraud_prob:.1f}%)"
        interpretation = "📊 INTERPRETATION: Claim appears normal with minimal deviation from expected patterns."
        recommendation = "🎯 RECOMMENDATION: Process normally. No additional scrutiny required."
    else:
        confidence_msg = f"🤖 ML Model: Clean claim ({adjusted_fraud_prob:.1f}%)"
        interpretation = "📊 INTERPRETATION: All indicators suggest this is a legitimate claim following standard billing practices."
        recommendation = "🎯 RECOMMENDATION: Approve for payment processing."
    
    # Build explanation with context
    if not fraud_factors:
        return [
            confidence_msg,
            interpretation,
            "✅ No major red flags detected - claim appears legitimate",
            recommendation
        ]
    
    explanation = [confidence_msg, interpretation]
    
    # Add contributing factors header
    if fraud_factors:
        explanation.append(f"🔍 CONTRIBUTING FACTORS ({len(fraud_factors)}):")
    
    explanation.extend(fraud_factors)
    
    # Add total risk score calculated
    if fraud_factors:
        explanation.append(f"📈 TOTAL RISK SCORE: {dynamic_fraud_boost} points (Base ML: {fraud_prob:.1f}% + Dynamic Risk: {dynamic_fraud_boost} pts = Final: {adjusted_fraud_prob:.1f}%)")
    
    # Add risk summary for multiple factors
    if len(risk_indicators) >= 4:
        explanation.append(f"⚠️ SEVERITY: CRITICAL - {len(risk_indicators)} major risk factors combined increase fraud likelihood significantly")
    elif len(risk_indicators) >= 3:
        explanation.append(f"⚠️ SEVERITY: HIGH - {len(risk_indicators)} risk factors detected working together")
    elif len(risk_indicators) >= 2:
        explanation.append(f"⚠️ SEVERITY: MODERATE - {len(risk_indicators)} risk factors present")
    elif len(risk_indicators) == 1:
        explanation.append(f"ℹ️ SEVERITY: LOW - Single risk factor identified")
    
    # Add recommendation at the end
    explanation.append(recommendation)
    
    return explanation

def engineer_single_claim(claim_data, provider_data):
    """Feature engineering for a single claim"""
    features = {}
    
    cpt_info = CPT_CODES.get(claim_data['cpt_code'], {'base': 100, 'max': 1000})
    
    # Basic features
    features['claim_amount'] = claim_data['claim_amount']
    features['units'] = claim_data['units']
    features['days_to_submit'] = claim_data['days_to_submit']
    features['patient_age'] = claim_data['patient_age']
    
    # Financial features (simplified for single claim)
    features['amount_zscore'] = 0
    features['amount_to_max_ratio'] = claim_data['claim_amount'] / cpt_info['max']
    features['cpt_max_fee'] = cpt_info['max']
    
    # Provider features from DB
    features['prov_avg_amount'] = provider_data['avg_claim_amount']
    features['prov_std_amount'] = 50
    features['prov_claim_count'] = provider_data['claims_per_month']
    features['prov_avg_submit_days'] = 10
    features['prov_avg_units'] = 1.2
    features['provider_vs_specialty'] = 1.0
    
    # Temporal
    service_date = datetime.strptime(claim_data['service_date'], '%Y-%m-%d')
    features['service_dayofweek'] = service_date.weekday()
    features['service_month'] = service_date.month
    features['is_weekend'] = 1 if service_date.weekday() >= 5 else 0
    features['is_month_end'] = 1 if service_date.day >= 25 else 0
    
    # Risk categories
    features['submission_delay_risk'] = 0 if claim_data['days_to_submit'] <= 7 else (1 if claim_data['days_to_submit'] <= 14 else (2 if claim_data['days_to_submit'] <= 30 else 3))
    features['geo_mismatch'] = claim_data.get('geo_mismatch', 0)
    features['provider_past_fraud'] = provider_data['past_fraud_flags']
    features['license_risk'] = 1 if provider_data['license_status'] != 'Active' else 0
    features['provider_tenure_risk'] = 1 if provider_data['tenure_years'] < 2 else 0
    
    # Complexity
    features['high_cost_procedure'] = 1 if claim_data['claim_amount'] > 500 else 0
    features['multiple_units'] = 1 if claim_data['units'] > 1 else 0
    features['extreme_units'] = 1 if claim_data['units'] > 3 else 0
    features['amount_x_units'] = claim_data['claim_amount'] * claim_data['units']
    features['delay_x_amount'] = claim_data['days_to_submit'] * np.log1p(claim_data['claim_amount'])
    
    # Encoded categories
    try:
        features['specialty_encoded'] = encoders['specialty'].transform([provider_data['specialty']])[0]
    except:
        features['specialty_encoded'] = 0
    
    try:
        features['cpt_encoded'] = encoders['cpt'].transform([claim_data['cpt_code']])[0]
    except:
        features['cpt_encoded'] = 0
    
    return np.array([[features.get(col, 0) for col in FEATURE_COLS]])

@app.route('/')
def index():
    return send_from_directory('Static', 'index.html')

@app.route('/database.html')
def database():
    return send_from_directory('Static', 'database.html')

@app.route('/demo.html')
def demo():
    return send_from_directory('Static', 'demo.html')

@app.route('/executive.html')
def executive():
    return send_from_directory('Static', 'executive.html')

@app.route('/api/providers', methods=['GET'])
def get_providers():
    try:
        conn = get_db_connection()
        providers = conn.execute('SELECT * FROM providers LIMIT 50').fetchall()
        conn.close()
        return jsonify([dict(row) for row in providers])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_claim():
    try:
        data = request.json
        
        # Get provider info
        conn = get_db_connection()
        provider = conn.execute(
            'SELECT * FROM providers WHERE provider_id = ?', 
            (data['provider_id'],)
        ).fetchone()
        conn.close()
        
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404
        
        provider_data = dict(provider)
        
        # Rule-based check
        violations, rule_score = check_rules(data, provider_data)
        
        # Feature engineering
        features = engineer_single_claim(data, provider_data)
        
        # ML predictions (if models loaded)
        if rf_model and iso_model and scaler and encoders:
            try:
                features_scaled = scaler.transform(features)
                fraud_prob = rf_model.predict_proba(features_scaled)[0][1] * 100
                
                # Use DYNAMIC anomaly calculation instead of Isolation Forest
                anomaly_factors, dynamic_anomaly_score = identify_anomaly_factors(data, provider_data, features_scaled)
                
                # Blend with Isolation Forest (70% dynamic, 30% ML model)
                iso_score = iso_model.score_samples(features_scaled)[0]
                iso_anomaly = max(0, min(100, (1 - iso_score) * 50))
                anomaly_risk = (dynamic_anomaly_score * 0.7) + (iso_anomaly * 0.3)
                
                fraud_factors = identify_fraud_factors(data, provider_data, fraud_prob)
            except Exception as e:
                print(f"ML prediction error: {e}")
                # Fallback if prediction fails
                fraud_prob = 50
                anomaly_factors, dynamic_anomaly_score = identify_anomaly_factors(data, provider_data, None)
                anomaly_risk = dynamic_anomaly_score
                fraud_factors = [f"⚠️ Rule-based analysis only (ML error: {str(e)[:50]})"]
        else:
            # Models not loaded - use rule-based detection only
            fraud_prob = rule_score  # Use rule score as fraud probability
            anomaly_factors, dynamic_anomaly_score = identify_anomaly_factors(data, provider_data, None)
            anomaly_risk = dynamic_anomaly_score
            fraud_factors = ["✅ Rule-based fraud detection active", "⚠️ ML models not available - using policy rules and pattern analysis"]
        
        # Ensemble score
        final_score = (rule_score * 0.4) + (anomaly_risk * 0.3) + (fraud_prob * 0.3)
        
        # Use display name if provided, otherwise use DB name
        display_name = data.get('provider_display_name', provider_data['provider_name'])
        
        # Check for CRITICAL POLICY VIOLATIONS that require manual review
        critical_violations = []
        for violation in violations:
            if any(keyword in violation.upper() for keyword in [
                'FUTURE', 'POLICY VIOLATION', 'IMPOSSIBLE', 
                'SEVERELY EXCEEDS', 'EXCEEDS 120%', 'EXCEEDS 110%',
                'EXTREME UNITS', 'VERY HIGH UNITS', 'HIGH UNITS',
                'NOT ACTIVE', 'LICENSE',
                'FRAUD HISTORY', 'DOCUMENTED FRAUD',
                'VERY DELAYED', 'VERY HIGH TOTAL',
                'INVALID PATIENT AGE', 'HIGH-COST',
                'SAME-DAY SUBMISSION'
            ]):
                critical_violations.append(violation)
        
        # Decision logic - POLICY VIOLATIONS trigger manual review
        if critical_violations:
            decision = "MANUAL_REVIEW"
            action = "Policy violation - Requires manual review"
            color = "orange"
            manual_review_reason = " | ".join(critical_violations[:2])  # Show top 2 reasons
        elif final_score >= 75:
            decision = "MANUAL_REVIEW"
            action = "High risk - Requires investigation"
            color = "red"
            manual_review_reason = "High fraud risk score"
        elif final_score >= 50:
            decision = "MANUAL_REVIEW"
            action = "Moderate risk - Queue for review"
            color = "orange"
            manual_review_reason = "Multiple risk indicators detected"
        elif final_score >= 35:
            decision = "LOW_RISK"
            action = "Low risk - Fast-track processing"
            color = "lightgreen"
            manual_review_reason = None
        else:
            decision = "APPROVED"
            action = "Clean claim - Process payment"
            color = "green"
            manual_review_reason = None
        
        result = {
            'claim_id': data.get('claim_id', 'NEW'),
            'provider_name': display_name,
            'specialty': provider_data['specialty'],
            'amount': data['claim_amount'],
            'cpt_code': data['cpt_code'],
            'decision': decision,
            'action': action,
            'color': color,
            'manual_review_reason': manual_review_reason,
            'risk_score': round(final_score, 1),
            'rule_score': rule_score,
            'anomaly_score': round(anomaly_risk, 1),
            'fraud_probability': round(fraud_prob, 1),
            'violations': violations,
            'critical_violations': critical_violations,
            'anomaly_factors': anomaly_factors,
            'fraud_factors': fraud_factors,
            'model_confidence': round(max(fraud_prob, 100-fraud_prob), 1),
            'top_features': ['claim_amount', 'provider_past_fraud', 'amount_to_max_ratio']
        }
        
        # Save to database
        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO claim_decisions 
                (claim_id, risk_score, decision, fraud_probability, anomaly_score, rule_violations, model_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (result['claim_id'], final_score, decision, fraud_prob, anomaly_risk, 
                  json.dumps(violations), 'RF_v1.0'))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Could not save decision: {e}")
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        conn = get_db_connection()
        
        # Decision distribution
        decisions = conn.execute('''
            SELECT decision, COUNT(*) as count 
            FROM claim_decisions 
            GROUP BY decision
        ''').fetchall()
        
        conn.close()
        
        return jsonify({
            'decision_distribution': {row['decision']: row['count'] for row in decisions}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/claims', methods=['GET'])
def get_claims():
    """Get all claims with optional filters"""
    try:
        limit = request.args.get('limit', 100, type=int)
        fraud_only = request.args.get('fraud_only', 'false').lower() == 'true'
        
        conn = get_db_connection()
        
        if fraud_only:
            query = 'SELECT * FROM claims WHERE is_fraud = 1 LIMIT ?'
        else:
            query = 'SELECT * FROM claims LIMIT ?'
        
        claims = conn.execute(query, (limit,)).fetchall()
        conn.close()
        
        return jsonify({
            'total': len(claims),
            'claims': [dict(row) for row in claims]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/decisions', methods=['GET'])
def get_decisions():
    """Get claim decisions with details"""
    try:
        limit = request.args.get('limit', 50, type=int)
        
        conn = get_db_connection()
        decisions = conn.execute('''
            SELECT d.*, c.cpt_code, c.claim_amount, p.provider_name, p.specialty
            FROM claim_decisions d
            LEFT JOIN claims c ON d.claim_id = c.claim_id
            LEFT JOIN providers p ON c.provider_id = p.provider_id
            ORDER BY d.created_at DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        conn.close()
        
        return jsonify({
            'total': len(decisions),
            'decisions': [dict(row) for row in decisions]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/database-summary', methods=['GET'])
def get_database_summary():
    """Get database statistics summary"""
    try:
        conn = get_db_connection()
        
        total_claims = conn.execute('SELECT COUNT(*) as count FROM claims').fetchone()['count']
        fraud_claims = conn.execute('SELECT COUNT(*) as count FROM claims WHERE is_fraud = 1').fetchone()['count']
        total_providers = conn.execute('SELECT COUNT(*) as count FROM providers').fetchone()['count']
        suspicious_providers = conn.execute('SELECT COUNT(*) as count FROM providers WHERE past_fraud_flags = 1').fetchone()['count']
        total_decisions = conn.execute('SELECT COUNT(*) as count FROM claim_decisions').fetchone()['count']
        
        avg_claim = conn.execute('SELECT AVG(claim_amount) as avg FROM claims').fetchone()['avg']
        avg_fraud = conn.execute('SELECT AVG(claim_amount) as avg FROM claims WHERE is_fraud = 1').fetchone()['avg']
        
        fraud_by_type = conn.execute('''
            SELECT fraud_type, COUNT(*) as count 
            FROM claims 
            WHERE is_fraud = 1 
            GROUP BY fraud_type
        ''').fetchall()
        
        conn.close()
        
        return jsonify({
            'claims': {
                'total': total_claims,
                'fraudulent': fraud_claims,
                'legitimate': total_claims - fraud_claims,
                'fraud_rate': round((fraud_claims / total_claims * 100), 2) if total_claims > 0 else 0,
                'avg_claim_amount': round(avg_claim, 2) if avg_claim else 0,
                'avg_fraud_amount': round(avg_fraud, 2) if avg_fraud else 0
            },
            'providers': {
                'total': total_providers,
                'suspicious': suspicious_providers
            },
            'decisions': {
                'total': total_decisions
            },
            'fraud_types': {row['fraud_type']: row['count'] for row in fraud_by_type}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Starting Fraud Detection API Server...")
    print("📊 Model: Random Forest + Isolation Forest")
    print("🗄️  Database: SQLite (data/fraud_detection.db)")
    print(f"🌐 Server running on port {port}")
    print("\n💡 Deployment ready for Railway, Heroku, Azure, and more!")
    app.run(host='0.0.0.0', debug=False, port=port)