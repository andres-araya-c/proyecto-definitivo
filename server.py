import socket
import threading
import json
import datetime
#------Permitimos que no haya problemas con pip ni pyotp─────────────────────────────────────────────────

recv_buffer = {}

import subprocess
import sys
import urllib.request
import os

try:
    import pyotp
except ImportError:
    pip_path = os.path.join(os.path.dirname(sys.executable), "Scripts", "pip.exe")
    if not os.path.exists(pip_path):
        installer = os.path.join(os.path.dirname(__file__), "get-pip.py")
        urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", installer)
        subprocess.check_call([sys.executable, installer])
        os.remove(installer)
    subprocess.check_call([pip_path, "install", "pyotp"])
    import pyotp

# ── Cargar base de datos ─────────────────────────────────────────────────

with open("accounts.json", encoding="utf-8") as f:
    cuentas = json.load(f)

with open("ejecutivos.json", encoding="utf-8") as f:
    ejecutivos_db = json.load(f)

# Catálogo de productos cargado desde Cartas.json
with open("Cartas.json", encoding="utf-8") as f:
    _datos_cartas = json.load(f)

catalogo = {
    carta["title"]: {
        "precio": carta["price_usd"],
        "stock":  10   # stock inicial por defecto para cada carta
    }
    for carta in _datos_cartas["cards"]
}

# ── Estado global compartido ─────────────────────────────────────────────

cola_espera      = []           # lista de (cuenta_cliente, conn_cliente, evento_conectado, evento_fin)
clientes_activos = {}           # username → {"cuenta": ..., "conn": ..., "ultima_accion": ..., "acciones": []}
lock_cola        = threading.Lock()
lock_stock       = threading.Lock()
lock_clientes    = threading.Lock()
lock_log         = threading.Lock()

LOG_FILE = "servidor_log.txt"

def escribir_log(mensaje: str):
    """Registra todas las solicitudes en un archivo de texto."""
    timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    linea = f"[{timestamp}] {mensaje}"
    with lock_log:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    print(linea)

# ── Helpers de comunicación ──────────────────────────────────────────────

def enviar(conn, msg: str):
    conn.sendall((msg + "\n").encode())

def enviar_bloque(conn, lineas: list):
    for linea in lineas:
        enviar(conn, linea)
    enviar(conn, "FIN")

def recibir(conn) -> str:
    fd = conn.fileno()
    buf = recv_buffer.get(fd, b"")
    while b"\n" not in buf:
        fragmento = conn.recv(4096)
        if not fragmento:
            raise ConnectionError("Cliente desconectado.")
        buf += fragmento
    linea, resto = buf.split(b"\n", 1)
    recv_buffer[fd] = resto
    return linea.decode().strip()

def registrar_accion(cuenta, accion: str):
    """Actualiza la última acción del cliente en el estado global y en el log."""
    nombre = cuenta["name"]
    with lock_clientes:
        username = cuenta["username"]
        if username in clientes_activos:
            clientes_activos[username]["ultima_accion"] = accion
            clientes_activos[username].setdefault("acciones", []).append(
                {"accion": accion, "fecha": datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}
            )
    escribir_log(f"{accion} - Cliente {nombre}.")

# ── Autenticación clientes ───────────────────────────────────────────────

def manejar_autenticacion_cliente(conn) -> dict | None:
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
        escribir_log(f"Cliente {cuenta['name']} conectado.")
        with lock_clientes:
            clientes_activos[cuenta["username"]] = {
                "cuenta": cuenta,
                "conn":   conn,
                "ultima_accion": "Recién conectado"
            }
        return cuenta

# ── Autenticación ejecutivos (con 2FA) ───────────────────────────────────

