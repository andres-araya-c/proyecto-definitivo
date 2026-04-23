# ============================================================
#  server.py  –  PUNTO 2: Manejador de mensajes del cliente
# ============================================================
# Se asume que ya tienes:
#   - Un hilo/función por cliente llamado handle_client(conn, addr)
#   - Una BD (dict o SQLite) con estructura:
#       users[email] = {
#           "name": str,
#           "password": str,
#           "history": [   # lista de operaciones
#               {
#                 "id": int,
#                 "type": "compra"|"venta"|"devolucion",
#                 "date": "DD/MM/YYYY HH:MM",
#                 "items": [{"name": str, "qty": int}],
#                 "status": str   # Pagado / Enviado / Recibido / etc.
#               }
#           ]
#       }
#       catalogue[nombre] = {"price": float, "stock": int}
#
# Helpers de comunicación -------------------------------------------------
import datetime
import threading

# Lock global para operaciones de stock (evitar race conditions)
stock_lock = threading.Lock()

def send(conn, msg: str):
    conn.sendall((msg + "\n").encode())

def send_block(conn, lines: list):
    """Envía múltiples líneas y cierra con %%END%%."""
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

# Manejadores de cada opción ----------------------------------------------

def handle_change_pass(conn, users, email, nueva_clave):
    """Recibe CHANGE_PASS <clave> y CHANGE_PASS_CONFIRM <clave>."""
    confirm_msg = recv(conn)                     # CHANGE_PASS_CONFIRM <clave>
    confirm_clave = confirm_msg.split(" ", 1)[1] if " " in confirm_msg else ""

    if nueva_clave != confirm_clave:
        send(conn, "Las contraseñas no coinciden. Intente nuevamente.")
        return False

    users[email]["password"] = nueva_clave
    send(conn, "Su clave ha sido actualizada exitosamente.")
    print(f"[SERVIDOR] Cambio Clave Cliente {users[email]['name']}.")
    return True


def handle_get_history(conn, users, email):
    """Envía el historial del último año."""
    history = users[email]["history"]
    cutoff = datetime.datetime.now() - datetime.timedelta(days=365)

    recientes = [
        op for op in history
        if datetime.datetime.strptime(op["date"], "%d/%m/%Y %H:%M") >= cutoff
    ]

    if not recientes:
        send_block(conn, ["No tienes operaciones en el último año."])
        return recientes

    lines = [f"[{i+1}] ({op['date']})" for i, op in enumerate(recientes)]
    send_block(conn, lines)
    return recientes


def handle_history_detail(conn, users, email, recientes):
    """Recibe HISTORY_DETAIL <n> y envía el detalle de esa operación."""
    msg = recv(conn)                             # HISTORY_DETAIL <n>
    idx_str = msg.split(" ", 1)[1] if " " in msg else "0"

    if idx_str == "0":
        send_block(conn, [""])
        return

    try:
        idx = int(idx_str) - 1
        op = recientes[idx]
    except (ValueError, IndexError):
        send_block(conn, ["Operación inválida."])
        return

    lines = [f"[{idx+1}] {op['type']} ({op['date']})"]
    for item in op["items"]:
        lines.append(f"* {item['name']} [x{item['qty']}]")
    lines.append(f"Estado: {op['status']}")
    send_block(conn, lines)


def handle_catalogue(conn, catalogue, users, email):
    """Envía catálogo y procesa compra."""
    lines = [f"* {name}: ${info['price']} (stock: {info['stock']})"
             for name, info in catalogue.items()]
    send_block(conn, lines)

    msg = recv(conn)                             # BUY <producto> <cantidad> o BUY_CANCEL

    if msg == "BUY_CANCEL":
        return

    partes = msg.split()
    if partes[0] != "BUY" or len(partes) < 3:
        send(conn, "Solicitud de compra inválida.")
        return

    producto = partes[1]
    try:
        cantidad = int(partes[2])
    except ValueError:
        send(conn, "Cantidad inválida.")
        return

    with stock_lock:
        if producto not in catalogue:
            send(conn, f"Producto '{producto}' no encontrado en el catálogo.")
            return
        if catalogue[producto]["stock"] < cantidad:
            send(conn, f"Stock insuficiente. Stock disponible: {catalogue[producto]['stock']}.")
            return

        catalogue[producto]["stock"] -= cantidad

        # Registrar en historial
        nueva_op = {
            "id": len(users[email]["history"]) + 1,
            "type": "compra",
            "date": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "items": [{"name": producto, "qty": cantidad}],
            "status": "Pagado"
        }
        users[email]["history"].append(nueva_op)

    send(conn, f"Compra exitosa: {cantidad}x {producto}. ¡Gracias!")
    print(f"[SERVIDOR] Compra Cliente {users[email]['name']}: {cantidad}x {producto}.")


