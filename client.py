import socket

# ── Helpers de comunicación ──────────────────────────────────────────────

def enviar(sock, msg: str):
    sock.sendall((msg + "\n").encode())

def recibir(sock) -> str:
    datos = b""
    while not datos.endswith(b"\n"):
        fragmento = sock.recv(4096)
        if not fragmento:
            raise ConnectionError("Servidor desconectado.")
        datos += fragmento
    return datos.decode().strip()

def recibir_bloque(sock) -> str:
    lineas = []
    while True:
        linea = recibir(sock)
        if linea == "%%FIN%%":
            break
        lineas.append(linea)
    return "\n".join(lineas)

# ── Autenticación ────────────────────────────────────────────────────────

def autenticar(sock) -> str:
    """
    Envía credenciales al servidor y retorna el nombre del usuario
    si la autenticación es exitosa.
    """
    print("¡Bienvenido a la plataforma de servicio al cliente de la tienda TC5G!")
    print("Para autenticarse ingrese su mail y contraseña:")

    while True:
        usuario = input("usuario: ").strip()
        contrasena = input("contraseña: ").strip()

        enviar(sock, f"AUTH {usuario} {contrasena}")
        respuesta = recibir(sock)

        if respuesta.startswith("AUTH_OK"):
            nombre = respuesta.split(" ", 1)[1]
            return nombre
        else:
            print(f"Asistente: {respuesta}\n")

# ── Submenús ─────────────────────────────────────────────────────────────

def menu_cambio_clave(sock, usuario):
    nueva = input("Ingrese su nueva contraseña: ")
    enviar(sock, f"CAMBIAR_CLAVE {nueva}")
    confirmar = input("Ingrese su nueva contraseña nuevamente: ")
    enviar(sock, f"CONFIRMAR_CLAVE {confirmar}")
    print(f"Asistente: {recibir(sock)}")

def menu_historial(sock, usuario):
    enviar(sock, "VER_HISTORIAL")
    print(f"Asistente:\n{recibir_bloque(sock)}")
    opcion = input("¿Desea ver más detalles de alguno? (0 = No): ").strip()
    enviar(sock, f"DETALLE_HISTORIAL {opcion}")
    if opcion != "0":
        print(f"Asistente:\n{recibir_bloque(sock)}")

def menu_catalogo(sock, usuario):
    enviar(sock, "VER_CATALOGO")
    print(f"Asistente: Catálogo disponible:\n{recibir_bloque(sock)}")
    producto = input("Ingrese el nombre del producto a comprar (0 = Cancelar): ").strip()
    if producto == "0":
        enviar(sock, "COMPRA_CANCELADA")
        return
    cantidad = input("Ingrese la cantidad: ").strip()
    enviar(sock, f"COMPRAR {producto} {cantidad}")
    print(f"Asistente: {recibir(sock)}")

def menu_devolucion(sock, usuario):
    enviar(sock, "VER_HISTORIAL")
    print(f"Asistente: Sus compras:\n{recibir_bloque(sock)}")
    opcion = input("Ingrese el número de operación a devolver (0 = Cancelar): ").strip()
    if opcion == "0":
        enviar(sock, "DEVOLUCION_CANCELADA")
        return
    enviar(sock, f"DEVOLVER {opcion}")
    print(f"Asistente: {recibir(sock)}")

def menu_confirmar_envio(sock, usuario):
    enviar(sock, "VER_ENVIOS_PENDIENTES")
    print(f"Asistente: Envíos pendientes:\n{recibir_bloque(sock)}")
    opcion = input("Ingrese el número de envío a confirmar (0 = Cancelar): ").strip()
    if opcion == "0":
        enviar(sock, "CONFIRMACION_CANCELADA")
        return
    enviar(sock, f"CONFIRMAR_ENVIO {opcion}")
    print(f"Asistente: {recibir(sock)}")

def menu_ejecutivo(sock, usuario):
    enviar(sock, "SOLICITAR_EJECUTIVO")
    print("Asistente: Estás en la cola de espera, aguarda un momento...")
    while True:
        msg = recibir(sock)
        if msg.startswith("EJECUTIVO_CONECTADO"):
            nombre_exec = msg.split(" ", 1)[1] if " " in msg else "un ejecutivo"
            print(f"Asistente: Te atiende {nombre_exec}.")
            break
        print(f"Asistente: {msg}")
    print("(Escribe tu mensaje. El ejecutivo cerrará la sesión cuando terminen.)")
    while True:
        msg = recibir(sock)
        if msg == "EJECUTIVO_DESCONECTADO":
            print("Asistente: El ejecutivo ha finalizado la sesión.")
            break
        print(f"Ejecutivo: {msg}")
        enviar(sock, input(f"{usuario}: ").strip())

# ── Menú principal ───────────────────────────────────────────────────────

def menu_principal(sock, usuario):
    while True:
        print(f"""
Asistente: ¡Bienvenido {usuario}! ¿En qué te podemos ayudar?
[1] Cambio de contraseña.
[2] Historial de operaciones.
[3] Catálogo de productos / Comprar productos.
[4] Solicitar devolución.
[5] Confirmar envío.
[6] Contactarse con un ejecutivo.
[7] Salir""")

        opcion = input("Ingrese un número: ").strip()

        if   opcion == "1": menu_cambio_clave(sock, usuario)
        elif opcion == "2": menu_historial(sock, usuario)
        elif opcion == "3": menu_catalogo(sock, usuario)
        elif opcion == "4": menu_devolucion(sock, usuario)
        elif opcion == "5": menu_confirmar_envio(sock, usuario)
        elif opcion == "6": menu_ejecutivo(sock, usuario)
        elif opcion == "7":
            enviar(sock, "SALIR")
            print("Asistente: ¡Hasta luego!")
            break
        else:
            print("Asistente: Opción inválida, intente nuevamente.")
            continue

        continuar = input("\nAsistente: ¿Desea realizar otra operación? (1=Sí / 0=No): ").strip()
        if continuar == "0":
            enviar(sock, "SALIR")
            print("Asistente: ¡Hasta luego!")
            break

# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8002

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        nombre = autenticar(sock)
        menu_principal(sock, nombre)
