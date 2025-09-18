import os
import random
import smtplib
import re
from datetime import timedelta, datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_cors import CORS
import firebase_admin
from email.mime.text import MIMEText
from firebase_admin import credentials, db, auth
import io
import json
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import certifi
from dotenv import load_dotenv

# Imports for PDF Generation
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.lib.units import inch
from reportlab.lib import colors

# Load environment variables from .env file for local development
load_dotenv()

# --- Configuration from Environment ---
# All secrets and configurations are now loaded from the environment.
FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY')
FIREBASE_DATABASE_URL = os.environ.get('FIREBASE_DATABASE_URL')
FIREBASE_CREDS_JSON = os.environ.get('FIREBASE_CREDENTIALS_JSON')

R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')
R2_PUBLIC_URL_BASE = os.environ.get('R2_PUBLIC_URL_BASE')

GMAIL_SENDER_EMAIL = os.environ.get('GMAIL_SENDER_EMAIL')
GMAIL_SENDER_PASSWORD = os.environ.get('GMAIL_SENDER_PASSWORD')

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app, resources={
    r"/*": {"origins": "*"}
})
app.secret_key = FLASK_SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# --- Firebase Initialization (Secure Method) ---
try:
    if FIREBASE_CREDS_JSON and FIREBASE_DATABASE_URL:
        firebase_creds_dict = json.loads(FIREBASE_CREDS_JSON)
        cred = credentials.Certificate(firebase_creds_dict)
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})
        print("✅ Firebase initialized successfully.")
    else:
        print("❌ ERROR: FIREBASE_CREDS_JSON or FIREBASE_DATABASE_URL environment variable not set.")
except (json.JSONDecodeError, TypeError) as e:
    print(f"❌ ERROR: Failed to parse Firebase credentials. Error: {e}")
except Exception as e:
    print(f"❌ ERROR: Failed to initialize Firebase. Error: {e}")

# --- Cloudflare R2 Client Initialization ---
try:
    if all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
        s3_client = boto3.client(
            's3',
            endpoint_url=f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name='auto',
            verify=certifi.where()
        )
        print("✅ S3 client initialized successfully.")
    else:
        s3_client = None
        print("⚠️ Warning: S3 client not initialized. R2 credentials missing from environment.")
except Exception as e:
    s3_client = None
    print(f"❌ ERROR: Failed to initialize S3 client. Error: {e}")


# --- Database Setup (Injects Sample Products) ---
def setup_database():
    """Checks for stock items and injects sample data if none exist."""
    stock_ref = db.reference('stockitems')
    if stock_ref.get() is None:
        print("No stock items found. Injecting sample data...")
        sample_products = {
            "item001": {'name': 'Ethereal Silk Saree', 'price': 4999, 'availableStock': 10, 'image': 'https://images.unsplash.com/photo-1620799140408-edc6d633?w=500&q=80', 'description': 'Graceful sarees woven with pure silk threads.'},
            "item002": {'name': 'Urban Comfort Kurti', 'price': 1299, 'availableStock': 25, 'image': 'https://images.unsplash.com/photo-1617137968427-85924c800a22?w=500&q=80', 'description': 'Contemporary designs for the modern lifestyle.'},
            "item003": {'name': 'Festive Anarkali', 'price': 7500, 'availableStock': 8, 'image': 'https://images.unsplash.com/photo-1583209575916-b6b6a4a6e8b4?w=500&q=80', 'description': 'Celebrate in style with our vibrant festive collection.'},
            "item004": {'name': 'Dreamy Linen Bedsheet', 'price': 2500, 'availableStock': 15, 'image': 'https://images.unsplash.com/photo-1593930432389-1a73c1c3b4a2?w=500&q=80', 'description': 'Comfortable and chic home linen essentials.'},
            "item005": {'name': 'Classic Cotton Salwar', 'price': 1800, 'availableStock': 30, 'image': 'https://images.unsplash.com/photo-1600871649646-a1851b453e0d?w=500&q=80', 'description': 'Breathable and elegant everyday cotton wear.'},
            "item006": {'name': 'Bridal Lehenga', 'price': 25000, 'availableStock': 5, 'image': 'https://images.unsplash.com/photo-1596609552197-0dc234123652?w=500&q=80', 'description': 'Exquisite handcrafted bridal wear for your special day.'},
            "item007": {'name': 'Designer Georgette Gown', 'price': 8999, 'availableStock': 12, 'image': 'https://images.unsplash.com/photo-1594650537308-391307047f9e?w=500&q=80', 'description': 'Flowy and elegant for evening parties.'},
            "item008": {'name': 'Handloom Cotton Towels', 'price': 999, 'availableStock': 0, 'image': 'https://images.unsplash.com/photo-1611099149791-33299a9a5f7e?w=500&q=80', 'description': 'Set of 2 soft, absorbent handloom towels.'},
        }
        stock_ref.set(sample_products)
        print("Sample product data injected successfully.")

# --- Database Setup for Careers Page ---
def setup_careers_database():
    """Checks for careers data and injects it if none exists."""
    careers_ref = db.reference('careers')
    if careers_ref.get() is None:
        print("No careers data found. Injecting sample data...")
        sample_careers_data = {
            "jobs": {
                "job01": { "id": 1, "title": 'Senior Software Engineer, Backend', "location": 'Chennai, TN', "category": 'Engineering', "type": 'Full-time', "description": 'Design and develop scalable backend services for our e-commerce platform. Proficient in Python, Go, or similar languages and experienced with cloud infrastructure.' },
                "job02": { "id": 2, "title": 'Product Designer, UX/UI', "location": 'Mumbai, MH', "category": 'Design', "type": 'Full-time', "description": 'Create intuitive and beautiful user experiences across our web and mobile applications. Strong portfolio in UX research and visual design required.' },
                "job03": { "id": 3, "title": 'Data Scientist, Supply Chain', "location": 'Bengaluru, KA', "category": 'Data Science', "type": 'Full-time', "description": 'Leverage data to optimize our supply chain, forecast demand, and improve logistics. Expertise in machine learning models and statistical analysis is essential.' },
                "job04": { "id": 4, "title": 'Digital Marketing Manager', "location": 'Remote', "category": 'Marketing', "type": 'Full-time', "description": 'Lead our digital marketing campaigns across SEO, SEM, and social media channels to drive growth and brand awareness.' },
                "job05": { "id": 5, "title": 'Textile Sourcing Specialist', "location": 'Coimbatore, TN', "category": 'Operations', "type": 'Full-time', "description": 'Identify and build relationships with textile suppliers, ensuring quality and sustainability standards are met. Deep knowledge of fabrics is a must.' },
                "job06": { "id": 6, "title": 'Customer Support Associate', "location": 'Chennai, TN', "category": 'Customer Service', "type": 'Part-time', "description": 'Be the voice of Nila by providing exceptional support to our customers via email, chat, and phone. Excellent communication skills are key.' },
                "job07": { "id": 7, "title": 'Frontend Developer Intern', "location": 'Bengaluru, KA', "category": 'Engineering', "type": 'Internship', "description": 'Join our frontend team to build and improve user-facing features. Gain hands-on experience with modern JavaScript frameworks like React or Vue.' },
                "job08": { "id": 8, "title": 'Finance Analyst', "location": 'Mumbai, MH', "category": 'Finance', "type": 'Full-time', "description": 'Analyze financial data, prepare reports, and assist in budgeting and forecasting to support strategic business decisions.' }
            },
            "offices": {
                "loc01": { "city": 'Chennai, TN', "type": 'Corporate Office', "address": '123 NILA Towers, Anna Salai, Chennai, 600002' },
                "loc02": { "city": 'Mumbai, MH', "type": 'Showroom & Office', "address": '456 Silk Route, Bandra West, Mumbai, 400050' },
                "loc03": { "city": 'Bengaluru, KA', "type": 'Technology Hub', "address": '789 Tech Park, Koramagala, Bengaluru, 560095' },
                "loc04": { "city": 'Coimbatore, TN', "type": 'Sourcing & Operations', "address": '101 Cotton Avenue, Gandhipuram, Coimbatore, 641012' },
                "loc05": { "city": 'New York, USA', "type": 'International Office', "address": '5th Avenue, New York, NY 10016, United States' },
                "loc06": { "city": 'London, UK', "type": 'European Showroom', "address": 'Regent Street, London W1B 5AP, United Kingdom' }
            }
        }
        careers_ref.set(sample_careers_data)
        print("Sample careers data injected successfully.")


