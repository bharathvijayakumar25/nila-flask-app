import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import os
import sys
from dotenv import load_dotenv  # <-- 1. ADD THIS IMPORT

load_dotenv()  # <-- 2. ADD THIS LINE TO LOAD THE .env FILE

# --- Cloudflare R2 Configuration (Loaded from Environment) ---
# These values are now securely loaded from your .env file
R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')

# --- Local File to Upload ---
LOCAL_FILE_PATH = "design.mp4" 

# --- Destination in R2 ---
OBJECT_KEY = "standalone_test_upload.mp4"   


def test_r2_upload(local_file, bucket_name, object_key):
    """
    Tests uploading a single local file to Cloudflare R2.
    """
    print("--- R2 Upload Test Initialized ---")
    
    # 1. Initialize the S3 client for R2
    try:
        endpoint = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
        
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name='auto'
        )
        print("✅ S3 client initialized successfully.")
    except Exception as e:
        print(f"❌ Error initializing S3 client: {e}")
        return

    # 2. Check if the local file exists
    if not os.path.exists(local_file):
        print(f"❌ FAILED: The source file '{local_file}' was not found.")
        print("Please update the LOCAL_FILE_PATH variable in the script.")
        return
    print(f"✅ Source file found at: {local_file}")

    # 3. Perform the upload
    print(f"\nAttempting to upload to bucket '{bucket_name}' as '{object_key}'...")
    try:
        s3_client.upload_file(
            local_file,
            bucket_name,
            object_key,
            ExtraArgs={'ContentType': 'video/mp4'}
        )
        print("\n🎉 SUCCESS! File uploaded successfully to R2.")
        print(f"   Bucket: {bucket_name}")
        print(f"   Object Key: {object_key}")

    except ClientError as e:
        print(f"\n❌ FAILED: A client error occurred: {e}")
        if "SSL" in str(e):
             print("\n💡 This could be an SSL/TLS Handshake Failure. Try upgrading libraries:")
             print("   pip install --upgrade boto3 botocore certifi requests")
             
    except NoCredentialsError:
        print("\n❌ FAILED: Credentials not available or incorrect.")
    
    except Exception as e:
        print(f"\n❌ FAILED: An unexpected error occurred: {e}")

# --- Main execution block ---
if __name__ == "__main__":
    # Check if all required environment variables are loaded successfully.
    required_vars = [R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME]
    if not all(required_vars):
        print("❌ FAILED: One or more required environment variables are not set.")
        print("   Please check your .env file or environment settings for:")
        print("   - R2_ACCOUNT_ID")
        print("   - R2_ACCESS_KEY_ID")
        print("   - R2_SECRET_ACCESS_KEY")
        print("   - R2_BUCKET_NAME")
        sys.exit(1) # Exit the script with an error code

    test_r2_upload(LOCAL_FILE_PATH, R2_BUCKET_NAME, OBJECT_KEY)