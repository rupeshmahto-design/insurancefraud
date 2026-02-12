import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import json
import sqlite3
import pickle
import os
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
import warnings
warnings.filterwarnings('ignore')

# Create directories
os.makedirs('data', exist_ok=True)
os.makedirs('models', exist_ok=True)
os.makedirs('static', exist_ok=True)

print("🏗️  Building Real Fraud Detection System...")

def generate_synthetic_healthcare_data(n_records=5000, fraud_rate=0.08):
    """Generate realistic healthcare claims data with known fraud patterns"""
    np.random.seed(42)
    random.seed(42)
    
    print(f"📊 Generating {n_records} synthetic claims with {fraud_rate:.1%} fraud rate...")
    
    specialties = ['Cardiology', 'Orthopedics', 'General Practice', 'Dermatology', 
                   'Physical Therapy', 'Chiropractic', 'Internal Medicine', 'Neurology', 'Oncology']
    states = ['CA', 'TX', 'NY', 'FL', 'IL', 'PA', 'OH', 'GA', 'NC', 'MI']
    
    cpt_codes = {
        '99213': {'desc': 'Office visit, level 3', 'base_fee': 120, 'max_fee': 200, 'category': 'visit'},
        '99214': {'desc': 'Office visit, level 4', 'base_fee': 180, 'max_fee': 300, 'category': 'visit'},
        '99215': {'desc': 'Office visit, level 5', 'base_fee': 250, 'max_fee': 400, 'category': 'visit'},
        '36415': {'desc': 'Venipuncture', 'base_fee': 15, 'max_fee': 25, 'category': 'lab'},
        '80053': {'desc': 'Comprehensive metabolic panel', 'base_fee': 45, 'max_fee': 75, 'category': 'lab'},
        '71020': {'desc': 'Chest X-ray', 'base_fee': 85, 'max_fee': 150, 'category': 'radiology'},
        '93000': {'desc': 'Electrocardiogram', 'base_fee': 65, 'max_fee': 110, 'category': 'cardiology'},
        '97110': {'desc': 'Physical therapy', 'base_fee': 95, 'max_fee': 160, 'category': 'therapy'},
        '20610': {'desc': 'Joint injection', 'base_fee': 220, 'max_fee': 350, 'category': 'surgery'},
        '11042': {'desc': 'Debridement', 'base_fee': 350, 'max_fee': 550, 'category': 'surgery'},
        '93306': {'desc': 'Echocardiogram', 'base_fee': 450, 'max_fee': 700, 'category': 'cardiology'},
        '99285': {'desc': 'ER visit, level 5', 'base_fee': 800, 'max_fee': 1200, 'category': 'emergency'}
    }
    
    icd10_codes = ['E11.9', 'I10', 'M25.561', 'J06.9', 'Z00.00', 'K21.9', 'F41.1', 'M54.5', 
                   'N18.6', 'I25.10', 'E78.5', 'F32.9']
    
    # Generate providers
    n_providers = 200
    providers = []
    for i in range(n_providers):
        provider_id = f"PRV{str(i+1000).zfill(5)}"
        tenure = np.random.randint(1, 25)
        is_suspicious = np.random.random() < 0.05
        
        providers.append({
            'provider_id': provider_id,
            'provider_name': f"Dr. {random.choice(['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'])} {random.choice(['A.', 'B.', 'C.', 'D.', 'E.'])}",
            'specialty': random.choice(specialties),
            'state': random.choice(states),
            'tenure_years': tenure,
            'license_status': 'Suspended' if is_suspicious else np.random.choice(['Active', 'Active', 'Active', 'Active', 'Probation'], p=[0.90, 0.04, 0.03, 0.02, 0.01]),
            'past_fraud_flags': 1 if is_suspicious else np.random.choice([0, 1], p=[0.97, 0.03]),
            'avg_claim_amount': np.random.normal(250, 150),
            'claims_per_month': np.random.randint(20, 200),
            'is_suspicious_provider': is_suspicious
        })
    
    providers_df = pd.DataFrame(providers)
    
    # Generate claims
    claims = []
    base_date = datetime(2023, 1, 1)
    
    for i in range(n_records):
        is_fraud = np.random.random() < fraud_rate
        
        if is_fraud:
            if np.random.random() < 0.4:
                provider = providers_df[providers_df['is_suspicious_provider'] == True].sample(1).iloc[0]
            else:
                provider = providers_df.sample(1).iloc[0]
        else:
            provider = providers_df.sample(1).iloc[0]
        
        cpt = random.choice(list(cpt_codes.keys()))
        cpt_info = cpt_codes[cpt]
        
        service_date = base_date + timedelta(days=random.randint(0, 730))
        submission_lag = random.randint(1, 30)
        
        if is_fraud:
            fraud_type = random.choice(['upcoding', 'overcharge', 'phantom', 'duplicate', 'unbundling', 'frequency'])
            
            if fraud_type == 'upcoding':
                amount = cpt_info['max_fee'] * random.uniform(1.1, 1.4)
                units = 1
            elif fraud_type == 'overcharge':
                amount = cpt_info['max_fee'] * random.uniform(1.3, 2.2)
                units = 1
            elif fraud_type == 'phantom':
                amount = cpt_info['base_fee'] * random.uniform(1.5, 3.0)
                units = random.randint(2, 6)
            elif fraud_type == 'unbundling':
                amount = cpt_info['base_fee'] * random.uniform(1.4, 2.0)
                units = random.randint(2, 5)
            elif fraud_type == 'frequency':
                amount = cpt_info['base_fee']
                units = random.randint(4, 10)
            else:
                amount = cpt_info['base_fee']
                units = 1
            
            fraud_label = 1
            fraud_type_label = fraud_type
        else:
            amount = random.uniform(cpt_info['base_fee'] * 0.85, cpt_info['max_fee'] * 1.0)
            units = 1
            fraud_label = 0
            fraud_type_label = 'none'
        
        patient_age = random.randint(18, 85)
        patient_state = provider['state'] if random.random() > 0.15 else random.choice(states)
        
        claims.append({
            'claim_id': f"CLM{str(i+100000).zfill(8)}",
            'provider_id': provider['provider_id'],
            'patient_id': f"PAT{str(random.randint(10000, 99999))}",
            'service_date': service_date.strftime('%Y-%m-%d'),
            'submission_date': (service_date + timedelta(days=submission_lag)).strftime('%Y-%m-%d'),
            'cpt_code': cpt,
            'cpt_category': cpt_info['category'],
            'icd10_code': random.choice(icd10_codes),
            'claim_amount': round(amount, 2),
            'units': units,
            'patient_age': patient_age,
            'patient_state': patient_state,
            'provider_state': provider['state'],
            'is_fraud': fraud_label,
            'fraud_type': fraud_type_label,
            'days_to_submit': submission_lag
        })
    
    claims_df = pd.DataFrame(claims)
    full_data = claims_df.merge(providers_df, on='provider_id', how='left')
    
    return full_data, providers_df