# --- R2 Upload Helper ---
def upload_video_to_r2(video_file, user_name, return_id):
    if not video_file:
        return None, "No video file provided."
    if not s3_client:
        return None, "S3 client is not configured."
    user_name_safe = re.sub(r'[^a-zA-Z0-9_-]', '_', user_name)
    object_key = f"{user_name_safe}/{return_id}/{return_id}_verification.mp4"
    try:
        s3_client.upload_fileobj(
            video_file,
            R2_BUCKET_NAME,
            object_key,
            ExtraArgs={'ContentType': 'video/mp4'}
        )
        public_url = f"{R2_PUBLIC_URL_BASE}/{object_key}"
        print(f"Successfully uploaded {object_key} to R2 bucket {R2_BUCKET_NAME}.")
        return public_url, None
    except Exception as e:
        error_msg = f"An unexpected error occurred during upload: {e}"
        print(f"Upload Error: {error_msg}")
        return None, error_msg

# --- R2 Upload Helper for Resumes ---
def upload_resume_to_r2(resume_file, application_id):
    if not resume_file:
        return None, "No resume file provided."
    if not s3_client:
        return None, "S3 client is not configured."
    object_key = f"job_applications/{application_id}/{application_id}_resume.pdf"
    try:
        s3_client.upload_fileobj(
            resume_file,
            R2_BUCKET_NAME,
            object_key,
            ExtraArgs={'ContentType': 'application/pdf'}
        )
        public_url = f"{R2_PUBLIC_URL_BASE}/{object_key}"
        print(f"Successfully uploaded {object_key} to R2 bucket {R2_BUCKET_NAME}.")
        return public_url, None
    except Exception as e:
        error_msg = f"An unexpected error occurred during resume upload: {e}"
        print(f"Upload Error: {error_msg}")
        return None, error_msg

# --- R2 Deletion Helper for Resumes ---
def delete_resume_from_r2(application_id):
    """Deletes a resume file from Cloudflare R2 based on the application ID."""
    if not application_id:
        return False, "Application ID not provided."
    if not s3_client:
        return False, "S3 client is not configured."
    object_key = f"job_applications/{application_id}/{application_id}_resume.pdf"
    try:
        print(f"Attempting to delete {object_key} from R2 bucket {R2_BUCKET_NAME}...")
        s3_client.delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
        print(f"Successfully deleted {object_key} from R2.")
        return True, None
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"Warning: File {object_key} not found in R2 for deletion, but proceeding.")
            return True, "File not found."
        else:
            error_msg = f"An S3 client error occurred during resume deletion: {e}"
            print(f"Deletion Error: {error_msg}")
            return False, error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred during resume deletion: {e}"
        print(f"Deletion Error: {error_msg}")
        return False, error_msg

# --- Unique ID Generation Helper ---
def generate_unique_id(prefix, id_type):
    id_ref = db.reference(f'existing_ids/{id_type}')
    num_digits = 5
    while True:
        random_part = str(random.randint(0, 10**num_digits - 1)).zfill(num_digits)
        new_id = f"{prefix}{random_part}"
        if not id_ref.child(new_id).get():
            return new_id

# --- PDF Generation Logic (Unchanged) ---
SIGNATURE_IMAGE_PATH = "seal.png"
RUPEE_IMAGE_PATH = "rupee.png"

def create_price_cell(amount_float, styles, is_bold=False):
    font_name = 'Helvetica-Bold' if is_bold else 'Helvetica'
    font_size = 11 if is_bold else 9
    formatted_amount = f"{amount_float:,.2f}"
    if not os.path.exists(RUPEE_IMAGE_PATH):
        style = ParagraphStyle(name='fallbackPrice', fontName=font_name, fontSize=font_size, alignment=TA_RIGHT)
        return Paragraph(f"₹ {formatted_amount}", style)
    rupee_img = Image(RUPEE_IMAGE_PATH, width=font_size, height=font_size)
    rupee_img.hAlign = 'LEFT'
    text_style = ParagraphStyle(name='priceText', fontName=font_name, fontSize=font_size, alignment=TA_RIGHT)
    amount_para = Paragraph(formatted_amount, text_style)
    inner_table = Table(
        [[rupee_img, amount_para]],
        colWidths=[font_size + 2, None],
        style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)])
    )
    return inner_table

