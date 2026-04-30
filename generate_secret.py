import qrcode

# Tu clave secreta y datos
secret = "MRZXNFPPAD3HQKHJGQAMK4WJDOLV4IVR"
account_name = "Mi_Cuenta"  # Cambia esto por el nombre que quieras
issuer = "Mi_Servicio"      # Cambia esto por el nombre de la plataforma

# Formato estándar de URI para aplicaciones TOTP (2FA)
otpauth_url = f"otpauth://totp/{issuer}:{account_name}?secret={secret}&issuer={issuer}"

# Generar el código QR
qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_L,
    box_size=10,
    border=4,
)
qr.add_data(otpauth_url)
qr.make(fit=True)

# Guardar la imagen localmente
img = qr.make_image(fill_color="black", back_color="white")
img.save("mi_codigo_2fa.png")

print("Código QR generado y guardado como 'mi_codigo_2fa.png'. ¡Mantenlo seguro!")