def manejar_autenticacion_ejecutivo(conn) -> dict | None:
    while True:
        msg = recibir(conn)
        if not msg.startswith("AUTH_EJECUTIVO "):
            enviar(conn, "Formato inválido.")
            continue

        partes = msg.split(" ", 3)
        if len(partes) < 4:
            enviar(conn, "Credenciales incompletas.")
            continue

        _, usuario, contrasena, codigo = partes
        ejecutivo = next((e for e in ejecutivos_db if e["username"] == usuario), None)

        if not ejecutivo or ejecutivo["password"] != contrasena:
            enviar(conn, "Credenciales inválidas. Intente nuevamente.")
            continue

        if not pyotp.TOTP(ejecutivo["secret"]).verify(codigo, valid_window=1):
            enviar(conn, "Código 2FA inválido. Intente nuevamente.")
            continue

        enviar(conn, f"AUTH_OK {ejecutivo['name']}")
        escribir_log(f"Ejecutivo {ejecutivo['name']} conectado.")
        return ejecutivo

# ── Handlers clientes ────────────────────────────────────────────────────

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
    escribir_log(f"Cambio Clave Cliente {cuenta['name']}.")
    registrar_accion(cuenta, "Cambio de contraseña")


def manejar_ver_historial(conn, cuenta):
    historial   = cuenta.get("history", [])
    hace_un_año = datetime.datetime.now() - datetime.timedelta(days=365)

    recientes = [
        op for op in historial
        if datetime.datetime.strptime(op["date"], "%d/%m/%Y %H:%M") >= hace_un_año    ]

    if not recientes:
        enviar_bloque(conn, ["No tienes operaciones en el último año."])
    else:
        lineas = [f"[{i+1}] {op['type']} ({op['date']})" for i, op in enumerate(recientes)]
        enviar_bloque(conn, lineas)

    registrar_accion(cuenta, "Consulta de historial")
    return recientes


def manejar_detalle_historial(conn, recientes):
    msg     = recibir(conn)
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

    lineas = [f"[{idx+1}] {op['type']} ({op['date']})"]
    for articulo in op.get("items", []):
        lineas.append(f"* {articulo['name']} [x{articulo['qty']}]")
    lineas.append(f"Estado: {op['status']}")
    enviar_bloque(conn, lineas)


def manejar_catalogo(conn, cuenta):
    lineas = [
        f"[{i+1}] {nombre}: ${info['precio']} (stock: {info['stock']})"
        for i, (nombre, info) in enumerate(catalogo.items())
    ]
    enviar_bloque(conn, lineas)
    registrar_accion(cuenta, "Consulta de catálogo")

    msg = recibir(conn)
    if msg == "COMPRA_CANCELADA":
        return

    partes = msg.split(" ", 1)
    if partes[0] != "COMPRAR" or len(partes) < 2:
        enviar(conn, "Solicitud inválida.")
        return

    resto = partes[1].rsplit(" ", 1)
    producto = resto[0]
    try:
        cantidad = int(resto[1])

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
            "id":     len(cuenta.get("history", [])) + 1,
            "type":   "compra",
            "date":   datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "items":  [{"name": producto, "qty": cantidad}],
            "status": "No enviado"
        }
        cuenta.setdefault("history", []).append(nueva_op)
        with open("accounts.json", "w", encoding="utf-8") as f:
            json.dump(cuentas, f, indent=4, ensure_ascii=False)

    enviar(conn, f"Compra exitosa: {cantidad}x {producto}. ¡Gracias!")
    escribir_log(f"Compra Cliente {cuenta['name']}: {cantidad}x {producto}.")
    registrar_accion(cuenta, f"Compra de {cantidad}x {producto}")


def manejar_devolucion(conn, cuenta):
    recientes = manejar_ver_historial(conn, cuenta)

    msg = recibir(conn)
    if msg == "DEVOLUCION_CANCELADA":
        return

    try:
        idx = int(msg.split()[1]) - 1
        op  = recientes[idx]
    except (ValueError, IndexError):
        enviar(conn, "Operación inválida.")
        return

    if op["status"] not in ("No enviado", "Pagado", "Enviado", "Recibido"):
        enviar(conn, "Esta operación no puede ser devuelta.")
        return
    with lock_stock:
        for articulo in op.get("items", []):
            if articulo["name"] in catalogo:
                catalogo[articulo["name"]]["stock"] += articulo["qty"]
        op["status"] = "Devolución tramitada"

   
    with open("accounts.json", "w", encoding="utf-8") as f:
        json.dump(cuentas, f, indent=4, ensure_ascii=False)

    enviar(conn, "Devolución solicitada exitosamente.")
    escribir_log(f"Devolución Cliente {cuenta['name']}.")
    registrar_accion(cuenta, "Solicitud de devolución")