def create_modern_invoice(order_data, user_data, path_or_buffer, title="Tax Invoice"):
    doc = SimpleDocTemplate(path_or_buffer, pagesize=A4, rightMargin=0.5*inch, leftMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='MainTitle', fontName='Helvetica-Bold', fontSize=22, alignment=TA_LEFT, textColor=colors.HexColor('#005A9C')))
    styles.add(ParagraphStyle(name='RightAlignText', fontName='Helvetica', fontSize=10, alignment=TA_RIGHT, leading=14))
    styles.add(ParagraphStyle(name='AddressHeader', fontName='Helvetica-Bold', fontSize=10, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='AddressBody', fontName='Helvetica', fontSize=10, alignment=TA_LEFT, leading=14))
    styles.add(ParagraphStyle(name='TableHeader', fontName='Helvetica-Bold', fontSize=9, alignment=TA_CENTER, textColor=colors.white))
    styles.add(ParagraphStyle(name='FooterText', fontName='Helvetica', fontSize=8, alignment=TA_CENTER, textColor=colors.grey))
    styles.add(ParagraphStyle(name='CompanyBrand', fontName='Helvetica-Bold', fontSize=11, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='SignatureText', fontName='Helvetica', fontSize=10, alignment=TA_CENTER))
    id_text = f"Order ID: {order_data['orderId']}<br/>Invoice ID: {order_data['invoiceId']}"
    if title == "Return Invoice" and 'returnInvoiceId' in order_data:
        id_text += f"<br/>Return ID: {order_data['returnInvoiceId']}"
    header_data = [
        [Paragraph(title, styles['MainTitle']), Paragraph(id_text, styles['RightAlignText'])],
        ['', Paragraph(f"Date: {datetime.now().strftime('%d-%b-%Y')}", styles['RightAlignText'])]
    ]
    story.append(Table(header_data, colWidths=[4*inch, 3.5*inch], style=TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')])))
    story.append(Spacer(1, 0.25 * inch))
    if title == "Return Invoice" and 'returnDetails' in order_data:
        addr = order_data['returnDetails'].get('pickupAddress', order_data['shippingAddress'])
    else:
        addr = order_data['shippingAddress']
    address_content = f"{user_data.get('name', '')}<br/>{addr.get('address', '')},<br/>{addr.get('city', '')}, {addr.get('state', '')} - {addr.get('pincode', '')}<br/>{addr.get('country', '')}"
    address_data = [[Paragraph('Sold By', styles['AddressHeader']), Paragraph('Shipping Address', styles['AddressHeader'])], [Paragraph("<b>NILA PRODUCTS</b><br/>14/1-1 Andal Avenue, Vellalore<br/>Coimbatore, Tamil Nadu, 641111<br/><b>GSTIN:</b> 33AQGPM1414L2ZZ", styles['AddressBody']), Paragraph(address_content, styles['AddressBody'])]]
    story.append(Table(address_data, colWidths=[3.75*inch, 3.75*inch], style=TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('PADDING', (0,0), (-1,-1), 10)])))
    story.append(Spacer(1, 0.3 * inch))
    table_header = [Paragraph(h, styles['TableHeader']) for h in ['Product', 'Description', 'Qty', 'Amount', 'CGST (2.5%)', 'SGST (2.5%)', 'Total']]
    col_widths = [1.5*inch, 2.0*inch, 0.4*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.9*inch]
    table_data = [table_header]
    grand_total_amount, total_tax_amount, total_base_amount = 0.0, 0.0, 0.0
    for item in order_data['items']:
        base_price = item['price'] * item['quantity']
        cgst, sgst = base_price * 0.025, base_price * 0.025
        total_item_price = base_price + cgst + sgst
        row = [ Paragraph(item['name'], styles['Normal']), Paragraph(item.get('description', 'N/A'), styles['Normal']), item['quantity'], create_price_cell(base_price, styles), create_price_cell(cgst, styles), create_price_cell(sgst, styles), create_price_cell(total_item_price, styles) ]
        total_base_amount += base_price
        total_tax_amount += (cgst + sgst)
        grand_total_amount += total_item_price
        table_data.append(row)
    items_table = Table(table_data, colWidths=col_widths, style=TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#005A9C')), ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]), ('ALIGN', (2, 1), (2, -1), 'CENTER'), ('ALIGN', (3, 1), (-1, -1), 'RIGHT')]))
    story.append(items_table)
    story.append(Spacer(1, 0.3 * inch))
    totals_data = [
        [Paragraph('Subtotal:', styles['RightAlignText']), create_price_cell(total_base_amount, styles)],
        [Paragraph('Tax (CGST+SGST):', styles['RightAlignText']), create_price_cell(total_tax_amount, styles)],
        [Paragraph('<b>Grand Total:</b>', styles['RightAlignText']), create_price_cell(grand_total_amount, styles, is_bold=True)],
    ]
    totals_table = Table(totals_data, colWidths=[1.5*inch, 1.5*inch], style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('FONTSIZE', (0,0), (-1,-1), 10)]))
    signature_section = ''
    if os.path.exists(SIGNATURE_IMAGE_PATH):
        signature_img = Image(SIGNATURE_IMAGE_PATH, width=1.2*inch, height=0.8*inch)
        signature_section = Table([[signature_img], [Paragraph("For NILA PRODUCTS", styles['SignatureText'])], [Paragraph("<i>Authorized Seal</i>", styles['SignatureText'])]], style=TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
    summary_table = Table([[signature_section, totals_table]], colWidths=[4.5*inch, 3*inch], style=TableStyle([('VALIGN', (0,0), (-1,-1), 'BOTTOM')]))
    story.append(summary_table)
    story.append(Spacer(1, 0.5 * inch))
    story.append(Table([[Paragraph("Generated via", styles['FooterText'])], [Paragraph("NILA PRODUCTS", styles['CompanyBrand'])]], colWidths=[7.5*inch]))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("This is a computer-generated document.", styles['FooterText']))
    doc.build(story)
    print(f"Document '{title}' successfully generated in-memory.")
    return path_or_buffer

# --- Email and Validation functions (Modified for Security) ---
def send_otp_email(receiver_email, otp):
    sender_email = GMAIL_SENDER_EMAIL
    sender_password = GMAIL_SENDER_PASSWORD
    if not all([sender_email, sender_password]):
        print("⚠️ Email credentials are not configured in environment.")
        return False
    msg = MIMEText(f"""<html><body style="font-family: Arial, sans-serif; color: #222;"><div style="max-width: 480px; margin: auto; border: 1px solid #e0e0e0; border-radius: 10px; box-shadow: 0 2px 8px #e0e0e0; padding: 32px 24px; background: #f9f9f9;"><h2 style="color: #00bcd4; margin-top: 0;">NILA Products Portal - OTP Verification</h2><p>Dear User,</p><p>We received a request to sign up or log in to your NILA Products account.</p><p style="font-size: 1.1em; margin: 24px 0;"><strong>Your One-Time Password (OTP) is:</strong><span style="display: inline-block; background: #e3f7fa; color: #00bcd4; font-size: 1.5em; letter-spacing: 4px; padding: 10px 24px; border-radius: 8px; margin-left: 10px;">{otp}</span></p><p>This OTP is valid for <strong>5 minutes</strong>. Please do not share this code with anyone.</p><p>If you did not request this, you can safely ignore this email.</p><br><p style="color: #888; font-size: 0.95em;">Thank you,<br>NILA Products Team</p></div></body></html>""", "html")
    msg['Subject'] = 'Your NILA OTP Code'
    msg['From'] = sender_email
    msg['To'] = receiver_email
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"OTP sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"Email send error: {e}")
        return False

def send_account_created_email(receiver_email, name):
    sender_email = GMAIL_SENDER_EMAIL
    sender_password = GMAIL_SENDER_PASSWORD
    if not all([sender_email, sender_password]):
        print("⚠️ Email credentials are not configured in environment.")
        return False
    msg = MIMEText(f"""<html><body style="font-family: Arial, sans-serif; color: #222;"><div style="max-width: 480px; margin: auto; border: 1px solid #e0e0e0; border-radius: 10px; box-shadow: 0 2px 8px #e0e0e0; padding: 32px 24px; background: #f9f9f9;"><h2 style="color: #00bcd4; margin-top: 0;">🎉 Welcome to NILA Products!</h2><p>Dear <strong>{name}</strong>,</p><p>We are thrilled to let you know that your <b>NILA Products</b> account has been <span style="color:#00bcd4;font-weight:bold;">successfully created</span>!</p><ul style="margin: 18px 0 18px 1.2em; color: #444;"><li>Your <b>email</b> is your username for secure access.</li><li>Your <b>phone number</b> is linked for account recovery and notifications.</li><li>Enjoy seamless access to our textile commerce platform.</li></ul><p style="margin: 18px 0; color: #388e3c;"><b>✨ Explore, connect, and grow with NILA Products!</b></p><div style="margin: 24px 0; padding: 16px; background: #e3f7fa; border-radius: 8px; color: #00bcd4;"><b>Security Tip:</b> Never share your password or OTP with anyone.<br>For help, contact us at <a href="mailto:support@nilaproducts.com">support@nilaproducts.com</a>.</div><p style="color: #888; font-size: 0.95em;">Thank you for joining us,<br><strong>NILA Products Team</strong></p><div style="margin-top:18px;text-align:center;"><img src="https://img.icons8.com/color/96/000000/checked-2--v2.png" alt="Success" width="48" height="48"/></div></div></body></html>""", "html")
    msg['Subject'] = '🎉 Your NILA Products Account is Ready!'
    msg['From'] = sender_email
    msg['To'] = receiver_email
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"Account creation email sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"Account creation email send error: {e}")
        return False

