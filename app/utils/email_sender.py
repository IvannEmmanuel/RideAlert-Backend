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

    def _create_email_payload(self, to_email: str, to_name: str, subject: str, html_content: str, text_content: str, tags: list, headers: dict = None) -> dict:
        """Create optimized email payload with anti-spam measures"""
        base_payload = {
            "sender": {
                "name": "RideAlert",
                "email": self.brevo_from_email
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name
                }
            ],
            "subject": subject,
            "htmlContent": html_content,
            "textContent": text_content,
            "tags": tags,
            "headers": {
                "X-Mailer": "RideAlert-System",
                "X-Priority": "3",  # Normal priority
                "X-MSMail-Priority": "Normal",
                "Importance": "Normal"
            },
            "params": {
                "company": "RideAlert",
                "website": "https://ridealertadminpanel.onrender.com"
            }
        }
        
        # Add custom headers if provided
        if headers:
            base_payload["headers"].update(headers)
            
        return base_payload

    def send_verification_email(self, email: str, otp: str) -> bool:
        try:
            print(f"📧 Attempting to send verification email to: {email}")
            
            if not self.brevo_api_key:
                error_msg = "Brevo configuration incomplete - check BREVO_API_KEY"
                print(f"❌ {error_msg}")
                raise ValueError(error_msg)
            
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "accept": "application/json",
                "api-key": self.brevo_api_key,
                "content-type": "application/json"
            }
            
            # Improved email content with anti-spam optimization
            subject = "Verify Your RideAlert Account"
            html_content = self._create_verification_html(otp)
            text_content = self._create_verification_text(otp)
            
            payload = self._create_email_payload(
                to_email=email,
                to_name=email.split('@')[0],
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                tags=["verification", "authentication", "transactional"],
                headers={
                    "X-Template": "account-verification"
                }
            )
            
            return self._send_email_via_brevo(url, headers, payload, email, "verification")
                
        except Exception as e:
            print(f"❌ Unexpected error in verification email: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _create_verification_html(self, otp: str) -> str:
        return f"""
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
                    
                    <div style="background: #fff7ed; border-left: 4px solid #f97316; padding: 20px; margin: 25px 0; border-radius: 8px;">
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

    def _create_verification_text(self, otp: str) -> str:
        return f"""RIDEALERT ACCOUNT VERIFICATION

Hello,

To complete your RideAlert account setup, please use the verification code below:

VERIFICATION CODE: {otp}

This code expires in 10 minutes for security reasons.

If you didn't request this verification, please ignore this email.

Need help? Contact our support team.

© 2025 RideAlert. All rights reserved.
https://ridealertadminpanel.onrender.com
"""

    def _send_email_via_brevo(self, url: str, headers: dict, payload: dict, recipient: str, email_type: str) -> bool:
        """Send email via Brevo API with enhanced error handling"""
        try:
            print(f"🔗 Sending {email_type} email via Brevo API...")
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            print(f"📨 Brevo API Response for {email_type}:")
            print(f"   Status Code: {response.status_code}")
            
            if response.status_code == 201:
                response_data = response.json()
                message_id = response_data.get('messageId', 'Unknown')
                print(f"✅ {email_type.capitalize()} email accepted by Brevo! Message ID: {message_id}")
                return True
            else:
                error_details = response.text
                print(f"❌ Brevo API Error for {email_type}: {response.status_code}")
                print(f"   Error Details: {error_details}")
                return False
                
        except requests.exceptions.Timeout:
            print(f"❌ Brevo API timeout for {email_type} email to {recipient}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error sending {email_type} email: {e}")
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
            
            subject = f"Registration Approved - Welcome to RideAlert, {company_name}!"
            html_content = self._create_approval_html(company_name, company_email, login_credentials)
            text_content = self._create_approval_text(company_name, company_email, login_credentials)
            
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
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content,
                "headers": {
                    "X-Mailer": "RideAlert-System",
                    "X-Priority": "3",
                    "X-MSMail-Priority": "Normal",
                    "Importance": "Normal",
                    "X-Template": "account-approval"
                },
                "tags": ["approval", "onboarding", "transactional"],
                "params": {
                    "company": "RideAlert",
                    "website": "https://ridealertadminpanel.onrender.com"
                }
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
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

    def _create_approval_html(self, company_name: str, company_email: str, login_credentials: dict) -> str:
        login_url = login_credentials.get('login_url', 'https://ridealertadminpanel.onrender.com') if login_credentials else 'https://ridealertadminpanel.onrender.com'
        
        return f"""
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
                        <h3>Login Credentials:</h3>
                        <p><strong>Email:</strong> {company_email}</p>
                        <p><strong>Password:</strong> Use the password you created during registration</p>
                        <p><strong>Login URL:</strong> <a href="{login_url}">Access Your Dashboard</a></p>
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
                        &copy; 2025 RideAlert. All rights reserved.<br>
                        <a href="https://ridealertadminpanel.onrender.com" style="color: #64748b;">Visit our website</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

    def _create_approval_text(self, company_name: str, company_email: str, login_credentials: dict) -> str:
        login_url = login_credentials.get('login_url', 'https://ridealertadminpanel.onrender.com') if login_credentials else 'https://ridealertadminpanel.onrender.com'
        
        return f"""REGISTRATION APPROVED - RIDEALERT

Congratulations, {company_name}!

Your company registration has been approved and your fleet management account is now active.

You can now access the RideAlert dashboard to manage your vehicles and track routes.

Login Details:
• Email: {company_email}
• Password: Use the password you created during registration
• Login URL: {login_url}

Next Steps:
• Log in to your dashboard
• Set up your vehicle fleet
• Add drivers and assign vehicles
• Configure your tracking preferences

Need help? Contact our support team.

© 2025 RideAlert. All rights reserved.
Website: https://ridealertadminpanel.onrender.com
"""


class RejectionEmailSender:
    def __init__(self):
        self.brevo_api_key = os.getenv("BREVO_API_KEY")
        self.brevo_from_email = os.getenv("BREVO_FROM_EMAIL", "noreply@ridealert.com")
    
    def send_rejection_email(self, company_email: str, company_name: str, rejection_reason: str = None) -> bool:
        """
        Send rejection email to company with optional reason
        """
        try:
            print(f"📧 Sending rejection email to: {company_email}")
            
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
            
            subject = f"Update on Your RideAlert Registration - {company_name}"
            html_content = self._create_rejection_html(company_name, rejection_reason)
            text_content = self._create_rejection_text(company_name, rejection_reason)
            
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
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content,
                "headers": {
                    "X-Mailer": "RideAlert-System",
                    "X-Priority": "3",
                    "X-MSMail-Priority": "Normal",
                    "Importance": "Normal",
                    "X-Template": "account-rejection"
                },
                "tags": ["rejection", "registration", "transactional"],
                "params": {
                    "company": "RideAlert",
                    "website": "https://ridealertadminpanel.onrender.com"
                }
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            print(f"📨 Rejection Email API Response: {response.status_code}")
            
            if response.status_code == 201:
                print(f"✅ Rejection email sent successfully to {company_email}")
                return True
            else:
                print(f"❌ Failed to send rejection email: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending rejection email: {e}")
            return False

    def _create_rejection_html(self, company_name: str, rejection_reason: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Registration Update - RideAlert</title>
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
                    background: linear-gradient(135deg, #6b7280, #4b5563); 
                    color: white; 
                    padding: 40px 30px; 
                    text-align: center; 
                }}
                .content {{ 
                    padding: 40px 30px; 
                    background: #ffffff;
                }}
                .notice {{
                    background: #fef2f2;
                    border: 2px solid #fecaca;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .next-steps {{
                    background: #fffbeb;
                    border: 2px solid #fed7aa;
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
                    <h1>Registration Status Update</h1>
                    <p>RideAlert Fleet Management</p>
                </div>
                <div class="content">
                    <h2>Dear {company_name},</h2>
                    
                    <p>Thank you for your interest in RideAlert. After careful review, we regret to inform you that your registration request has not been approved at this time.</p>
                    
                    <div class="notice">
                        <h3>Application Status: <span style="color: #dc2626;">Not Approved</span></h3>
                        {f'<p><strong>Reason:</strong> {rejection_reason}</p>' if rejection_reason else '''
                        <p>This decision may be due to various factors including business verification requirements, documentation completeness, or current capacity limitations.</p>
                        '''}
                    </div>
                    
                    <div class="next-steps">
                        <h3>What You Can Do Next:</h3>
                        <ul>
                            <li>Review your submitted information for accuracy</li>
                            <li>Ensure all required documents are clear and valid</li>
                            <li>Contact our support team if you have questions</li>
                            <li>Consider reapplying with updated information</li>
                        </ul>
                    </div>
                    
                    <p>We appreciate your understanding and encourage you to reach out to our support team if you would like more specific feedback about your application.</p>
                    
                    <p>Thank you for considering RideAlert for your fleet management needs.</p>
                </div>
                <div class="footer">
                    <p style="margin: 0 0 10px 0;">
                        <strong>RideAlert Team</strong><br>
                        Vehicle Tracking & Management Solutions
                    </p>
                    <p style="margin: 0; font-size: 12px; opacity: 0.7;">
                        This is an automated message. Please do not reply to this email.<br>
                        &copy; 2025 RideAlert. All rights reserved.<br>
                        <a href="https://ridealertadminpanel.onrender.com" style="color: #64748b;">Visit our website</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

    def _create_rejection_text(self, company_name: str, rejection_reason: str) -> str:
        return f"""REGISTRATION UPDATE - RIDEALERT

Dear {company_name},

Thank you for your interest in RideAlert. After careful review, we regret to inform you that your registration request has not been approved at this time.

Application Status: Not Approved
{ f'Reason: {rejection_reason}' if rejection_reason else 'This decision may be due to various factors including business verification requirements, documentation completeness, or current capacity limitations.'}

What You Can Do Next:
• Review your submitted information for accuracy
• Ensure all required documents are clear and valid
• Contact our support team if you have questions
• Consider reapplying with updated information

We appreciate your understanding and encourage you to reach out to our support team if you would like more specific feedback about your application.

Thank you for considering RideAlert for your fleet management needs.

© 2025 RideAlert. All rights reserved.
Website: https://ridealertadminpanel.onrender.com
"""

# Global email sender instances
email_sender = EmailSender()
approval_email_sender = ApprovalEmailSender()
rejection_email_sender = RejectionEmailSender()