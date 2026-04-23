import json
import pyotp

print("¡Bienvenido a la plataforma de servicio al cliente de la tienda TC5G! ")
print("Para autenticarse ingrese su mail (username) y contraseña:")

with open("accounts.json") as f:
    accounts = json.load(f)

Login = False

while not Login:
    # Bucle para el usuario
    while True:
        username = input("Username: ")
        account = next((a for a in accounts if a["username"] == username), None)

        if not account:
            print("Authentication failed\n")
        else:
            break  # Usuario correcto

    # Bucle para la contraseña
    while True:
        password = input("Password: ")

        if account["password"] != password:
            print("Authentication failed\n")
        else:
            break  # Contraseña correcta

    # Solo se llega aquí con usuario y contraseña válidos
    code = input("2FA Code: ")

    if not pyotp.TOTP(account["secret"]).verify(code, valid_window=1):
        print("Authentication failed\n")
    else:
        Login = True
        print(f"Authentication successful! Welcome, {account['name']}.")