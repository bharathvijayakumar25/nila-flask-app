import firebase_admin
from firebase_admin import credentials, db

# Initialize Firebase with your service account
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://nila-products-default-rtdb.firebaseio.com/'
})

# Take username (e.g., phone number) as input
username = input("Enter phone number (username): ")

# Create user with default 'orders' set to 0
ref = db.reference('users')
ref.child(username).set({
    'orders': 0
})

print(f"User '{username}' created with orders = 0.")
