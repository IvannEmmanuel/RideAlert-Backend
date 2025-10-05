import smtplib
import os
from email.message import EmailMessage
import secrets
import time
from typing import Dict, Optional

# In-memory store for OTPs
otp_store: Dict[str, dict] = {}

class EmailSender:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.email_user = os.getenv("EMAIL_USER")
        self.email_password = os.getenv("EMAIL_PASSWORD")
        
        print(f"🔧 Email Config Loaded:")
        print(f"   User: {self.email_user}")
        print(f"   Password: {'*' * len(self.email_password) if self.email_password else 'NOT SET'}")
        print(f"   Server: {self.smtp_server}:{self.smtp_port}")
        
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
        """Send verification email with OTP"""
        try:
            print(f"📧 Attempting to send email to: {email}")
            
            # Validate configuration
            if not self.email_user or not self.email_password:
                error_msg = "Email configuration incomplete - check EMAIL_USER and EMAIL_PASSWORD"
                print(f"❌ {error_msg}")
                raise ValueError(error_msg)
            
            # Create message
            msg = EmailMessage()
            msg['From'] = self.email_user
            msg['To'] = email
            msg['Subject'] = "Verify Your Email - RideAlert"
            
            # Email content
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; }}
                    .content {{ background: #f8fafc; padding: 30px; }}
                    .otp {{ font-size: 32px; font-weight: bold; color: #2563eb; text-align: center; margin: 20px 0; }}
                    .footer {{ text-align: center; padding: 20px; color: #64748b; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>RideAlert</h1>
                        <p>Vehicle Tracking & Management System</p>
                    </div>
                    <div class="content">
                        <h2>Verify Your Email Address</h2>
                        <p>Thank you for registering with RideAlert. Use the verification code below:</p>
                        <div class="otp">{otp}</div>
                        <p><strong>This code will expire in 10 minutes.</strong></p>
                    </div>
                    <div class="footer">
                        <p>&copy; 2024 RideAlert. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg.set_content(f"Your RideAlert verification code is: {otp}. This code expires in 10 minutes.")
            msg.add_alternative(html_content, subtype='html')
            
            print(f"🔗 Connecting to {self.smtp_server}:{self.smtp_port}...")
            
            # Send email with detailed error handling
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.set_debuglevel(1)  # This will print SMTP conversation
                print("🔐 Starting TLS...")
                server.starttls()
                
                print(f"👤 Logging in as: {self.email_user}")
                server.login(self.email_user, self.email_password)
                
                print(f"📤 Sending email...")
                server.send_message(msg)
            
            print(f"✅ Email sent successfully to {email}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP Authentication Failed: {e}")
            print("   This usually means:")
            print("   1. Wrong email or password")
            print("   2. 2FA not enabled on Gmail")
            print("   3. Using regular password instead of App Password")
            print("   4. App Password not generated for 'Mail'")
            return False
        except smtplib.SMTPException as e:
            print(f"❌ SMTP Error: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

# Global email sender instance
email_sender = EmailSender()