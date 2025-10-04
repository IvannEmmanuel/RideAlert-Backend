#!/usr/bin/env python3
"""
Test script to verify password hashing compatibility
Run this script to test if the password hashing fix works
"""

from app.utils.pasword_hashing import hash_password, verify_password
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def test_password_hashing():
    print("Testing password hashing compatibility...")

    # Test cases
    test_passwords = [
        "simplepassword",
        "complex@Password123!",
        "a" * 100,  # Long password to test truncation
        "émojis🔥password",  # Unicode characters
    ]

    for password in test_passwords:
        print(
            f"\nTesting password: '{password[:20]}{'...' if len(password) > 20 else ''}'")

        try:
            # Hash the password
            hashed = hash_password(password)
            print(f"✓ Hashing successful: {hashed[:30]}...")

            # Verify the password
            is_valid = verify_password(password, hashed)
            print(f"✓ Verification: {'PASS' if is_valid else 'FAIL'}")

            # Test with wrong password
            wrong_password = password + "wrong"
            is_invalid = verify_password(wrong_password, hashed)
            print(
                f"✓ Wrong password rejected: {'PASS' if not is_invalid else 'FAIL'}")

        except Exception as e:
            print(f"✗ Error: {e}")

    print("\n" + "="*50)
    print("Password hashing test completed!")


if __name__ == "__main__":
    test_password_hashing()