def send_order_confirmation_email(receiver_email, name, order_data):
    sender_email = GMAIL_SENDER_EMAIL
    sender_password = GMAIL_SENDER_PASSWORD
    if not all([sender_email, sender_password]):
        print("⚠️ Email credentials are not configured in environment.")
        return False
    items_html = ""
    total_base_amount = 0.0
    for item in order_data['items']:
        item_total = item['price'] * item['quantity']
        total_base_amount += item_total
        items_html += f"<tr><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{item['name']}</td><td style='padding: 8px; border-bottom: 1px solid #ddd; text-align: center;'>{item['quantity']}</td><td style='padding: 8px; border-bottom: 1px solid #ddd; text-align: right;'>₹{item_total:,.2f}</td></tr>"
    tax_amount = total_base_amount * 0.05
    grand_total = total_base_amount + tax_amount
    addr = order_data['shippingAddress']
    address_html = f"{addr.get('address', '')},<br>{addr.get('city', '')}, {addr.get('state', '')} - {addr.get('pincode', '')}<br>{addr.get('country', '')}"
    msg_body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333;"><div style="max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 10px; padding: 32px 24px; background: #f9f9f9;"><h2 style="color: #00bcd4; margin-top: 0;">✅ Your NILA Order is Confirmed!</h2><p>Dear <strong>{name}</strong>,</p><p>Thank you for your purchase! We've received your order and are getting it ready for you. Here are the details:</p><div style="margin: 24px 0; padding: 16px; background: #fff; border-radius: 8px;"><h3 style="margin-top: 0; color: #555;">Order Summary</h3><p><strong>Order ID:</strong> {order_data['orderId']}<br><strong>Invoice ID:</strong> {order_data['invoiceId']}<br><strong>Order Date:</strong> {datetime.now().strftime('%d-%b-%Y %H:%M')}</p><table style="width: 100%; border-collapse: collapse; margin-top: 16px;"><thead><tr><th style='padding: 8px; background-color: #f2f2f2; text-align: left;'>Product</th><th style='padding: 8px; background-color: #f2f2f2; text-align: center;'>Quantity</th><th style='padding: 8px; background-color: #f2f2f2; text-align: right;'>Price</th></tr></thead><tbody>{items_html}</tbody></table><hr style="border: 0; border-top: 1px solid #eee; margin: 16px 0;"><p style="text-align: right;"><strong>Subtotal:</strong> ₹{total_base_amount:,.2f}</p><p style="text-align: right;"><strong>Tax (5%):</strong> ₹{tax_amount:,.2f}</p><p style="text-align: right; font-size: 1.2em;"><strong>Grand Total:</strong> ₹{grand_total:,.2f}</p></div><div style="margin: 24px 0; padding: 16px; background: #fff; border-radius: 8px;"><h3 style="margin-top: 0; color: #555;">Shipping Address</h3><p>{address_html}</p></div><p>You can view your order details and track its status from your dashboard.</p><p style="color: #888; font-size: 0.95em;">Thank you for shopping with us,<br><strong>NILA Products Team</strong></p></div></body></html>"""
    msg = MIMEText(msg_body, "html")
    msg['Subject'] = f"Order Confirmed: Your NILA Products Order #{order_data['orderId']}"
    msg['From'] = sender_email
    msg['To'] = receiver_email
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"Order confirmation email sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"Order confirmation email send error: {e}")
        return False

def send_application_confirmation_email(receiver_email, name, application_data, job_details):
    sender_email = GMAIL_SENDER_EMAIL
    sender_password = GMAIL_SENDER_PASSWORD
    if not all([sender_email, sender_password]):
        print("⚠️ Email credentials are not configured in environment.")
        return False
    job_title = job_details.get('title', 'N/A')
    job_location = job_details.get('location', 'N/A')
    application_id = application_data.get('applicationId', 'N/A')
    msg_body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333;"><div style="max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 10px; padding: 32px 24px; background: #f9f9f9;"><h2 style="color: #00bcd4; margin-top: 0;">Application Received!</h2><p>Dear <strong>{name}</strong>,</p><p>Thank you for your interest in a career at NILA Products. We have successfully received your application for the following position:</p><div style="margin: 24px 0; padding: 16px; background: #e3f7fa; border-left: 4px solid #00bcd4; border-radius: 4px;"><p style="margin: 0; font-size: 1.2em; color: #00796b;"><strong>{job_title}</strong></p><p style="margin: 4px 0 0; color: #555;">Location: {job_location}</p></div><p>Your application ID is: <strong>{application_id}</strong>. Please keep this for your records.</p><p>Our talent acquisition team will review your qualifications and experience. If your profile matches our requirements, we will contact you for the next steps in the hiring process.</p><p>We appreciate you taking the time to apply.</p><p style="color: #888; font-size: 0.95em;">Best regards,<br><strong>The NILA Products Hiring Team</strong></p></div></body></html>"""
    msg = MIMEText(msg_body, "html")
    msg['Subject'] = f"Your Application for {job_title} at NILA Products"
    msg['From'] = sender_email
    msg['To'] = receiver_email
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"Job application confirmation email sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"Job application confirmation email send error: {e}")
        return False

def send_return_request_email(receiver_email, name, order_data):
    sender_email = GMAIL_SENDER_EMAIL
    sender_password = GMAIL_SENDER_PASSWORD
    if not all([sender_email, sender_password]):
        print("⚠️ Email credentials are not configured in environment.")
        return False
    order_id = order_data.get('orderId', 'N/A')
    return_id = order_data.get('returnInvoiceId', 'N/A')
    reason = order_data.get('returnDetails', {}).get('reason', 'N/A')
    msg_body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333;"><div style="max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 10px; padding: 32px 24px; background: #f9f9f9;"><h2 style="color: #00bcd4; margin-top: 0;">Return Request Initiated</h2><p>Dear <strong>{name}</strong>,</p><p>We have received your return request for your NILA Products order. Our team will review the details and get back to you shortly regarding the next steps for pickup and refund.</p><div style="margin: 24px 0; padding: 16px; background: #fff; border-radius: 8px;"><h3 style="margin-top: 0; color: #555;">Return Details</h3><p><strong>Original Order ID:</strong> {order_id}</p><p><strong>Return ID:</strong> {return_id}</p><p><strong>Reason for Return:</strong> {reason}</p></div><p>Please ensure the product is in its original condition with all tags and packaging intact for a smooth return process. You can track the status of your return request in your user dashboard.</p><p>If you have any questions, feel free to contact our customer support.</p><p style="color: #888; font-size: 0.95em;">Thank you,<br><strong>NILA Products Team</strong></p></div></body></html>"""
    msg = MIMEText(msg_body, "html")
    msg['Subject'] = f"Return Initiated for NILA Order #{order_id}"
    msg['From'] = sender_email
    msg['To'] = receiver_email
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"Return request confirmation email sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"Return request confirmation email send error: {e}")
        return False