def manejar_confirmar_envio(conn, cuenta):
    historial = cuenta.get("history", [])
    pendientes = [op for op in historial if op.get("status") == "No enviado"]

    if not pendientes:
        enviar_bloque(conn, ["No tienes envíos pendientes de confirmación."])
        recibir(conn)
        return

    lineas = []
    for i, op in enumerate(pendientes):
        descripcion = op.get("tipo") or op.get("type") or "envío"
        fecha = op.get("fecha") or op.get("date") or "fecha desconocida"
        articulos = op.get("articulos") or op.get("items") or []
        nombres = [a.get("nombre") or a.get("name") or "artículo" for a in articulos]
        lineas.append(f"[{i+1}] {descripcion} ({fecha}) - {', '.join(nombres)}")

    enviar_bloque(conn, lineas)

    msg = recibir(conn)
    if msg == "CONFIRMACION_CANCELADA":
        return

    try:
        idx = int(msg.split()[1]) - 1
        pendientes[idx]["status"] = "Enviado"
        enviar(conn, "Envío confirmado. El pedido ha sido marcado como enviado.")
        escribir_log(f"Confirmación envío Cliente {cuenta['name']}.")
        registrar_accion(cuenta, "Confirmación de envío")
    except (ValueError, IndexError):
        enviar(conn, "Operación inválida.")


def manejar_solicitar_ejecutivo(conn, cuenta):
    # Dos eventos: uno cuando el ejecutivo toma al cliente, otro cuando termina el chat
    evento_conectado  = threading.Event()
    evento_fin_chat   = threading.Event()
    with lock_cola:
        cola_espera.append((cuenta, conn, evento_conectado, evento_fin_chat))
        posicion = len(cola_espera)
    enviar(conn, f"Estás en la posición {posicion} de la cola. Espera un momento...")
    escribir_log(f"Cliente {cuenta['name']} en cola de espera para ejecutivo.")
    registrar_accion(cuenta, "Solicitud de ejecutivo")
    # Bloquear hasta que el chat con el ejecutivo termine completamente
    evento_fin_chat.wait()

# ── Chat cliente-ejecutivo ───────────────────────────────────────────────

