import socket
import threading
import json
import datetime

# ── Cargar base de datos ─────────────────────────────────────────────────

with open("accounts.json", encoding="utf-8") as f:
    cuentas = json.load(f)

# Catálogo de productos
catalogo = {
    "Pikachu ex":            {"precio": 15000, "stock": 5},
    "Metapod ex":            {"precio": 8000,  "stock": 3},
    "Sobre Brilliant Stars": {"precio": 5000,  "stock": 20},
    "Caterpie":              {"precio": 2000,  "stock": 10},
}

# Cola de clientes esperando ejecutivo
cola_espera  = []
lock_cola    = threading.Lock()
lock_stock   = threading.Lock()

# ── Helpers de comunicación ──────────────────────────────────────────────

def enviar(conn, msg: str):
    conn.sendall((msg + "\n").encode())

def enviar_bloque(conn, lineas: list):
    for linea in lineas:
        enviar(conn, linea)
    enviar(conn, "%%FIN%%")

def recibir(conn) -> str:
    datos = b""
    while not datos.endswith(b"\n"):
        fragmento = conn.recv(4096)
        if not fragmento:
            raise ConnectionError("Cliente desconectado.")
        datos += fragmento
    return datos.decode().strip()

# ── Autenticación ────────────────────────────────────────────────────────

def manejar_autenticacion(conn) -> dict | None:
    """
    Espera mensajes AUTH <usuario> <contraseña> hasta que sean correctos.
    Retorna el dict de la cuenta autenticada.
    """
    while True:
        msg = recibir(conn)

        if not msg.startswith("AUTH "):
            enviar(conn, "Formato inválido. Use: AUTH <usuario> <contraseña>")
            continue

        partes = msg.split(" ", 2)
        if len(partes) < 3:
            enviar(conn, "Credenciales incompletas.")
            continue

        _, usuario, contrasena = partes
        cuenta = next((c for c in cuentas if c["username"] == usuario), None)

        if not cuenta or cuenta["password"] != contrasena:
            enviar(conn, "Credenciales inválidas. Intente nuevamente.")
            continue

        enviar(conn, f"AUTH_OK {cuenta['name']}")
        print(f"[SERVIDOR] Cliente {cuenta['name']} conectado.")
        return cuenta

# ── Handlers de cada opción ──────────────────────────────────────────────

def manejar_cambio_clave(conn, cuenta, nueva_clave):
    msg_confirmacion = recibir(conn)
    clave_confirmada = msg_confirmacion.split(" ", 1)[1] if " " in msg_confirmacion else ""

    if nueva_clave != clave_confirmada:
        enviar(conn, "Las contraseñas no coinciden. Intente nuevamente.")
        return

    cuenta["password"] = nueva_clave
    with open("accounts.json", "w", encoding="utf-8") as f:
        json.dump(cuentas, f, indent=4, ensure_ascii=False)

    enviar(conn, "Su clave ha sido actualizada exitosamente.")
    print(f"[SERVIDOR] Cambio Clave Cliente {cuenta['name']}.")


def manejar_ver_historial(conn, cuenta):
    historial  = cuenta.get("historial", [])
    hace_un_año = datetime.datetime.now() - datetime.timedelta(days=365)

    recientes = [
        op for op in historial
        if datetime.datetime.strptime(op["fecha"], "%d/%m/%Y %H:%M") >= hace_un_año
    ]

    if not recientes:
        enviar_bloque(conn, ["No tienes operaciones en el último año."])
    else:
        lineas = [f"[{i+1}] {op['tipo']} ({op['fecha']})" for i, op in enumerate(recientes)]
        enviar_bloque(conn, lineas)

    return recientes


def manejar_detalle_historial(conn, recientes):
    msg     = recibir(conn)                     # "DETALLE_HISTORIAL <n>"
    idx_str = msg.split(" ", 1)[1] if " " in msg else "0"

    if idx_str == "0":
        enviar_bloque(conn, [""])
        return

    try:
        idx = int(idx_str) - 1
        op  = recientes[idx]
    except (ValueError, IndexError):
        enviar_bloque(conn, ["Operación inválida."])
        return

    lineas = [f"[{idx+1}] {op['tipo']} ({op['fecha']})"]
    for articulo in op.get("articulos", []):
        lineas.append(f"* {articulo['nombre']} [x{articulo['cantidad']}]")
    lineas.append(f"Estado: {op['estado']}")
    enviar_bloque(conn, lineas)