def send_stock_notification_email(receiver_email, name, restocked_products):
    sender_email = GMAIL_SENDER_EMAIL
    sender_password = GMAIL_SENDER_PASSWORD
    if not all([sender_email, sender_password]):
        print("⚠️ Email credentials are not configured in environment.")
        return False
    
    product_list_html = ""
    for product in restocked_products:
        product_list_html += f"<li style='margin-bottom: 10px;'><strong>{product['name']}</strong> - Price: ₹{product['price']:,}</li>"

    msg_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
      <div style="max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 10px; padding: 32px 24px; background: #f9f9f9;">
        <h2 style="color: #28a745; margin-top: 0;">Good News! Items are Back in Stock!</h2>
        <p>Dear <strong>{name}</strong>,</p>
        <p>You're in luck! The following item(s) you were interested in are now back in stock and available for purchase:</p>
        <ul style="margin: 24px 0; padding-left: 20px; background: #fff; border-radius: 8px; padding: 16px;">
          {product_list_html}
        </ul>
        <p>Visit the NILA Products dashboard to place your order before they sell out again!</p>
        <p style="color: #888; font-size: 0.95em;">Happy shopping,<br><strong>The NILA Products Team</strong></p>
      </div>
    </body>
    </html>
    """
    
    msg = MIMEText(msg_body, "html")
    msg['Subject'] = "An item you wanted is back in stock!"
    msg['From'] = sender_email
    msg['To'] = receiver_email
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"Stock notification email sent to {receiver_email} for {len(restocked_products)} items.")
        return True
    except Exception as e:
        print(f"Stock notification email send error: {e}")
        return False


def validate_email(email):
    return bool(re.fullmatch(r"[\w\.-]+@[\w\.-]+\.\w{2,}", email))
def validate_phone(phone):
    return bool(re.fullmatch(r"\+?\d{10,15}", phone))
def validate_name(name):
    return bool(re.fullmatch(r"[A-Za-z\s'-]{2,40}", name))
def log_user_out_and_print_message():
    user_email = session.get('user_email')
    if user_email:
        try:
            safe_email_key = user_email.replace('.', '_')
            user_ref = db.reference('users').child(safe_email_key)
            user_data = user_ref.get()
            user_name = user_data.get('name', 'Unknown User') if user_data else user_email
            print(f"--- {user_name} logged out. Session cleared. ---")
        except Exception as e:
            print(f"Error fetching user data for logout message: {e}")
        finally:
            session.clear()
def update_cart_in_db(user_email, cart_data):
    if not user_email:
        print("Error: user_email is missing for database cart update.")
        return False
    safe_email_key = user_email.replace('.', '_')
    user_cart_ref = db.reference(f'users/{safe_email_key}/cart_items')
    try:
        user_cart_ref.set(cart_data)
        print(f"Cart for {user_email} updated in database.")
        return True
    except Exception as e:
        print(f"Error updating cart for {user_email} in database: {e}")
        return False

# --- Routes ---
@app.route('/')
def cover_page():
    return render_template('cover_page.html')

@app.route('/login.html')
def login_page():
    return render_template('login.html')

@app.route('/nila_careers.html')
def careers_page():
    user_info = None
    if session.get('logged_in'):
        user_email = session.get('user_email')
        if user_email:
            safe_email_key = user_email.replace('.', '_')
            user_ref = db.reference(f'users/{safe_email_key}')
            user_data = user_ref.get()
            if user_data:
                user_info = {
                    'name': user_data.get('name', 'N/A'),
                    'email': user_data.get('email')
                }
    return render_template('nila_careers.html', user_info=user_info)


@app.route('/customer_support.html')
def support_page():
    return render_template('customer_support.html')

# --- CAREERS API ROUTES ---
@app.route('/get_jobs')
def get_jobs():
    """Fetches all job listings from the Firebase RTDB."""
    try:
        jobs_ref = db.reference('careers/jobs')
        jobs_data = jobs_ref.get()
        if not jobs_data:
            return jsonify({'success': True, 'jobs': []})
        
        jobs_list = list(jobs_data.values())
        return jsonify({'success': True, 'jobs': jobs_list})
    except Exception as e:
        print(f"Error fetching jobs from DB: {e}")
        return jsonify({'success': False, 'error': 'Could not retrieve job data.'}), 500

@app.route('/get_locations')
def get_locations():
    """Fetches all office locations from the Firebase RTDB."""
    try:
        locations_ref = db.reference('careers/offices')
        locations_data = locations_ref.get()
        if not locations_data:
            return jsonify({'success': True, 'locations': []})

        locations_list = list(locations_data.values())
        return jsonify({'success': True, 'locations': locations_list})
    except Exception as e:
        print(f"Error fetching locations from DB: {e}")
        return jsonify({'success': False, 'error': 'Could not retrieve location data.'}), 500

@app.route('/submit_application', methods=['POST'])
def submit_application():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Authentication required. Please log in to apply.'}), 401

    try:
        user_email_from_session = session.get('user_email')
        safe_email_key = user_email_from_session.replace('.', '_')
        form_data = request.form
        resume_file = request.files.get('resume')

        required_fields = ['jobId', 'applicantName', 'primaryEmail', 'experience', 'workType', 'qualification', 'skills', 'coverLetter']
        for field in required_fields:
            if not form_data.get(field):
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        if not resume_file:
            return jsonify({'success': False, 'error': 'Resume file is required.'}), 400
        
        print("--- New job application received. Processing... ---")
        
        application_id = generate_unique_id('JOB', 'job_applications')
        print(f"Generated unique application ID: {application_id}")

        print(f"Uploading resume for {application_id}...")
        resume_url, upload_error = upload_resume_to_r2(resume_file, application_id)
        if upload_error:
            return jsonify({'success': False, 'error': f'File upload failed: {upload_error}'}), 500
        
        application_data = {
            'applicationId': application_id,
            'jobId': form_data.get('jobId'),
            'applicantName': form_data.get('applicantName'),
            'primaryEmail': form_data.get('primaryEmail'),
            'secondaryEmail': user_email_from_session,
            'experience': form_data.get('experience'),
            'workType': form_data.get('workType'),
            'qualification': form_data.get('qualification'),
            'skills': form_data.get('skills'),
            'coverLetter': form_data.get('coverLetter'),
            'resumeUrl': resume_url,
            'status': 'Received',
            'submittedAt': {'.sv': 'timestamp'}
        }

        print(f"Saving application data for {application_id} to Firebase for user {user_email_from_session}...")
        db.reference(f'users/{safe_email_key}/job_applications/{application_id}').set(application_data)
        
        db.reference(f'existing_ids/job_applications/{application_id}').set(True)

        print(f"--- Application {application_id} submitted successfully for user {user_email_from_session}. ---")

        try:
            job_id_from_form = form_data.get('jobId')
            all_jobs_data = db.reference('careers/jobs').get()
            job_details = None
            if all_jobs_data:
                for job_key, job_info in all_jobs_data.items():
                    if str(job_info.get('id')) == str(job_id_from_form):
                        job_details = job_info
                        break
            if job_details:
                send_application_confirmation_email(
                    receiver_email=application_data.get('primaryEmail'),
                    name=application_data.get('applicantName'),
                    application_data=application_data,
                    job_details=job_details
                )
            else:
                print(f"Warning: Could not find job details for jobId '{job_id_from_form}' to send confirmation email.")
        except Exception as email_error:
            print(f"Error sending job application confirmation email: {email_error}")
        
        return jsonify({
            'success': True, 
            'applicationId': application_id
        })

    except Exception as e:
        print(f"[submit_application] An unexpected error occurred: {e}")
        return jsonify({'success': False, 'error': 'An internal server error occurred. Please try again later.'}), 500

@app.route('/get_my_applications')
def get_my_applications():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Authentication required.'}), 401

    try:
        user_email = session.get('user_email')
        safe_email_key = user_email.replace('.', '_')
        
        user_applications_ref = db.reference(f'users/{safe_email_key}/job_applications')
        applications_data = user_applications_ref.get()

        if not applications_data:
            return jsonify({'success': True, 'applications': []})

        applications_list = sorted(list(applications_data.values()), key=lambda x: x.get('submittedAt', 0), reverse=True)
        
        return jsonify({'success': True, 'applications': applications_list})
    except Exception as e:
        print(f"[get_my_applications] Error: {e}")
        return jsonify({'success': False, 'error': 'Could not retrieve your applications.'}), 500

@app.route('/withdraw_application', methods=['POST'])
def withdraw_application():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Authentication required.'}), 401

    try:
        data = request.get_json()
        application_id = data.get('applicationId')
        if not application_id:
            return jsonify({'success': False, 'error': 'Application ID is required.'}), 400

        user_email = session.get('user_email')
        safe_email_key = user_email.replace('.', '_')

        app_ref = db.reference(f'users/{safe_email_key}/job_applications/{application_id}')
        application_data = app_ref.get()

        if not application_data:
            return jsonify({'success': False, 'error': 'Application not found or you do not have permission to modify it.'}), 404

        success, error = delete_resume_from_r2(application_id)
        if not success:
            print(f"Could not delete resume from R2 for {application_id}: {error}")

        print(f"Deleting application {application_id} from Firebase...")
        app_ref.delete()
        db.reference(f'existing_ids/job_applications/{application_id}').delete()
        
        print(f"--- Application {application_id} successfully withdrawn by {user_email}. ---")
        return jsonify({'success': True, 'message': 'Application withdrawn successfully.'})

    except Exception as e:
        print(f"[withdraw_application] Error: {e}")
        return jsonify({'success': False, 'error': 'An internal server error occurred.'}), 500


@app.route('/request_otp', methods=['POST'])
def request_otp():
    data = request.get_json()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    if not email or not validate_email(email):
        return jsonify({'success': False, 'error': 'Invalid email', 'field_error': 'email'}), 400
    if not phone or not validate_phone(phone):
        return jsonify({'success': False, 'error': 'Invalid phone', 'field_error': 'phone'}), 400
    safe_email_key = email.replace('.', '_')
    user_ref = db.reference('users').child(safe_email_key)
    if user_ref.get() is not None:
        return jsonify({'success': False, 'error': 'User Already exists'}), 400
    otp = str(random.randint(100000, 999999))
    session.permanent = True
    session['otp'] = otp
    session['email'] = email
    session['phone'] = phone
    if send_otp_email(email, otp):
        return jsonify({'success': True, 'message': 'OTP sent to email'})
    else:
        return jsonify({'success': False, 'error': 'Failed to send OTP. Please try again later.'}), 500

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    entered_otp = data.get('otp', '').strip()
    actual_otp = session.get('otp')
    email = session.get('email')
    if not email or not actual_otp or entered_otp != actual_otp:
        return jsonify({'success': False, 'error': 'Incorrect OTP or session expired.', 'field_error': 'otp'}), 400
    return jsonify({'success': True, 'message': 'OTP verified!'})

@app.route('/save_user_data', methods=['POST'])
def save_user_data():
    data = request.get_json()
    email = session.get('email')
    phone = session.get('phone')
    if not email or not phone:
        return jsonify({'success': False, 'error': 'Session expired. Please start over.'}), 400
    data['email'] = email
    data['phone'] = phone
    required_fields = ['name', 'organization', 'email', 'phone', 'country', 'state', 'district', 'address', 'pincode']
    for field in required_fields:
        value = data.get(field, '').strip() if isinstance(data.get(field), str) else data.get(field)
        if not value:
            return jsonify({'success': False, 'error': f'Field "{field}" is required', 'field_error': field}), 400
    try:
        safe_email_key = email.replace('.', '_')
        if db.reference('users').child(safe_email_key).get() is not None:
            return jsonify({'success': False, 'error': 'User already exists.'}), 400
        user_data = {
            'email': email, 'phone': phone, 'name': data['name'], 'organization': data['organization'],
            'country': data['country'], 'state': data['state'], 'district': data['district'],
            'address': data['address'], 'pincode': data['pincode'],
            'orders': 0, 'cart_items': [], 'created_at': {'.sv': 'timestamp'}
        }
        db.reference('users').child(safe_email_key).set(user_data)
        send_account_created_email(email, data['name'])
        return jsonify({'success': True, 'message': 'Profile completed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to save profile. Please try again.'}), 500

@app.route('/login_check', methods=['POST'])
def login_check():
    data = request.get_json()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    if not email or not validate_email(email):
        return jsonify({'success': False, 'error': "Invalid email"}), 400
    if not phone or not validate_phone(phone):
        return jsonify({'success': False, 'error': "Invalid phone"}), 400
    safe_email_key = email.replace('.', '_')
    user_data = db.reference('users').child(safe_email_key).get()
    if not user_data:
        return jsonify({'success': False, 'error': "Account doesn't exist"}), 404
    stored_phone = str(user_data.get('phone', '')).replace(' ', '').replace('-', '')
    input_phone = phone.replace(' ', '').replace('-', '')
    if not (stored_phone.endswith(input_phone[-10:]) and len(input_phone) >= 10):
        return jsonify({'success': False, 'error': "Phone number doesn't match with the records"}), 401
    otp = str(random.randint(100000, 999999))
    session.permanent = True
    session['otp'] = otp
    session['email'] = email
    session['phone'] = stored_phone
    if send_otp_email(email, otp):
        return jsonify({'success': True, 'message': 'OTP sent to email for login verification'})
    else:
        return jsonify({'success': False, 'error': 'Failed to send OTP. Please try again later.'}), 500

@app.route('/verify_login_otp', methods=['POST'])
def verify_login_otp():
    data = request.get_json()
    entered_otp = data.get('otp', '').strip()
    actual_otp = session.get('otp')
    email = session.get('email')
    if not email or not actual_otp or entered_otp != actual_otp:
        return jsonify({'success': False, 'error': 'Incorrect OTP or session expired.'}), 400

    session['logged_in'] = True
    session['user_email'] = email
    safe_email_key_as_uid = email.replace('.', '_')

    try:
        user_ref = db.reference(f'users/{safe_email_key_as_uid}')
        user_data = user_ref.get()
        if user_data:
            order_history = user_ref.child('order_details/order_history').get()
            actual_order_count = len(order_history) if order_history else 0
            stored_order_count = user_data.get('orders', 0)
            if actual_order_count != stored_order_count:
                user_ref.child('orders').set(actual_order_count)
                print(f"Order count for {email} synchronized from {stored_order_count} to {actual_order_count}.")
    except Exception as e:
        print(f"Error synchronizing order count for {email}: {e}")

    try:
        custom_token = auth.create_custom_token(safe_email_key_as_uid, {'email': email})
    except Exception as e:
        return jsonify({'success': False, 'error': 'Authentication failed on server.'}), 500

    session.pop('otp', None)
    session.pop('phone', None)
    return jsonify({
        'success': True, 'message': 'Login successful!',
        'redirect_url': url_for('user_dashboard_page'),
        'token': custom_token.decode('utf-8')
    })

@app.route('/user_dashboard.html')
def user_dashboard_page():
    if not session.get('logged_in'):
        return redirect(url_for('login_page'))
    email = session.get('user_email')
    return render_template('user_dashboard.html', user_email=email)

@app.route('/get_products')
def get_products():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Authentication required.'}), 401
    try:
        stock_ref = db.reference('stockitems')
        products = stock_ref.get()
        if not products:
            return jsonify({'success': True, 'products': []})
        
        product_list = []
        for product_id, product_data in products.items():
            product_data['id'] = product_id 
            product_list.append(product_data)
            
        return jsonify({'success': True, 'products': product_list})
    except Exception as e:
        print(f"Error fetching products from DB: {e}")
        return jsonify({'success': False, 'error': 'Could not retrieve product data.'}), 500


@app.route('/get_current_stocks')
def get_current_stocks():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Authentication required.'}), 401
    try:
        stock_ref = db.reference('stockitems')
        products = stock_ref.get()
        if products:
            stocks = {pid: pdata.get('availableStock') for pid, pdata in products.items()}
            return jsonify({'success': True, 'stocks': stocks})
        return jsonify({'success': True, 'stocks': {}})
    except Exception as e:
        print(f"Error fetching stocks from DB: {e}")
        return jsonify({'success': False, 'error': 'Could not retrieve stock data.'}), 500

@app.route('/update_cart_db', methods=['POST'])
def update_cart_db_route():
    data = request.get_json()
    user_email = data.get('user_email')
    cart_items = data.get('cart_items', [])
    if not user_email or not isinstance(cart_items, list):
        return jsonify({'success': False, 'error': 'Invalid request data.'}), 400
    if update_cart_in_db(user_email, cart_items):
        return jsonify({'success': True, 'message': 'Cart updated in database.'})
    else:
        return jsonify({'success': False, 'error': 'Failed to update cart in database.'}), 500

@app.route('/place_order', methods=['POST'])
def place_order():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'User not logged in.'}), 401

    user_email = session.get('user_email')
    data = request.get_json()
    selected_address_id = data.get('address_id')

    if not selected_address_id:
        return jsonify({'success': False, 'error': 'Shipping address ID is required.'}), 400

    safe_email_key = user_email.replace('.', '_')
    user_ref = db.reference(f'users/{safe_email_key}')
    stock_ref = db.reference('stockitems')

    try:
        user_data = user_ref.get()
        if not user_data:
            return jsonify({'success': False, 'error': 'User not found.'}), 404

        cart_items = user_data.get('cart_items', [])
        if not cart_items:
            return jsonify({'success': False, 'error': 'Your cart is empty.'}), 400
            
        shipping_address = user_data.get('order_details', {}).get('shipping_address', {}).get(selected_address_id)
        if not shipping_address:
            return jsonify({'success': False, 'error': 'Invalid shipping address selected.'}), 400

        all_products_from_db = stock_ref.get()
        if not all_products_from_db:
            return jsonify({'success': False, 'error': 'Could not verify product catalog.'}), 500

        validated_cart = []
        adjustments_made = []
        cart_was_modified = False

        for item in cart_items:
            product_id = str(item['id'])
            product_in_db = all_products_from_db.get(product_id)
            
            if not product_in_db:
                adjustments_made.append(f"'{item.get('name', 'An item')}' was removed as it is no longer available.")
                cart_was_modified = True
                continue

            current_stock = product_in_db.get('availableStock', 0)
            
            if current_stock <= 0:
                adjustments_made.append(f"'{item['name']}' was removed as it is now out of stock.")
                cart_was_modified = True
                continue

            if item['quantity'] > current_stock:
                adjustments_made.append(f"Quantity for '{item['name']}' reduced to {current_stock} due to low stock.")
                item['quantity'] = current_stock
                cart_was_modified = True
            
            validated_cart.append(item)
        
        if cart_was_modified:
            user_ref.child('cart_items').set(validated_cart)
            error_message = "Your cart has been updated due to stock changes. Please review and proceed. " + " ".join(adjustments_made)
            return jsonify({
                'success': False, 
                'error': error_message,
                'cart_updated': True,
                'updated_cart': validated_cart
            }), 409

        total_price = 0
        order_items_details = []
        stock_updates = {}

        for item in validated_cart:
            product_id, quantity = str(item['id']), item['quantity']
            product_in_db = all_products_from_db.get(product_id)
            
            total_price += product_in_db['price'] * quantity
            order_items_details.append({
                'id': product_id, 'name': product_in_db['name'], 'price': product_in_db['price'],
                'quantity': quantity, 'image': product_in_db['image'], 'description': product_in_db.get('description', 'N/A')
            })
            stock_updates[f'{product_id}/availableStock'] = product_in_db['availableStock'] - quantity

        if not order_items_details:
            return jsonify({'success': False, 'error': 'All items in your cart are out of stock.'}), 400

        order_id = generate_unique_id('ORD', 'orders')
        invoice_id = generate_unique_id('INV', 'invoices')
        order_status = random.choice(["Shipped", "Out for Delivery", "Delivered"])

        order_data = {
            'orderId': order_id, 'invoiceId': invoice_id,
            'orderDate': {'.sv': 'timestamp'}, 'status': order_status,
            'items': order_items_details, 'shippingAddress': shipping_address,
            'totalAmount': total_price
        }

        if order_status == "Delivered":
            order_data['deliveryDate'] = datetime.now().strftime('%d-%b-%Y')

        updates = {
            f'users/{safe_email_key}/order_details/order_history/{order_id}': order_data,
            f'users/{safe_email_key}/cart_items': [],
            f'users/{safe_email_key}/orders': user_data.get('orders', 0) + 1,
            f'existing_ids/orders/{order_id}': True,
            f'existing_ids/invoices/{invoice_id}': True
        }
        db.reference().update(updates)
        stock_ref.update(stock_updates)

        print(f"--- Order {order_id} placed for {user_email}. Stock updated. ---")

        try:
            user_name = user_data.get('name', 'Valued Customer')
            send_order_confirmation_email(user_email, user_name, order_data)
        except Exception as email_error:
            print(f"Error sending order confirmation email: {email_error}")

        return jsonify({
            'success': True, 'message': 'Order placed successfully!',
            'orderId': order_id, 'invoiceId': invoice_id
        })
    except Exception as e:
        print(f"[place_order] Error: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred while placing your order.'}), 500

@app.route('/request_stock_notification', methods=['POST'])
def request_stock_notification():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Authentication required.'}), 401
    
    user_email = session.get('user_email')
    data = request.get_json()
    product_id = data.get('productId')

    if not product_id:
        return jsonify({'success': False, 'error': 'Product ID is missing.'}), 400

    try:
        def add_user_to_notification_list(current_data):
            if current_data is None:
                current_data = {}
            current_data[user_email.replace('.', '_')] = True
            return current_data

        notification_ref = db.reference(f'stock_notifications/{product_id}')
        notification_ref.transaction(add_user_to_notification_list)
        
        print(f"User {user_email} registered for stock notification for product {product_id}.")
        return jsonify({'success': True, 'message': 'Notification request received.'})

    except Exception as e:
        print(f"Error in request_stock_notification: {e}")
        return jsonify({'success': False, 'error': 'Could not process notification request.'}), 500

def handle_stock_notifications(restocked_products):
    print(f"Handling notifications for {len(restocked_products)} restocked items.")
    notifications_ref = db.reference('stock_notifications')
    all_notifications = notifications_ref.get()

    if not all_notifications:
        return

    user_notifications = {} 

    for product in restocked_products:
        product_id = product['id']
        if product_id in all_notifications:
            users_to_notify = all_notifications[product_id]
            for safe_email_key in users_to_notify.keys():
                user_email = safe_email_key.replace('_', '.')
                if user_email not in user_notifications:
                    user_notifications[user_email] = []
                user_notifications[user_email].append(product)
    
    if not user_notifications:
        return

    all_users_data = db.reference('users').get()
    paths_to_delete = {}
    
    for user_email, products_to_notify in user_notifications.items():
        safe_email_key = user_email.replace('.', '_')
        user_data = all_users_data.get(safe_email_key)
        user_name = user_data.get('name', 'Valued Customer') if user_data else 'Valued Customer'
        
        send_stock_notification_email(user_email, user_name, products_to_notify)
        
        for product in products_to_notify:
            paths_to_delete[f'stock_notifications/{product["id"]}/{safe_email_key}'] = None

    if paths_to_delete:
        db.reference().update(paths_to_delete)
        print(f"Cleared {len(paths_to_delete)} sent stock notifications from the database.")


@app.route('/request_return', methods=['POST'])
def request_return():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'User not logged in.'}), 401

    user_email = session.get('user_email')
    try:
        order_id = request.form.get('orderId')
        reason = request.form.get('reason')
        address_info = json.loads(request.form.get('addressInfo'))
        contact_info = json.loads(request.form.get('contactInfo'))
        video_file = request.files.get('videoFile')
    except (json.JSONDecodeError, TypeError):
        return jsonify({'success': False, 'error': 'Malformed request data.'}), 400

    if not all([order_id, reason, address_info, contact_info, video_file]):
        return jsonify({'success': False, 'error': 'Incomplete return request data.'}), 400

    safe_email_key = user_email.replace('.', '_')
    user_ref = db.reference(f'users/{safe_email_key}')
    order_ref = user_ref.child(f'order_details/order_history/{order_id}')

    try:
        user_data_snapshot = user_ref.get()
        if not user_data_snapshot: return jsonify({'success': False, 'error': 'User not found.'}), 404
        user_name = user_data_snapshot.get('name', 'AnonymousUser')
        
        order_data = order_ref.get()
        if not order_data: return jsonify({'success': False, 'error': 'Order not found.'}), 404
        
        current_status = order_data.get('status')
        if current_status in ['Return Requested', 'Returned']:
            return jsonify({'success': False, 'error': f'Return already processed. Status: {current_status}'}), 400
        if current_status != 'Delivered':
            return jsonify({'success': False, 'error': 'Only delivered items can be returned.'}), 400

        delivery_date_str = order_data.get('deliveryDate')
        if not delivery_date_str: return jsonify({'success': False, 'error': 'Delivery date not found.'}), 400
        
        delivery_date = datetime.strptime(delivery_date_str, '%d-%b-%Y')
        if datetime.now() - delivery_date > timedelta(days=15):
            return jsonify({'success': False, 'error': 'The 15-day return window has expired.'}), 400

        return_address = {}
        if address_info.get('type') == 'same':
            return_address = order_data.get('shippingAddress', {})
        else:
            return_address = address_info.get('customAddress', {})
        
        return_contact = ""
        if contact_info.get('type') == 'same':
            return_contact = order_data.get('shippingAddress', {}).get('phone', '')
        else:
            return_contact = contact_info.get('customContact', '')

        return_invoice_id = generate_unique_id('RET', 'returns')
        video_url, upload_error = upload_video_to_r2(video_file, user_name, return_invoice_id)
        if upload_error:
            return jsonify({'success': False, 'error': f'Video upload failed: {upload_error}'}), 500

        return_details = {
            'reason': reason, 'videoUrl': video_url,
            'pickupAddress': return_address, 'pickupContact': return_contact,
            'requestedAt': {'.sv': 'timestamp'}
        }
        
        updates = {
            f'status': "Return Requested",
            f'returnInvoiceId': return_invoice_id,
            f'returnDetails': return_details
        }
        order_ref.update(updates)
        db.reference(f'existing_ids/returns/{return_invoice_id}').set(True)

        print(f"--- Return requested for Order {order_id} by {user_email}. Return ID: {return_invoice_id} ---")
        
        try:
            updated_order_data_for_email = order_data.copy()
            updated_order_data_for_email['status'] = "Return Requested"
            updated_order_data_for_email['returnInvoiceId'] = return_invoice_id
            updated_order_data_for_email['returnDetails'] = return_details
            send_return_request_email(user_email, user_name, updated_order_data_for_email)
        except Exception as email_error:
            print(f"Error sending return request confirmation email: {email_error}")

        return jsonify({
            'success': True, 'message': 'Return requested successfully!',
            'newStatus': "Return Requested", 'returnInvoiceId': return_invoice_id
        })

    except Exception as e:
        print(f"[request_return] Error: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred.'}), 500


# --- ROUTES FOR ON-DEMAND INVOICE GENERATION ---
@app.route('/download_invoice/<order_id>')
def download_invoice(order_id):
    if not session.get('logged_in'): return "Access Denied", 401
    user_email = session.get('user_email')
    safe_email_key = user_email.replace('.', '_')
    try:
        user_ref = db.reference(f'users/{safe_email_key}')
        user_data = user_ref.get()
        order_data = user_ref.child(f'order_details/order_history/{order_id}').get()
        if not user_data or not order_data: return "Order not found.", 404
        buffer = io.BytesIO()
        create_modern_invoice(order_data, user_data, buffer, title="Tax Invoice")
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"NILA-Invoice-{order_data.get('invoiceId', order_id)}.pdf", mimetype='application/pdf')
    except Exception as e:
        print(f"Error generating invoice for order {order_id}: {e}")
        return "Failed to generate invoice.", 500

@app.route('/download_return_invoice/<order_id>')
def download_return_invoice(order_id):
    if not session.get('logged_in'): return "Access Denied", 401
    user_email = session.get('user_email')
    safe_email_key = user_email.replace('.', '_')
    try:
        user_ref = db.reference(f'users/{safe_email_key}')
        user_data = user_ref.get()
        order_data = user_ref.child(f'order_details/order_history/{order_id}').get()
        if not user_data or not order_data: return "Order not found.", 404
        if 'returnInvoiceId' not in order_data or order_data.get('status') not in ['Return Requested', 'Returned']:
            return "No return invoice exists for this order.", 404
        buffer = io.BytesIO()
        create_modern_invoice(order_data, user_data, buffer, title="Return Invoice")
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"NILA-Return-Invoice-{order_data.get('returnInvoiceId')}.pdf", mimetype='application/pdf')
    except Exception as e:
        print(f"Error generating return invoice for order {order_id}: {e}")
        return "Failed to generate return invoice.", 500


@app.route('/logout')
def logout():
    log_user_out_and_print_message()
    return redirect(url_for('cover_page'))

@app.route('/beacon_logout', methods=['POST'])
def beacon_logout():
    log_user_out_and_print_message()
    return '', 204

if __name__ == '__main__':
    with app.app_context():
        setup_database()
        setup_careers_database() 
    app.run(host='0.0.0.0', port=5000, debug=True)