def manejar_chat_con_ejecutivo(conn_cliente, conn_ejecutivo, cuenta_cliente, nombre_ejecutivo):
    """
    Puente bidireccional entre cliente y ejecutivo.
    Corre en el hilo del ejecutivo; el cliente queda bloqueado esperando mensajes.
    """
    nombre_cliente = cuenta_cliente["name"]

    # Avisar al cliente que el ejecutivo está listo
    enviar(conn_cliente, f"EJECUTIVO_CONECTADO {nombre_ejecutivo}")
    escribir_log(f"Cliente {nombre_cliente} redirigido a ejecutivo {nombre_ejecutivo}.")

    # Evento para señalar fin del chat
    fin_chat = threading.Event()

    def escuchar_cliente():
        """Reenvía mensajes del cliente al ejecutivo."""
        while not fin_chat.is_set():
            try:
                msg = recibir(conn_cliente)
                enviar(conn_ejecutivo, f"CHAT_CLIENTE {nombre_cliente}: {msg}")
            except ConnectionError:
                fin_chat.set()
                break

    hilo_cliente = threading.Thread(target=escuchar_cliente, daemon=True)
    hilo_cliente.start()

    # El hilo actual escucha al ejecutivo y reenvía al cliente
    while not fin_chat.is_set():
        try:
            msg = recibir(conn_ejecutivo)

            if msg == "CMD_DESCONECTAR":
                enviar(conn_cliente, "EJECUTIVO_DESCONECTADO")
                fin_chat.set()
                break

            elif msg.startswith("CHAT_EJECUTIVO "):
                texto = msg.split(" ", 1)[1]
                enviar(conn_cliente, texto)

            elif msg.startswith("CMD_COMPRAR "):
                # Formato: CMD_COMPRAR nombre carta|precio
                resto = msg[len("CMD_COMPRAR "):]
                if "|" not in resto:
                    enviar(conn_ejecutivo, "Uso: :comprar [nombre carta] [precio]")
                    continue
                carta, precio_str = resto.rsplit("|", 1)
                try:
                    precio = float(precio_str.strip())
                except ValueError:
                    enviar(conn_ejecutivo, "Precio inválido.")
                    continue

                nueva_op = {
                    "id":        len(cuenta_cliente.get("history", [])) + 1,
                    "type":      "venta",
                    "date":     datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "items": [{"nombre": carta.strip(), "cantidad": 1}],
                    "status":    "No enviado",
                    "precio":    precio
                }
                cuenta_cliente.setdefault("history", []).append(nueva_op)
                enviar(conn_ejecutivo, f"Compra registrada: {carta.strip()} por ${precio}.")
                enviar(conn_cliente,   f"El ejecutivo ha comprado tu carta: {carta.strip()} por ${precio}.")
                escribir_log(f"Ejecutivo {nombre_ejecutivo} compró {carta.strip()} a {nombre_cliente} por ${precio}.")

            elif msg.startswith("CMD_PUBLICAR "):
                # Formato: CMD_PUBLICAR nombre carta|precio
                resto = msg[len("CMD_PUBLICAR "):]
                if "|" not in resto:
                    enviar(conn_ejecutivo, "Uso: :publicar [nombre carta] [precio]")
                    continue
                carta, precio_str = resto.rsplit("|", 1)
                try:
                    precio = float(precio_str.strip())
                except ValueError:
                    enviar(conn_ejecutivo, "Precio inválido.")
                    continue

                with lock_stock:
                    if carta.strip() in catalogo:
                        catalogo[carta.strip()]["stock"] += 1
                    else:
                        catalogo[carta.strip()] = {"precio": precio, "stock": 1}

                enviar(conn_ejecutivo, f"'{carta.strip()}' publicada en el catálogo por ${precio}.")
                escribir_log(f"Ejecutivo {nombre_ejecutivo} publicó {carta.strip()} por ${precio}.")

            # Pasar otros comandos del ejecutivo (estado, detalles, etc.)
            # al dispatcher del ejecutivo — se ignoran durante el chat
            else:
                enviar(conn_ejecutivo, "Comando no disponible durante el chat.")

        except ConnectionError:
            fin_chat.set()
            break

    hilo_cliente.join(timeout=2)

# ── Handlers ejecutivo ───────────────────────────────────────────────────

