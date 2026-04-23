# ============================================================
#  client.py  –  PUNTO 2: Menú de servicios (agregar tras auth)
# ============================================================
# Se asume que ya tienes:
#   sock  → socket TCP conectado al servidor
#   username → nombre del cliente autenticado
#
# Helpers de comunicación -------------------------------------------------

def send(sock, msg: str):
    """Envía un mensaje terminado en newline."""
    sock.sendall((msg + "\n").encode())

def recv(sock) -> str:
    """Recibe una línea del servidor."""
    data = b""
    while not data.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Servidor desconectado.")
        data += chunk
    return data.decode().strip()

def recv_block(sock) -> str:
    """
    Recibe un bloque multilínea que el servidor termina con '%%END%%'.
    Útil para historial, catálogo, etc.
    """
    lines = []
    while True:
        line = recv(sock)
        if line == "%%END%%":
            break
        lines.append(line)
    return "\n".join(lines)

# Submenús ----------------------------------------------------------------

def menu_cambio_clave(sock, username):
    """Opción [1] Cambio de contraseña."""
    nueva = input("Ingrese su nueva contraseña: ")
    send(sock, f"CHANGE_PASS {nueva}")

    confirm = input("Ingrese su nueva contraseña nuevamente: ")
    send(sock, f"CHANGE_PASS_CONFIRM {confirm}")

    respuesta = recv(sock)
    print(f"Asistente: {respuesta}")


def menu_historial(sock, username):
    """Opción [2] Historial de operaciones."""
    send(sock, "GET_HISTORY")
    historial = recv_block(sock)
    print(f"Asistente:\n{historial}")

    opcion = input("¿Desea ver más detalles de alguno? (0 = No): ").strip()
    send(sock, f"HISTORY_DETAIL {opcion}")

    if opcion != "0":
        detalle = recv_block(sock)
        print(f"Asistente:\n{detalle}")


def menu_catalogo(sock, username):
    """Opción [3] Catálogo / Comprar productos."""
    send(sock, "GET_CATALOGUE")
    catalogo = recv_block(sock)
    print(f"Asistente: Catálogo disponible:\n{catalogo}")

    producto = input("Ingrese el nombre del producto a comprar (0 = Cancelar): ").strip()
    if producto == "0":
        send(sock, "BUY_CANCEL")
        return

    cantidad = input("Ingrese la cantidad: ").strip()
    send(sock, f"BUY {producto} {cantidad}")

    respuesta = recv(sock)
    print(f"Asistente: {respuesta}")


def menu_devolucion(sock, username):
    """Opción [4] Solicitar devolución."""
    send(sock, "GET_HISTORY")          # reutiliza historial para elegir qué devolver
    historial = recv_block(sock)
    print(f"Asistente: Sus compras:\n{historial}")

    opcion = input("Ingrese el número de operación a devolver (0 = Cancelar): ").strip()
    if opcion == "0":
        send(sock, "RETURN_CANCEL")
        return

    send(sock, f"RETURN {opcion}")
    respuesta = recv(sock)
    print(f"Asistente: {respuesta}")


def menu_confirmar_envio(sock, username):
    """Opción [5] Confirmar envío."""
    send(sock, "GET_PENDING_SHIPMENTS")
    envios = recv_block(sock)
    print(f"Asistente: Envíos pendientes de confirmación:\n{envios}")

    opcion = input("Ingrese el número de envío a confirmar (0 = Cancelar): ").strip()
    if opcion == "0":
        send(sock, "CONFIRM_CANCEL")
        return

    send(sock, f"CONFIRM_SHIPMENT {opcion}")
    respuesta = recv(sock)
    print(f"Asistente: {respuesta}")


def menu_ejecutivo(sock, username):
    """Opción [6] Contactarse con un ejecutivo."""
    send(sock, "REQUEST_EXECUTIVE")
    print("Asistente: Estás en la cola de espera, aguarda un momento...")

    # Espera hasta que el servidor indique que un ejecutivo está disponible
    while True:
        msg = recv(sock)
        if msg.startswith("EXEC_CONNECTED"):
            exec_name = msg.split(" ", 1)[1] if " " in msg else "un ejecutivo"
            print(f"Asistente: Te ha atendido {exec_name}.")
            break
        print(f"Asistente: {msg}")   # mensajes de posición en cola, etc.

    # Chat libre con el ejecutivo
    print("(Escribe tu mensaje. El ejecutivo cerrará la sesión cuando terminen.)")
    while True:
        msg = recv(sock)          # puede ser mensaje del ejecutivo o señal de cierre
        if msg == "EXEC_DISCONNECT":
            print("Asistente: El ejecutivo ha finalizado la sesión.")
            break
        print(f"Ejecutivo: {msg}")

        respuesta = input(f"{username}: ").strip()
        send(sock, respuesta)


# Bucle principal del menú ------------------------------------------------

def menu_principal(sock, username):
    """
    Punto de entrada del punto 2.
    Llama a esta función justo después de que el servidor confirme la autenticación.
    """
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

        if opcion == "1":
            menu_cambio_clave(sock, username)
        elif opcion == "2":
            menu_historial(sock, username)
        elif opcion == "3":
            menu_catalogo(sock, username)
        elif opcion == "4":
            menu_devolucion(sock, username)
        elif opcion == "5":
            menu_confirmar_envio(sock, username)
        elif opcion == "6":
            menu_ejecutivo(sock, username)
        elif opcion == "7":
            send(sock, "LOGOUT")
            print("Asistente: ¡Hasta luego!")
            break
        else:
            print("Asistente: Opción inválida, intente nuevamente.")
            continue

        # Después de cada operación el servidor pregunta si continuar
        continuar = input("Asistente: ¿Desea realizar otra operación? (1=Sí / 0=No): ").strip()
        if continuar == "0":
            send(sock, "LOGOUT")
            print("Asistente: ¡Hasta luego!")
            break
