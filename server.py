import socket
import threading
import json
import datetime

# ── Cargar base de datos ─────────────────────────────────────────────────

with open("accounts.json") as f:
    accounts = json.load(f)

# Catálogo de ejemplo (puedes moverlo a un catalogue.json si prefieres)
catalogue = {
    "Pikachu ex":            {"price": 15000, "stock": 5},
    "Metapod ex":            {"price": 8000,  "stock": 3},
    "Sobre Brilliant Stars": {"price": 5000,  "stock": 20},
    "Caterpie":              {"price": 2000,  "stock": 10},
}

# Cola de clientes esperando ejecutivo
waiting_queue = []
queue_lock    = threading.Lock()
stock_lock    = threading.Lock()

# ── Helpers de comunicación ──────────────────────────────────────────────

def send(conn, msg: str):
    conn.sendall((msg + "\n").encode())

def send_block(conn, lines: list):
    for line in lines:
        send(conn, line)
    send(conn, "%%END%%")

def recv(conn) -> str:
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(4096)
        if not chunk:
            raise ConnectionError("Cliente desconectado.")
        data += chunk
    return data.decode().strip()

# ── Autenticación ────────────────────────────────────────────────────────

def handle_auth(conn) -> dict | None:
    """
    Espera mensajes AUTH <username> <password> hasta que sean correctos.
    Retorna el dict de la cuenta autenticada, o None si el cliente se desconecta.
    """
    while True:
        msg = recv(conn)                        # "AUTH usuario contraseña"

        if not msg.startswith("AUTH "):
            send(conn, "Formato inválido. Use: AUTH <usuario> <contraseña>")
            continue

        partes = msg.split(" ", 2)
        if len(partes) < 3:
            send(conn, "Credenciales incompletas.")
            continue

        _, username, password = partes
        account = next((a for a in accounts if a["username"] == username), None)

        if not account or account["password"] != password:
            send(conn, "Credenciales inválidas. Intente nuevamente.")
            continue

        # Autenticación exitosa
        send(conn, f"AUTH_OK {account['name']}")
        print(f"[SERVIDOR] Cliente {account['name']} conectado.")
        return account

# ── Handlers de cada opción ──────────────────────────────────────────────

def handle_change_pass(conn, account, nueva_clave):
    confirm_msg = recv(conn)
    confirm_clave = confirm_msg.split(" ", 1)[1] if " " in confirm_msg else ""

    if nueva_clave != confirm_clave:
        send(conn, "Las contraseñas no coinciden. Intente nuevamente.")
        return

    account["password"] = nueva_clave
    # Persistir cambio en accounts.json
    with open("accounts.json", "w") as f:
        json.dump(accounts, f, indent=4, ensure_ascii=False)

    send(conn, "Su clave ha sido actualizada exitosamente.")
    print(f"[SERVIDOR] Cambio Clave Cliente {account['name']}.")


def handle_get_history(conn, account):
    history = account.get("history", [])
    cutoff  = datetime.datetime.now() - datetime.timedelta(days=365)

    recientes = [
        op for op in history
        if datetime.datetime.strptime(op["date"], "%d/%m/%Y %H:%M") >= cutoff
    ]

    if not recientes:
        send_block(conn, ["No tienes operaciones en el último año."])
    else:
        lines = [f"[{i+1}] {op['type']} ({op['date']})" for i, op in enumerate(recientes)]
        send_block(conn, lines)

    return recientes


def handle_history_detail(conn, recientes):
    msg     = recv(conn)                        # "HISTORY_DETAIL <n>"
    idx_str = msg.split(" ", 1)[1] if " " in msg else "0"

    if idx_str == "0":
        send_block(conn, [""])
        return

    try:
        idx = int(idx_str) - 1
        op  = recientes[idx]
    except (ValueError, IndexError):
        send_block(conn, ["Operación inválida."])
        return

    lines = [f"[{idx+1}] {op['type']} ({op['date']})"]
    for item in op.get("items", []):
        lines.append(f"* {item['name']} [x{item['qty']}]")
    lines.append(f"Estado: {op['status']}")
    send_block(conn, lines)


