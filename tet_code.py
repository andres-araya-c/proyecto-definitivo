import json
import pyotp

with open("accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)

account = next(a for a in accounts if a["username"] == "lukrak69@example.com")

totp = pyotp.TOTP(account["secret"])
print("Código 2FA actual:", totp.now())