@echo off
echo Setting up FraudShield AI...
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python fraud_detection_system.py
echo Setup complete! Run: python app.py
pause