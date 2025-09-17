import os
import random
from datetime import datetime
import socket
import urllib.request
import urllib.error

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.lib.units import inch
from reportlab.lib import colors

# --- Cloudflare R2 Configuration ---
R2_ACCOUNT_ID = '6991a8c34f6392f9f8e53363fd3f1639'
R2_ACCESS_KEY_ID = '060f4cdb48cb4329960edb859375a420'
R2_SECRET_ACCESS_KEY = 'cc4e70de5f7010ab2a8f4ff9be17beb00ca29b26cf3a36f1f3551fb6cbfe93a7'
R2_BUCKET_NAME = 'nila-invoices'
R2_PUBLIC_URL = 'https://pub-e202626b8b554c0cb86edddea736d22c.r2.dev'
R2_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
R2_HOSTNAME = f'{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'

# --- Placeholder functions for the Boto3 test ---
SIGNATURE_IMAGE_PATH = "seal.png"
RUPEE_IMAGE_PATH = "rupee.png"

def create_modern_invoice(order_data, user_data, path):
    """Generates a dummy invoice file for the upload test."""
    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph("Test Invoice", styles['h1']), Paragraph(f"Order ID: {order_data['orderId']}", styles['Normal'])]
    doc.build(story)
    print(f"  [INFO] Dummy invoice generated at: {os.path.abspath(path)}")
    return path

# --- Main Diagnostics Block ---
if __name__ == "__main__":
    print("--- Starting Network & Upload Diagnostics ---")
    print(f"Target Hostname: {R2_HOSTNAME}")
    print(f"Target Endpoint: {R2_ENDPOINT_URL}")
    test_results = {}

    # --- TEST 1: DNS Resolution ---
    # Can your computer find the IP address for the Cloudflare R2 hostname?
    # This checks for DNS server or host file issues.
    print("\n--- 1. Testing DNS Resolution ---")
    try:
        ip_address = socket.gethostbyname(R2_HOSTNAME)
        print(f"  [SUCCESS] ✅ Hostname resolved to IP Address: {ip_address}")
        test_results['DNS'] = 'Success'
    except socket.gaierror as e:
        print(f"  [FAILURE] ❌ Could not resolve hostname. Error: {e}")
        print("  [CAUSE] This indicates a DNS problem. Your computer can't find Cloudflare's servers.")
        test_results['DNS'] = 'Failure'
    except Exception as e:
        print(f"  [FAILURE] ❌ An unexpected error occurred during DNS lookup: {e}")
        test_results['DNS'] = f'Failure: {e}'

    # --- TEST 2: Raw Socket Connection ---
    # Can your computer make a basic network connection to the server on the HTTPS port?
    # This bypasses all libraries and directly tests for firewall blocks.
    print("\n--- 2. Testing Raw Socket Connection on Port 443 ---")
    if test_results.get('DNS') == 'Success':
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)  # 10 second timeout
        try:
            sock.connect((R2_HOSTNAME, 443))
            print("  [SUCCESS] ✅ Connection to port 443 was successful.")
            test_results['Socket'] = 'Success'
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            print(f"  [FAILURE] ❌ Raw connection to port 443 failed. Error: {e}")
            print("  [CAUSE] This STRONGLY suggests a Firewall or Antivirus is blocking Python.")
            test_results['Socket'] = 'Failure'
        finally:
            sock.close()
    else:
        print("  [SKIPPED] Cannot perform socket test without successful DNS resolution.")
        test_results['Socket'] = 'Skipped'


    # --- TEST 3: Standard Library HTTPS Connection ---
    # Can Python's built-in HTTPS library connect?
    # This tests your system's SSL/TLS certificate configuration.
    print("\n--- 3. Testing HTTPS Connection with Standard Library (urllib) ---")
    if test_results.get('Socket') == 'Success':
        try:
            # We expect an error code from the server, which is a sign of success
            urllib.request.urlopen(R2_ENDPOINT_URL, timeout=10)
        except urllib.error.HTTPError as e:
            print(f"  [SUCCESS] ✅ Connection successful. Server responded with HTTP Status: {e.code}")
            print("  [INFO] This is a good result. It means we connected and got a valid response.")
            test_results['Urllib'] = 'Success'
        except urllib.error.URLError as e:
            print(f"  [FAILURE] ❌ Urllib could not open the URL. Error: {e.reason}")
            print("  [CAUSE] This could be an SSL/TLS certificate issue or a proxy problem.")
            test_results['Urllib'] = 'Failure'
    else:
        print("  [SKIPPED] Cannot perform HTTPS test without a successful raw socket connection.")
        test_results['Urllib'] = 'Skipped'


    # --- TEST 4: Boto3 Upload ---
    # The final test using your original logic.
    print("\n--- 4. Attempting File Upload with Boto3 ---")
    if test_results.get('Urllib') == 'Success':
        s3_client = boto3.client(
            's3', endpoint_url=R2_ENDPOINT_URL, aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY, config=Config(signature_version='s3v4'),
            region_name='us-east-1'
        )
        sample_order_id = str(random.randint(10000000, 99999999))
        temp_invoice_filename = f"invoice_{sample_order_id}.pdf"
        try:
            # Generate dummy file
            create_modern_invoice({'orderId': sample_order_id}, {}, path=temp_invoice_filename)
            object_key = f"diagnostics/{sample_order_id}/invoice.pdf"
            print(f"  [INFO] Attempting to upload to bucket '{R2_BUCKET_NAME}'...")
            s3_client.upload_file(temp_invoice_filename, R2_BUCKET_NAME, object_key)
            print(f"  [SUCCESS] ✅ Boto3 upload was successful!")
            test_results['Boto3'] = 'Success'
        except Exception as e:
            print(f"  [FAILURE] ❌ Boto3 upload failed. Error: {e}")
            print("  [CAUSE] Failure at this stage points to an issue specific to Boto3 or its dependencies (e.g., proxy handling).")
            test_results['Boto3'] = 'Failure'
        finally:
            if os.path.exists(temp_invoice_filename):
                os.remove(temp_invoice_filename)
    else:
        print("  [SKIPPED] Cannot perform Boto3 test without a successful standard library connection.")
        test_results['Boto3'] = 'Skipped'
    
    print("\n--- DIAGNOSIS COMPLETE ---")