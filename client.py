import socket

# ── Helpers de comunicación ──────────────────────────────────────────────

def send(sock, msg: str):
    sock.sendall((msg + "\n").encode())

def recv(sock) -> str:
    data = b""
    while not data.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Servidor desconectado.")
        data += chunk
    return data.decode().strip()

def recv_block(sock) -> str:
    lines = []
    while True:
        line = recv(sock)
        if line == "%%END%%":
            break
        lines.append(line)
    return "\n".join(lines)

# ── Autenticación (ahora via socket) ────────────────────────────────────

def autenticar(sock) -> str:
    """
    Envía credenciales al servidor y retorna el nombre del usuario
    si la autenticación es exitosa.
    """
    print("¡Bienvenido a la plataforma de servicio al cliente de la tienda TC5G!")
    print("Para autenticarse ingrese su mail y contraseña:")

    while True:
        username = input("usuario: ").strip()
        password = input("contraseña: ").strip()

        # Enviamos usuario y contraseña al servidor
        send(sock, f"AUTH {username} {password}")
        respuesta = recv(sock)

        if respuesta.startswith("AUTH_OK"):
            # El servidor responde: AUTH_OK <nombre>
            nombre = respuesta.split(" ", 1)[1]
            return nombre
        else:
            print(f"Asistente: {respuesta}\n")   # ej: "Credenciales inválidas"

# ── Submenús ─────────────────────────────────────────────────────────────

def menu_cambio_clave(sock, username):
    nueva = input("Ingrese su nueva contraseña: ")
    send(sock, f"CHANGE_PASS {nueva}")
    confirm = input("Ingrese su nueva contraseña nuevamente: ")
    send(sock, f"CHANGE_PASS_CONFIRM {confirm}")
    print(f"Asistente: {recv(sock)}")

def menu_historial(sock, username):
    send(sock, "GET_HISTORY")
    print(f"Asistente:\n{recv_block(sock)}")
    opcion = input("¿Desea ver más detalles de alguno? (0 = No): ").strip()
    send(sock, f"HISTORY_DETAIL {opcion}")
    if opcion != "0":
        print(f"Asistente:\n{recv_block(sock)}")

def menu_catalogo(sock, username):
    send(sock, "GET_CATALOGUE")
    print(f"Asistente: Catálogo disponible:\n{recv_block(sock)}")
    producto = input("Ingrese el nombre del producto a comprar (0 = Cancelar): ").strip()
    if producto == "0":
        send(sock, "BUY_CANCEL")
        return
    cantidad = input("Ingrese la cantidad: ").strip()
    send(sock, f"BUY {producto} {cantidad}")
    print(f"Asistente: {recv(sock)}")

def menu_devolucion(sock, username):
    send(sock, "GET_HISTORY")
    print(f"Asistente: Sus compras:\n{recv_block(sock)}")
    opcion = input("Ingrese el número de operación a devolver (0 = Cancelar): ").strip()
    if opcion == "0":
        send(sock, "RETURN_CANCEL")
        return
    send(sock, f"RETURN {opcion}")
    print(f"Asistente: {recv(sock)}")

def menu_confirmar_envio(sock, username):
    send(sock, "GET_PENDING_SHIPMENTS")
    print(f"Asistente: Envíos pendientes:\n{recv_block(sock)}")
    opcion = input("Ingrese el número de envío a confirmar (0 = Cancelar): ").strip()
    if opcion == "0":
        send(sock, "CONFIRM_CANCEL")
        return
    send(sock, f"CONFIRM_SHIPMENT {opcion}")
    print(f"Asistente: {recv(sock)}")

def menu_ejecutivo(sock, username):
    send(sock, "REQUEST_EXECUTIVE")
    print("Asistente: Estás en la cola de espera, aguarda un momento...")
    while True:
        msg = recv(sock)
        if msg.startswith("EXEC_CONNECTED"):
            exec_name = msg.split(" ", 1)[1] if " " in msg else "un ejecutivo"
            print(f"Asistente: Te atiende {exec_name}.")
            break
        print(f"Asistente: {msg}")
    print("(Escribe tu mensaje. El ejecutivo cerrará la sesión cuando terminen.)")
    while True:
        msg = recv(sock)
        if msg == "EXEC_DISCONNECT":
            print("Asistente: El ejecutivo ha finalizado la sesión.")
            break
        print(f"Ejecutivo: {msg}")
        send(sock, input(f"{username}: ").strip())

# ── Menú principal ───────────────────────────────────────────────────────

def menu_principal(sock, username):
    while True:
        print(f"""
Asistente: ¡Bienvenido {username}! ¿En qué te podemos ayudar?
[1] Cambio de contraseña.
[2] Historial de operaciones.
[3] Catálogo de productos / Comprar productos.
[4] Solicitar devolución.
[5] Confirmar envío.
[6] Contactarse con un ejecutivo.
[7] Salir""")

        opcion = input("Ingrese un número: ").strip()

        if   opcion == "1": menu_cambio_clave(sock, username)
        elif opcion == "2": menu_historial(sock, username)
        elif opcion == "3": menu_catalogo(sock, username)
        elif opcion == "4": menu_devolucion(sock, username)
        elif opcion == "5": menu_confirmar_envio(sock, username)
        elif opcion == "6": menu_ejecutivo(sock, username)
        elif opcion == "7":
            send(sock, "LOGOUT")
            print("Asistente: ¡Hasta luego!")
            break
        else:
            print("Asistente: Opción inválida.")
            continue

        continuar = input("\nAsistente: ¿Desea realizar otra operación? (1=Sí / 0=No): ").strip()
        if continuar == "0":
            send(sock, "LOGOUT")
            print("Asistente: ¡Hasta luego!")
            break

# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 9000

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        nombre = autenticar(sock)          # 1) Auth via socket
        menu_principal(sock, nombre)       # 2) Menú de servicios