def handle_catalogue(conn, account):
    lines = [f"* {name}: ${info['price']} (stock: {info['stock']})"
             for name, info in catalogue.items()]
    send_block(conn, lines)

    msg = recv(conn)                            # "BUY <producto> <cantidad>" o "BUY_CANCEL"
    if msg == "BUY_CANCEL":
        return

    partes = msg.split(" ", 2)
    if partes[0] != "BUY" or len(partes) < 3:
        send(conn, "Solicitud inválida.")
        return

    producto = partes[1]
    try:
        cantidad = int(partes[2])
    except ValueError:
        send(conn, "Cantidad inválida.")
        return

    with stock_lock:
        if producto not in catalogue:
            send(conn, f"'{producto}' no está en el catálogo.")
            return
        if catalogue[producto]["stock"] < cantidad:
            send(conn, f"Stock insuficiente. Disponible: {catalogue[producto]['stock']}.")
            return

        catalogue[producto]["stock"] -= cantidad

        nueva_op = {
            "id":     len(account.get("history", [])) + 1,
            "type":   "compra",
            "date":   datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "items":  [{"name": producto, "qty": cantidad}],
            "status": "Pagado"
        }
        account.setdefault("history", []).append(nueva_op)

    send(conn, f"Compra exitosa: {cantidad}x {producto}. ¡Gracias!")
    print(f"[SERVIDOR] Compra Cliente {account['name']}: {cantidad}x {producto}.")


def handle_return(conn, account):
    recientes = handle_get_history(conn, account)

    msg = recv(conn)                            # "RETURN <n>" o "RETURN_CANCEL"
    if msg == "RETURN_CANCEL":
        return

    try:
        idx = int(msg.split()[1]) - 1
        op  = recientes[idx]
    except (ValueError, IndexError):
        send(conn, "Operación inválida.")
        return

    if op["status"] not in ("Pagado", "Enviado", "Recibido"):
        send(conn, "Esta operación no puede ser devuelta.")
        return

    with stock_lock:
        for item in op.get("items", []):
            if item["name"] in catalogue:
                catalogue[item["name"]]["stock"] += item["qty"]
        op["status"] = "Devolución tramitada"

    send(conn, "Devolución solicitada exitosamente.")
    print(f"[SERVIDOR] Devolución Cliente {account['name']}.")


def handle_confirm_shipment(conn, account):
    history  = account.get("history", [])
    enviados = [op for op in history if op["status"] == "Enviado"]

    if not enviados:
        send_block(conn, ["No tienes envíos pendientes de confirmación."])
        recv(conn)      # consume CONFIRM_CANCEL del cliente
        return

    lines = [
        f"[{i+1}] {op['type']} ({op['date']}) - "
        + ", ".join(it["name"] for it in op.get("items", []))
        for i, op in enumerate(enviados)
    ]
    send_block(conn, lines)

    msg = recv(conn)                            # "CONFIRM_SHIPMENT <n>" o "CONFIRM_CANCEL"
    if msg == "CONFIRM_CANCEL":
        return

    try:
        idx = int(msg.split()[1]) - 1
        enviados[idx]["status"] = "Recibido"
        send(conn, "Envío confirmado. ¡Gracias!")
        print(f"[SERVIDOR] Confirmación envío Cliente {account['name']}.")
    except (ValueError, IndexError):
        send(conn, "Operación inválida.")


def handle_request_executive(conn, account):
    with queue_lock:
        waiting_queue.append((account, conn))
        pos = len(waiting_queue)
    send(conn, f"Estás en la posición {pos} de la cola. Espera un momento...")
    print(f"[SERVIDOR] Cliente {account['name']} en cola de espera para ejecutivo.")
    # El hilo del ejecutivo tomará control de esta conexión

# ── Dispatcher principal ─────────────────────────────────────────────────

def handle_client(conn, addr):
    try:
        account = handle_auth(conn)
        if not account:
            return

        while True:
            msg = recv(conn)

            if msg.startswith("CHANGE_PASS "):
                nueva = msg.split(" ", 1)[1]
                handle_change_pass(conn, account, nueva)

            elif msg == "GET_HISTORY":
                recientes = handle_get_history(conn, account)
                handle_history_detail(conn, recientes)

            elif msg == "GET_CATALOGUE":
                handle_catalogue(conn, account)

            elif msg == "GET_PENDING_SHIPMENTS":
                handle_confirm_shipment(conn, account)

            elif msg.startswith("RETURN"):
                handle_return(conn, account)

            elif msg == "REQUEST_EXECUTIVE":
                handle_request_executive(conn, account)
                return      # el hilo del ejecutivo toma el control

            elif msg == "LOGOUT":
                print(f"[SERVIDOR] Cliente {account['name']} desconectado.")
                break

            else:
                send(conn, "Comando no reconocido.")

    except ConnectionError:
        name = account["name"] if account else addr
        print(f"[SERVIDOR] Cliente {name} desconectado abruptamente.")
    finally:
        conn.close()

# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 9000

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(10)       # hasta 10 conexiones simultáneas
        print(f"[SERVIDOR] Escuchando en {HOST}:{PORT}...")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