def manejar_ejecutivo(conn, ejecutivo):
    nombre = ejecutivo["name"]

    # Enviar cantidad de clientes conectados al iniciar sesión
    with lock_clientes:
        n_clientes = len(clientes_activos)
    enviar(conn, f"Hola {nombre}, en este momento hay {n_clientes} cliente(s) conectado(s).")

    cliente_actual      = None   # cuenta del cliente que se atiende
    conn_cliente_actual = None

    try:
        while True:
            msg = recibir(conn)

            # ── :estado ──────────────────────────────────────────────
            if msg == "CMD_ESTADO":
                with lock_clientes:
                    n = len(clientes_activos)
                with lock_cola:
                    n_cola = len(cola_espera)
                    nombres_cola = [c[0]["name"] for c in cola_espera]
                lineas = [
                    f"Clientes conectados: {n}",
                    f"Solicitudes en cola: {n_cola}"
                ] + ([f"  En cola: " + ", ".join(nombres_cola)] if nombres_cola else [])
                enviar_bloque(conn, lineas)

            # ── :detalles ─────────────────────────────────────────────
            elif msg == "CMD_DETALLES":
                with lock_clientes:
                    if not clientes_activos:
                        enviar_bloque(conn, ["No hay clientes conectados."])
                    else:
                        lineas = [
                            f"{datos['cuenta']['username']}  {datos['cuenta']['name']}  →  {datos['ultima_accion']}"
                            for datos in clientes_activos.values()
                        ]
                        enviar_bloque(conn, lineas)

            # ── :conectar ─────────────────────────────────────────────
            elif msg == "CMD_CONECTAR":
                with lock_cola:
                    if not cola_espera:
                        enviar(conn, "No hay clientes en la cola de espera.")
                        continue
                    cuenta_cli, conn_cli, evento_conectado_cli, evento_fin_cli = cola_espera.pop(0)

                cliente_actual      = cuenta_cli
                conn_cliente_actual = conn_cli
                enviar(conn, f"CLIENTE_ASIGNADO {cuenta_cli['name']}")

                # Iniciar chat — cuando termine, activar evento_fin para liberar hilo cliente
                manejar_chat_con_ejecutivo(conn_cli, conn, cuenta_cli, nombre)
                evento_fin_cli.set()
                cliente_actual      = None
                conn_cliente_actual = None

            # ── :historial ────────────────────────────────────────────
            elif msg == "CMD_HISTORIAL":
                if not cliente_actual:
                    enviar_bloque(conn, ["No estás atendiendo a ningún cliente."])
                    continue
                # Buscar acciones del cliente en clientes_activos
                username = cliente_actual["username"]
                with lock_clientes:
                    acciones = clientes_activos.get(username, {}).get("acciones", [])
                if not acciones:
                    enviar_bloque(conn, ["El cliente no tiene acciones registradas en esta sesión."])
                else:
                    lineas = [f"[{i+1}] ({a['fecha']}) {a['accion']}" for i, a in enumerate(acciones)]
                    enviar_bloque(conn, lineas)

            # ── :operaciones ──────────────────────────────────────────
            elif msg == "CMD_OPERACIONES":
                if not cliente_actual:
                    enviar_bloque(conn, ["No estás atendiendo a ningún cliente."])
                    continue
                historial = cliente_actual.get("history", [])
                if not historial:
                    enviar_bloque(conn, ["El cliente no tiene operaciones registradas."])
                else:
                    lineas = []
                    for i, op in enumerate(historial):
                        lineas.append(f"[{i+1}] {op['tipo']} ({op['fecha']}) - Estado: {op['status']}")
                        for art in op.get("articulos", []):
                            lineas.append(f"    * {art['nombre']} [x{art['cantidad']}]")
                    enviar_bloque(conn, lineas)

            # ── :catalogo ─────────────────────────────────────────────
            elif msg == "CMD_CATALOGO":
                lineas = [
                    f"* {nombre_carta}: ${info['precio']} (stock: {info['stock']})"
                    for nombre_carta, info in catalogo.items()
                ]
                enviar_bloque(conn, lineas)

            # ── :publicar (fuera de chat) ──────────────────────────────
            elif msg.startswith("CMD_PUBLICAR "):
                resto = msg[len("CMD_PUBLICAR "):]
                if "|" not in resto:
                    enviar(conn, "Uso: :publicar [nombre carta] [precio]")
                    continue
                carta, precio_str = resto.rsplit("|", 1)
                carta = carta.strip()
                try:
                    precio = float(precio_str.strip())
                except ValueError:
                    enviar(conn, "Precio inválido.")
                    continue
                with lock_stock:
                    if carta in catalogo:
                        catalogo[carta]["stock"] += 1
                    else:
                        catalogo[carta] = {"precio": precio, "stock": 1}
                enviar(conn, f"'{carta}' publicada en el catálogo por ${precio}.")
                escribir_log(f"Ejecutivo {nombre} publicó {carta} por ${precio}.")

            # ── :salir ────────────────────────────────────────────────
            elif msg == "CMD_SALIR":
                escribir_log(f"Ejecutivo {nombre} desconectado.")
                break

            else:
                enviar(conn, "Comando no reconocido.")

    except ConnectionError:
        escribir_log(f"Ejecutivo {nombre} desconectado abruptamente.")
    finally:
        conn.close()

# ── Dispatcher principal ─────────────────────────────────────────────────

