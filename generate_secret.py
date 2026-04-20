import pyotp

input("Press Enter to generate your secret key...")
secret = pyotp.random_base32()
print(f"Your secret: {secret}")