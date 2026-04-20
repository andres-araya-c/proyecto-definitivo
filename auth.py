import json
import pyotp

with open("accounts.json") as f:
    accounts = json.load(f)

username = input("Username: ")
password = input("Password: ")
code     = input("2FA Code: ")

account = next((a for a in accounts if a["username"] == username), None)

if not account:
    print("Authentication failed")
elif account["password"] != password:
    print("Authentication failed")
elif not pyotp.TOTP(account["secret"]).verify(code, valid_window=1):
    print("Authentication failed")
else:
    print(f"Authentication successful! Welcome, {account['name']}.")