# Generate data
training_data, providers_db = generate_synthetic_healthcare_data(5000, fraud_rate=0.08)

print(f"✅ Generated {len(training_data)} claims")
print(f"🚨 Fraud distribution:\n{training_data['is_fraud'].value_counts()}")

# Save to CSV
training_data.to_csv('data/training_claims.csv', index=False)
providers_db.to_csv('data/providers.csv', index=False)

# Feature Engineering
def engineer_features(df, is_training=True, scaler=None, feature_cols=None):
    df = df.copy()
    
    # Financial Features
    cpt_stats = df.groupby('cpt_code')['claim_amount'].agg(['mean', 'std']).reset_index()
    cpt_stats.columns = ['cpt_code', 'cpt_mean_amount', 'cpt_std_amount']
    df = df.merge(cpt_stats, on='cpt_code', how='left')
    df['amount_zscore'] = (df['claim_amount'] - df['cpt_mean_amount']) / (df['cpt_std_amount'] + 1e-6)
    df['amount_zscore'] = df['amount_zscore'].fillna(0)
    
    cpt_max_map = {
        '99213': 200, '99214': 300, '99215': 400, '36415': 25,
        '80053': 75, '71020': 150, '93000': 110, '97110': 160,
        '20610': 350, '11042': 550, '93306': 700, '99285': 1200
    }
    df['cpt_max_fee'] = df['cpt_code'].map(cpt_max_map)
    df['amount_to_max_ratio'] = df['claim_amount'] / df['cpt_max_fee']
    
    # Provider Behavior Features
    provider_stats = df.groupby('provider_id').agg({
        'claim_amount': ['mean', 'std', 'count', 'max'],
        'days_to_submit': 'mean',
        'units': 'mean'
    }).reset_index()
    provider_stats.columns = ['provider_id', 'prov_avg_amount', 'prov_std_amount', 
                              'prov_claim_count', 'prov_max_amount', 'prov_avg_submit_days', 'prov_avg_units']
    df = df.merge(provider_stats, on='provider_id', how='left')
    
    specialty_stats = df.groupby('specialty')['claim_amount'].mean().reset_index()
    specialty_stats.columns = ['specialty', 'spec_avg_amount']
    df = df.merge(specialty_stats, on='specialty', how='left')
    df['provider_vs_specialty'] = df['prov_avg_amount'] / (df['spec_avg_amount'] + 1e-6)
    
    # Temporal Features
    df['service_date'] = pd.to_datetime(df['service_date'])
    df['service_dayofweek'] = df['service_date'].dt.dayofweek
    df['service_month'] = df['service_date'].dt.month
    df['is_weekend'] = (df['service_dayofweek'] >= 5).astype(int)
    df['is_month_end'] = (df['service_date'].dt.day >= 25).astype(int)
    
    df['submission_delay_risk'] = pd.cut(df['days_to_submit'], 
                                         bins=[0, 7, 14, 30, 100], 
                                         labels=[0, 1, 2, 3]).astype(int)
    
    # Geographic Features
    df['geo_mismatch'] = (df['patient_state'] != df['provider_state']).astype(int)
    
    # Historical Risk Features
    df['provider_past_fraud'] = df['past_fraud_flags']
    df['license_risk'] = (df['license_status'] != 'Active').astype(int)
    df['provider_tenure_risk'] = (df['tenure_years'] < 2).astype(int)
    
    # Complexity Features
    df['high_cost_procedure'] = (df['claim_amount'] > 500).astype(int)
    df['multiple_units'] = (df['units'] > 1).astype(int)
    df['extreme_units'] = (df['units'] > 3).astype(int)
    
    # Interaction Features
    df['amount_x_units'] = df['claim_amount'] * df['units']
    df['delay_x_amount'] = df['days_to_submit'] * np.log1p(df['claim_amount'])
    
    # Encode categorical features
    le_specialty = LabelEncoder()
    df['specialty_encoded'] = le_specialty.fit_transform(df['specialty'])
    
    le_cpt = LabelEncoder()
    df['cpt_encoded'] = le_cpt.fit_transform(df['cpt_code'])
    
    feature_columns = [
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
    
    df[feature_columns] = df[feature_columns].fillna(0)
    
    if is_training:
        scaler = StandardScaler()
        df[feature_columns] = scaler.fit_transform(df[feature_columns])
    else:
        df[feature_columns] = scaler.transform(df[feature_columns])
    
    return df, feature_columns, scaler, le_specialty, le_cpt

# Engineer features
print("🔧 Engineering features...")
featured_data, feature_cols, scaler, le_spec, le_cpt = engineer_features(training_data)

X = featured_data[feature_cols]
y = featured_data['is_fraud']

# Train Models
print("\n🤖 Training Machine Learning Models...")

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

# Random Forest
rf_model = RandomForestClassifier(
    n_estimators=200,
    max_depth=15,
    min_samples_split=10,
    min_samples_leaf=4,
    class_weight='balanced_subsample',
    random_state=42,
    n_jobs=-1
)

rf_model.fit(X_train, y_train)

# Evaluate
y_pred = rf_model.predict(X_test)
y_prob = rf_model.predict_proba(X_test)[:, 1]

print("\n📊 Random Forest Performance:")
print(classification_report(y_test, y_pred, target_names=['Legitimate', 'Fraud']))
print(f"AUC-ROC: {roc_auc_score(y_test, y_prob):.3f}")

# Isolation Forest
iso_model = IsolationForest(contamination=0.1, random_state=42, n_estimators=150)
iso_model.fit(X_train)

# Save models
with open('models/rf_fraud_model.pkl', 'wb') as f:
    pickle.dump(rf_model, f)
with open('models/isolation_forest.pkl', 'wb') as f:
    pickle.dump(iso_model, f)
with open('models/scaler.pkl', 'wb') as f:
    pickle.dump(scaler, f)
with open('models/label_encoders.pkl', 'wb') as f:
    pickle.dump({'specialty': le_spec, 'cpt': le_cpt}, f)

print("\n💾 Models saved to models/ folder")

# Create Database
print("\n🗄️  Setting up SQLite Database...")

conn = sqlite3.connect('data/fraud_detection.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS providers (
    provider_id TEXT PRIMARY KEY,
    provider_name TEXT,
    specialty TEXT,
    state TEXT,
    tenure_years INTEGER,
    license_status TEXT,
    past_fraud_flags INTEGER,
    avg_claim_amount REAL,
    claims_per_month INTEGER
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    provider_id TEXT,
    patient_id TEXT,
    service_date DATE,
    submission_date DATE,
    cpt_code TEXT,
    cpt_category TEXT,
    icd10_code TEXT,
    claim_amount REAL,
    units INTEGER,
    patient_age INTEGER,
    patient_state TEXT,
    provider_state TEXT,
    is_fraud INTEGER,
    fraud_type TEXT,
    days_to_submit INTEGER
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS claim_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT,
    risk_score REAL,
    decision TEXT,
    fraud_probability REAL,
    anomaly_score REAL,
    rule_violations TEXT,
    model_version TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

providers_db.to_sql('providers', conn, if_exists='replace', index=False)
training_data.to_sql('claims', conn, if_exists='replace', index=False)

conn.commit()
conn.close()

print("✅ Database created at data/fraud_detection.db")
print("\n🎉 SYSTEM READY!")
print("Run: python app.py")