def manejar_catalogo(conn, cuenta):
    lineas = [
        f"* {nombre}: ${info['precio']} (stock: {info['stock']})"
        for nombre, info in catalogo.items()
    ]
    enviar_bloque(conn, lineas)

    msg = recibir(conn)                         # "COMPRAR <producto> <cantidad>" o "COMPRA_CANCELADA"
    if msg == "COMPRA_CANCELADA":
        return

    partes = msg.split(" ", 2)
    if partes[0] != "COMPRAR" or len(partes) < 3:
        enviar(conn, "Solicitud inválida.")
        return

    producto = partes[1]
    try:
        cantidad = int(partes[2])
    except ValueError:
        enviar(conn, "Cantidad inválida.")
        return

    with lock_stock:
        if producto not in catalogo:
            enviar(conn, f"'{producto}' no está en el catálogo.")
            return
        if catalogo[producto]["stock"] < cantidad:
            enviar(conn, f"Stock insuficiente. Disponible: {catalogo[producto]['stock']}.")
            return

        catalogo[producto]["stock"] -= cantidad

        nueva_op = {
            "id":        len(cuenta.get("historial", [])) + 1,
            "tipo":      "compra",
            "fecha":     datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "articulos": [{"nombre": producto, "cantidad": cantidad}],
            "estado":    "Pagado"
        }
        cuenta.setdefault("historial", []).append(nueva_op)

    enviar(conn, f"Compra exitosa: {cantidad}x {producto}. ¡Gracias!")
    print(f"[SERVIDOR] Compra Cliente {cuenta['name']}: {cantidad}x {producto}.")


def manejar_devolucion(conn, cuenta):
    recientes = manejar_ver_historial(conn, cuenta)

    msg = recibir(conn)                         # "DEVOLVER <n>" o "DEVOLUCION_CANCELADA"
    if msg == "DEVOLUCION_CANCELADA":
        return

    try:
        idx = int(msg.split()[1]) - 1
        op  = recientes[idx]
    except (ValueError, IndexError):
        enviar(conn, "Operación inválida.")
        return

    if op["estado"] not in ("Pagado", "Enviado", "Recibido"):
        enviar(conn, "Esta operación no puede ser devuelta.")
        return

    with lock_stock:
        for articulo in op.get("articulos", []):
            if articulo["nombre"] in catalogo:
                catalogo[articulo["nombre"]]["stock"] += articulo["cantidad"]
        op["estado"] = "Devolución tramitada"

    enviar(conn, "Devolución solicitada exitosamente.")
    print(f"[SERVIDOR] Devolución Cliente {cuenta['name']}.")


def manejar_confirmar_envio(conn, cuenta):
    historial = cuenta.get("historial", [])
    enviados  = [op for op in historial if op["estado"] == "Enviado"]

    if not enviados:
        enviar_bloque(conn, ["No tienes envíos pendientes de confirmación."])
        recibir(conn)   # consume CONFIRMACION_CANCELADA del cliente
        return

    lineas = [
        f"[{i+1}] {op['tipo']} ({op['fecha']}) - "
        + ", ".join(a["nombre"] for a in op.get("articulos", []))
        for i, op in enumerate(enviados)
    ]
    enviar_bloque(conn, lineas)

    msg = recibir(conn)                         # "CONFIRMAR_ENVIO <n>" o "CONFIRMACION_CANCELADA"
    if msg == "CONFIRMACION_CANCELADA":
        return

    try:
        idx = int(msg.split()[1]) - 1
        enviados[idx]["estado"] = "Recibido"
        enviar(conn, "Envío confirmado. ¡Gracias!")
        print(f"[SERVIDOR] Confirmación envío Cliente {cuenta['name']}.")
    except (ValueError, IndexError):
        enviar(conn, "Operación inválida.")


def manejar_solicitar_ejecutivo(conn, cuenta):
    with lock_cola:
        cola_espera.append((cuenta, conn))
        posicion = len(cola_espera)
    enviar(conn, f"Estás en la posición {posicion} de la cola. Espera un momento...")
    print(f"[SERVIDOR] Cliente {cuenta['name']} en cola de espera para ejecutivo.")

# ── Dispatcher principal ─────────────────────────────────────────────────

def manejar_cliente(conn, addr):
    cuenta = None
    try:
        cuenta = manejar_autenticacion(conn)
        if not cuenta:
            return

        while True:
            msg = recibir(conn)

            if msg.startswith("CAMBIAR_CLAVE "):
                nueva = msg.split(" ", 1)[1]
                manejar_cambio_clave(conn, cuenta, nueva)

            elif msg == "VER_HISTORIAL":
                recientes = manejar_ver_historial(conn, cuenta)
                manejar_detalle_historial(conn, recientes)

            elif msg == "VER_CATALOGO":
                manejar_catalogo(conn, cuenta)

            elif msg == "VER_ENVIOS_PENDIENTES":
                manejar_confirmar_envio(conn, cuenta)

            elif msg.startswith("DEVOLVER") or msg == "DEVOLUCION_CANCELADA":
                manejar_devolucion(conn, cuenta)

            elif msg == "SOLICITAR_EJECUTIVO":
                manejar_solicitar_ejecutivo(conn, cuenta)
                return  # el hilo del ejecutivo toma el control

            elif msg == "SALIR":
                print(f"[SERVIDOR] Cliente {cuenta['name']} desconectado.")
                break

            else:
                enviar(conn, "Comando no reconocido.")

    except ConnectionError:
        nombre = cuenta["name"] if cuenta else str(addr)
        print(f"[SERVIDOR] Cliente {nombre} desconectado abruptamente.")
    finally:
        conn.close()

# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8002

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PORT))
        servidor.listen(10)
        print(f"[SERVIDOR] Escuchando en {HOST}:{PORT}...")

        while True:
            conn, addr = servidor.accept()
            threading.Thread(target=manejar_cliente, args=(conn, addr), daemon=True).start()