def handle_return(conn, users, email, catalogue):
    """Opción [4] Solicitar devolución."""
    recientes = handle_get_history(conn, users, email)

    msg = recv(conn)                             # RETURN <n> o RETURN_CANCEL
    if msg == "RETURN_CANCEL":
        return

    partes = msg.split()
    if len(partes) < 2:
        send(conn, "Solicitud inválida.")
        return

    try:
        idx = int(partes[1]) - 1
        op = recientes[idx]
    except (ValueError, IndexError):
        send(conn, "Operación inválida.")
        return

    if op["status"] not in ("Pagado", "Enviado", "Recibido"):
        send(conn, "Esta operación no puede ser devuelta.")
        return

    # Devolver stock
    with stock_lock:
        for item in op["items"]:
            if item["name"] in catalogue:
                catalogue[item["name"]]["stock"] += item["qty"]
        op["status"] = "Devolución tramitada"

    send(conn, "Devolución solicitada exitosamente.")
    print(f"[SERVIDOR] Devolución Cliente {users[email]['name']}.")


def handle_confirm_shipment(conn, users, email):
    """Opción [5] Confirmar envío."""
    history = users[email]["history"]
    enviados = [op for op in history if op["status"] == "Enviado"]

    if not enviados:
        send_block(conn, ["No tienes envíos pendientes de confirmación."])
        recv(conn)   # consume el CONFIRM_CANCEL que mandará el cliente
        return

    lines = [f"[{i+1}] {op['type']} ({op['date']}) - {', '.join(i['name'] for i in op['items'])}"
             for i, op in enumerate(enviados)]
    send_block(conn, lines)

    msg = recv(conn)                             # CONFIRM_SHIPMENT <n> o CONFIRM_CANCEL
    if msg == "CONFIRM_CANCEL":
        return

    partes = msg.split()
    try:
        idx = int(partes[1]) - 1
        enviados[idx]["status"] = "Recibido"
        send(conn, "Envío confirmado. ¡Gracias!")
        print(f"[SERVIDOR] Confirmación envío Cliente {users[email]['name']}.")
    except (ValueError, IndexError):
        send(conn, "Operación inválida.")


def handle_request_executive(conn, users, email, waiting_queue, queue_lock):
    """
    Opción [6]: pone al cliente en la cola de espera.
    waiting_queue es una list de (email, conn) compartida con los ejecutivos.
    """
    with queue_lock:
        waiting_queue.append((email, conn))
        pos = len(waiting_queue)

    send(conn, f"Estás en la posición {pos} de la cola. Espera un momento...")
    print(f"[SERVIDOR] Cliente {users[email]['name']} en cola de espera para ejecutivo.")
    # El hilo del ejecutivo tomará el control de esta conexión


# Dispatcher principal ----------------------------------------------------

def handle_client_session(conn, users, email, catalogue, waiting_queue, queue_lock):
    """
    Punto de entrada del punto 2.
    Llamar desde handle_client() justo después de la autenticación exitosa.
    """
    name = users[email]["name"]
    print(f"[SERVIDOR] Cliente {name} conectado.")

    try:
        while True:
            msg = recv(conn)

            if msg.startswith("CHANGE_PASS "):
                nueva = msg.split(" ", 1)[1]
                handle_change_pass(conn, users, email, nueva)

            elif msg == "GET_HISTORY":
                recientes = handle_get_history(conn, users, email)
                handle_history_detail(conn, users, email, recientes)

            elif msg == "GET_CATALOGUE":
                handle_catalogue(conn, catalogue, users, email)

            elif msg == "GET_PENDING_SHIPMENTS":
                handle_confirm_shipment(conn, users, email)

            elif msg.startswith("RETURN"):
                # El cliente ya pidió el historial primero;
                # aquí reenviamos historial para que elija
                handle_return(conn, users, email, catalogue)

            elif msg == "REQUEST_EXECUTIVE":
                handle_request_executive(conn, users, email, waiting_queue, queue_lock)
                # El hilo del ejecutivo toma control; este hilo queda en espera
                return   # salir del dispatcher; el ejecutivo maneja el resto

            elif msg == "LOGOUT":
                print(f"[SERVIDOR] Cliente {name} desconectado.")
                break

            else:
                send(conn, "Comando no reconocido.")

    except ConnectionError:
        print(f"[SERVIDOR] Cliente {name} desconectado abruptamente.")
    finally:
        conn.close()