def manejar_conexion(conn, addr):
    """
    Determina si la conexión es de un cliente o un ejecutivo
    según el primer mensaje recibido.
    """
    try:
        msg = recibir(conn)

        if msg.startswith("AUTH_EJECUTIVO "):
            ejecutivo = _autenticar_ejecutivo_con_msg(conn, msg)
            if ejecutivo:
                manejar_ejecutivo(conn, ejecutivo)

        elif msg.startswith("AUTH "):
            cuenta = _autenticar_cliente_con_msg(conn, msg)
            if cuenta:
                manejar_cliente_sesion(conn, cuenta)

        else:
            enviar(conn, "Tipo de conexión no reconocido.")
            conn.close()

    except ConnectionError:
        pass

def _autenticar_cliente_con_msg(conn, primer_msg) -> dict | None:
    """Autentica cliente reutilizando el primer mensaje ya leído."""
    while True:
        partes = primer_msg.split(" ", 2)
        if len(partes) >= 3:
            _, usuario, contrasena = partes
            cuenta = next((c for c in cuentas if c["username"] == usuario), None)
            if cuenta and cuenta["password"] == contrasena:
                enviar(conn, f"AUTH_OK {cuenta['name']}")
                escribir_log(f"Cliente {cuenta['name']} conectado.")
                with lock_clientes:
                    clientes_activos[cuenta["username"]] = {
                        "cuenta": cuenta,
                        "conn":   conn,
                        "ultima_accion": "Recién conectado"
                    }
                return cuenta
            else:
                enviar(conn, "Credenciales inválidas. Intente nuevamente.")
        else:
            enviar(conn, "Credenciales incompletas.")

        primer_msg = recibir(conn)
        if not primer_msg.startswith("AUTH "):
            enviar(conn, "Formato inválido.")
            return None

def _autenticar_ejecutivo_con_msg(conn, primer_msg) -> dict | None:
    """Autentica ejecutivo reutilizando el primer mensaje ya leído."""
    while True:
        # Formato: AUTH_EJECUTIVO usuario contraseña codigo
        partes = primer_msg.split(" ")
        if len(partes) >= 4:
            usuario    = partes[1]
            contrasena = partes[2]
            codigo     = partes[3]
            ejecutivo = next((e for e in ejecutivos_db if e["username"] == usuario), None)
            if ejecutivo and ejecutivo["password"] == contrasena:
                print(f"[DEBUG] TOTP esperado: {__import__('pyotp').TOTP(ejecutivo['secret']).now()} | recibido: {codigo}")
                if pyotp.TOTP(ejecutivo["secret"]).verify(codigo, valid_window=1):
                    enviar(conn, f"AUTH_OK {ejecutivo['name']}")
                    escribir_log(f"Ejecutivo {ejecutivo['name']} conectado.")
                    return ejecutivo
                else:
                    enviar(conn, "Código 2FA inválido. Intente nuevamente.")
            else:
                enviar(conn, "Credenciales inválidas. Intente nuevamente.")
        else:
            enviar(conn, "Credenciales incompletas.")

        primer_msg = recibir(conn)
        if not primer_msg.startswith("AUTH_EJECUTIVO "):
            enviar(conn, "Formato inválido.")
            return None

def manejar_cliente_sesion(conn, cuenta):
    try:
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
                registrar_accion(cuenta, "Atendido por ejecutivo - fin de sesión")
                # Después del chat el cliente vuelve al menú principal
                continue

            elif msg == "SALIR":
                escribir_log(f"Cliente {cuenta['name']} desconectado.")
                break

            else:
                enviar(conn, "Comando no reconocido.")

    except ConnectionError:
        escribir_log(f"Cliente {cuenta['name']} desconectado abruptamente.")
    finally:
        with lock_clientes:
            clientes_activos.pop(cuenta["username"], None)
        conn.close()

# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8002

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PORT))
        servidor.listen(10)
        escribir_log(f"Escuchando en {HOST}:{PORT}...")

        while True:
            conn, addr = servidor.accept()
            threading.Thread(target=manejar_conexion, args=(conn, addr), daemon=True).start()