import os
import secrets
import time
import requests
from typing import Dict, Optional

# In-memory store for OTPs
otp_store: Dict[str, dict] = {}

class EmailSender:
    def __init__(self):
        self.brevo_api_key = os.getenv("BREVO_API_KEY")
        self.brevo_from_email = os.getenv("BREVO_FROM_EMAIL", "noreply@ridealert.com")
        
        print(f"🔧 Brevo Config Loaded:")
        print(f"   From Email: {self.brevo_from_email}")
        print(f"   API Key: {'*' * len(self.brevo_api_key) if self.brevo_api_key else 'NOT SET'}")
        
    def generate_otp(self) -> str:
        """Generate a 6-digit OTP"""
        return str(secrets.randbelow(900000) + 100000)
    
    def store_otp(self, email: str, otp: str, expires_in: int = 600):
        """Store OTP with expiration (default 10 minutes)"""
        otp_store[email] = {
            "otp": otp,
            "expires_at": time.time() + expires_in
        }
    
    def verify_otp(self, email: str, otp: str) -> bool:
        """Verify OTP and clean up if valid"""
        if email not in otp_store:
            return False
        
        stored_data = otp_store[email]
        
        if time.time() > stored_data["expires_at"]:
            del otp_store[email]
            return False
        
        if stored_data["otp"] == otp:
            del otp_store[email]
            return True
        
        return False
    
    def send_verification_email(self, email: str, otp: str) -> bool:
        try:
            print(f"📧 Attempting to send email to: {email}")
            print(f"   From: {self.brevo_from_email}")
            
            # Validate configuration
            if not self.brevo_api_key:
                error_msg = "Brevo configuration incomplete - check BREVO_API_KEY"
                print(f"❌ {error_msg}")
                raise ValueError(error_msg)
            
            # Brevo API configuration
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "accept": "application/json",
                "api-key": self.brevo_api_key,
                "content-type": "application/json"
            }
            
            # Improved email content with better spam avoidance
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Verify Your RideAlert Account</title>
                <style>
                    body {{ 
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                        line-height: 1.6; 
                        color: #333333; 
                        margin: 0;
                        padding: 0;
                        background-color: #f8f9fa;
                        -webkit-font-smoothing: antialiased;
                    }}
                    .container {{ 
                        max-width: 600px; 
                        margin: 0 auto; 
                        background: #ffffff;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    }}
                    .header {{ 
                        background: linear-gradient(135deg, #2563eb, #1d4ed8); 
                        color: white; 
                        padding: 40px 30px; 
                        text-align: center; 
                    }}
                    .header h1 {{
                        margin: 0 0 10px 0;
                        font-size: 32px;
                        font-weight: 700;
                    }}
                    .header p {{
                        margin: 0;
                        opacity: 0.9;
                        font-size: 16px;
                    }}
                    .content {{ 
                        padding: 40px 30px; 
                        background: #ffffff;
                    }}
                    .otp-container {{
                        text-align: center;
                        margin: 30px 0;
                    }}
                    .otp {{ 
                        font-size: 48px; 
                        font-weight: 800; 
                        color: #2563eb; 
                        letter-spacing: 12px;
                        background: #f8fafc;
                        padding: 25px;
                        border-radius: 12px;
                        border: 3px solid #e2e8f0;
                        display: inline-block;
                        font-family: 'Courier New', monospace;
                    }}
                    .footer {{ 
                        text-align: center; 
                        padding: 30px; 
                        color: #64748b; 
                        font-size: 13px;
                        background: #f8f9fa;
                        border-top: 1px solid #e2e8f0;
                    }}
                    .note {{
                        background: #fff7ed;
                        border-left: 4px solid #f97316;
                        padding: 20px;
                        margin: 25px 0;
                        border-radius: 8px;
                        font-size: 14px;
                    }}
                    .button {{
                        display: inline-block;
                        background: #2563eb;
                        color: white;
                        padding: 12px 30px;
                        text-decoration: none;
                        border-radius: 6px;
                        font-weight: 600;
                        margin: 10px 0;
                    }}
                    @media only screen and (max-width: 600px) {{
                        .container {{
                            margin: 10px;
                        }}
                        .otp {{
                            font-size: 36px;
                            letter-spacing: 8px;
                            padding: 20px;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🚗 RideAlert</h1>
                        <p>Vehicle Tracking & Management System</p>
                    </div>
                    <div class="content">
                        <h2 style="color: #1e293b; margin-top: 0;">Email Verification Required</h2>
                        
                        <p>Hello,</p>
                        
                        <p>You're just one step away from accessing your RideAlert account. We received a request to verify this email address for your account.</p>
                        
                        <div class="otp-container">
                            <div class="otp">{otp}</div>
                        </div>
                        
                        <div class="note">
                            <p style="margin: 0; color: #9a3412;">
                                <strong>⏰ Security Notice:</strong> This verification code will expire in <strong>10 minutes</strong> for your protection.
                            </p>
                        </div>
                        
                        <p>If you did not request this verification, please disregard this email. Your account security is important to us.</p>
                        
                        <p>Need help? Contact our support team for assistance.</p>
                    </div>
                    <div class="footer">
                        <p style="margin: 0 0 10px 0;">
                            <strong>RideAlert Team</strong><br>
                            Vehicle Tracking & Management Solutions
                        </p>
                        <p style="margin: 0; font-size: 12px; opacity: 0.7;">
                            This is an automated message. Please do not reply to this email.<br>
                            &copy; 2024 RideAlert. All rights reserved.
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Brevo payload with improved settings
            payload = {
                "sender": {
                    "name": "RideAlert Verification",
                    "email": self.brevo_from_email
                },
                "to": [
                    {
                        "email": email,
                        "name": email.split('@')[0]
                    }
                ],
                "subject": "Verify Your RideAlert Account - Security Code Inside",
                "htmlContent": html_content,
                "textContent": f"""RIDEALERT ACCOUNT VERIFICATION

    Hello,

    To complete your RideAlert account setup, please use the verification code below:

    VERIFICATION CODE: {otp}

    This code expires in 10 minutes for security reasons.

    If you didn't request this verification, please ignore this email.

    Need help? Contact our support team.

    © 2024 RideAlert. All rights reserved.
    """,
                "tags": ["verification", "authentication"]
            }
            
            print(f"🔗 Sending email via Brevo API...")
            
            # Send email using Brevo API
            response = requests.post(url, headers=headers, json=payload)
            
            # Enhanced logging
            print(f"📨 Brevo API Response:")
            print(f"   Status Code: {response.status_code}")
            if response.status_code != 201:
                print(f"   Error Details: {response.text}")
            
            if response.status_code == 201:
                response_data = response.json()
                message_id = response_data.get('messageId', 'Unknown')
                print(f"✅ Email accepted by Brevo! Message ID: {message_id}")
                print(f"💡 Note: Using Gmail as sender may affect deliverability")
                return True
            else:
                print(f"❌ Brevo API Error: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

# Global email sender instance
email_sender = EmailSender()