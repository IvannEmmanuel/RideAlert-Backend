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
                        <h1>RideAlert</h1>
                        <p>Vehicle Tracking & Management System</p>
                    </div>
                    <div class="content">
                        <h2 style="color: #1e293b; margin-top: 0;">Email Verification Required</h2>
                        
                        <p>Hello,</p>
                        
                        <p>You're just one step away from accessing your RideAlert account. We received a request to verify this email address for your account.</p>
                        
                        <div class="otp-container">
                            <div class="otp">{otp}</div>
                        </div>
                        
                        <div>
                            <p style="margin: 0; color: #9a3412;">
                                <strong>Security Notice:</strong> This verification code will expire in <strong>10 minutes</strong> for your protection.
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
                            &copy; 2025 RideAlert. All rights reserved.
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

class ApprovalEmailSender:
    def __init__(self):
        self.brevo_api_key = os.getenv("BREVO_API_KEY")
        self.brevo_from_email = os.getenv("BREVO_FROM_EMAIL", "noreply@ridealert.com")
    
    def send_approval_email(self, company_email: str, company_name: str, login_credentials: dict = None) -> bool:
        """
        Send approval email to company with login credentials
        """
        try:
            print(f"📧 Sending approval email to: {company_email}")
            
            if not self.brevo_api_key:
                error_msg = "Brevo configuration incomplete - check BREVO_API_KEY"
                print(f"❌ {error_msg}")
                return False
            
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "accept": "application/json",
                "api-key": self.brevo_api_key,
                "content-type": "application/json"
            }
            
            # Email content for approval
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Registration Approved - RideAlert</title>
                <style>
                    body {{ 
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                        line-height: 1.6; 
                        color: #333333; 
                        margin: 0;
                        padding: 0;
                        background-color: #f8f9fa;
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
                        background: linear-gradient(135deg, #10b981, #059669); 
                        color: white; 
                        padding: 40px 30px; 
                        text-align: center; 
                    }}
                    .content {{ 
                        padding: 40px 30px; 
                        background: #ffffff;
                    }}
                    .success-icon {{
                        font-size: 48px;
                        text-align: center;
                        margin-bottom: 20px;
                    }}
                    .credentials {{
                        background: #f0fdf4;
                        border: 2px solid #bbf7d0;
                        border-radius: 8px;
                        padding: 20px;
                        margin: 20px 0;
                    }}
                    .footer {{ 
                        text-align: center; 
                        padding: 30px; 
                        color: #64748b; 
                        font-size: 13px;
                        background: #f8f9fa;
                        border-top: 1px solid #e2e8f0;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Registration Approved</h1>
                        <p>Welcome to RideAlert Fleet Management</p>
                    </div>
                    <div class="content">
                        <h2>Congratulations, {company_name}!</h2>
                        
                        <p>Your company registration has been <strong>approved</strong> and your fleet management account is now active.</p>
                        
                        <p>You can now access the RideAlert dashboard to manage your vehicles, track routes, and utilize all the features included in your selected plan.</p>
                        
                        <div class="credentials">
                            <h3>Login Credentails:</h3>
                            <p><strong>Email:</strong> {company_email}</p>
                            <p><strong>Password:</strong> Use the password you created during registration</p>
                            <p><strong>Login URL:</strong> <a href="{login_credentials.get('login_url', 'https://ridealertadminpanel.onrender.com')}">Access Your Dashboard</a></p>
                        </div>
                        
                        <p><strong>Next Steps:</strong></p>
                        <ul>
                            <li>Log in to your dashboard</li>
                            <li>Set up your vehicle fleet</li>
                            <li>Add drivers and assign vehicles</li>
                            <li>Configure your tracking preferences</li>
                        </ul>
                        
                        <p>If you have any questions or need assistance, please contact our support team.</p>
                    </div>
                    <div class="footer">
                        <p style="margin: 0 0 10px 0;">
                            <strong>RideAlert Team</strong><br>
                            Vehicle Tracking & Management Solutions
                        </p>
                        <p style="margin: 0; font-size: 12px; opacity: 0.7;">
                            This is an automated message. Please do not reply to this email.<br>
                            &copy; 2025 RideAlert. All rights reserved.
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            payload = {
                "sender": {
                    "name": "RideAlert Fleet Management",
                    "email": self.brevo_from_email
                },
                "to": [
                    {
                        "email": company_email,
                        "name": company_name
                    }
                ],
                "subject": f"🎉 Registration Approved - Welcome to RideAlert, {company_name}!",
                "htmlContent": html_content,
                "textContent": f"""REGISTRATION APPROVED - RIDEALERT

Congratulations, {company_name}!

Your company registration has been approved and your fleet management account is now active.

You can now access the RideAlert dashboard to manage your vehicles and track routes.

Login Details:
• Email: {company_email}
• Password: Use the password you created during registration
• Login URL: {login_credentials.get('login_url', 'https://ridealertadminpanel.onrender.com/')}

Next Steps:
• Log in to your dashboard
• Set up your vehicle fleet
• Add drivers and assign vehicles
• Configure your tracking preferences

Need help? Contact our support team.

© 2024 RideAlert. All rights reserved.
""",
                "tags": ["approval", "onboarding"]
            }
            
            response = requests.post(url, headers=headers, json=payload)
            
            print(f"📨 Approval Email API Response: {response.status_code}")
            
            if response.status_code == 201:
                print(f"✅ Approval email sent successfully to {company_email}")
                return True
            else:
                print(f"❌ Failed to send approval email: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending approval email: {e}")
            return False

# Global approval email sender instance
approval_email_sender = ApprovalEmailSender()
# Global email sender instance
email_sender = EmailSender()