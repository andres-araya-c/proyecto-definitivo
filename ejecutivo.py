import socket
import threading
import pyotp
import json

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

# ── Autenticación con 2FA ────────────────────────────────────────────────

def autenticar_ejecutivo(sock) -> str:
    print("¡Bienvenido a la plataforma de servicio al cliente de la tienda TC5G!")
    print("Para autenticarse ingrese su mail y contraseña:")

    while True:
        usuario    = input("usuario: ").strip()
        contrasena = input("contraseña: ").strip()
        codigo     = input("codigo 2FA: ").strip()

        enviar(sock, f"AUTH_EJECUTIVO {usuario} {contrasena} {codigo}")
        respuesta = recibir(sock)

        if respuesta.startswith("AUTH_OK"):
            nombre = respuesta.split(" ", 1)[1]
            return nombre
        else:
            print(f"Asistente: {respuesta}\n")

# ── Terminal del ejecutivo ───────────────────────────────────────────────

def terminal_ejecutivo(sock, nombre):
    bienvenida = recibir(sock)
    print(f"Asistente: {bienvenida}")

    print("\nComandos disponibles:")
    print("  :estado               -> clientes conectados y solicitudes en cola")
    print("  :detalles             -> clientes conectados y su ultima accion")
    print("  :conectar             -> atender al proximo cliente en cola")
    print("  :historial            -> historial de acciones del cliente actual")
    print("  :operaciones          -> historial completo de compras del cliente actual")
    print("  :catalogo             -> ver catalogo de cartas y precios")
    print("  :comprar [carta] [precio] -> comprarle carta al cliente")
    print("  :publicar [carta] [precio] -> poner carta a la venta")
    print("  :desconectar          -> terminar sesion con el cliente actual")
    print("  :salir                -> desconectarse del servidor\n")

    cliente_actual = None
    fin_sesion = threading.Event()

    def escuchar_servidor():
        nonlocal cliente_actual
        while not fin_sesion.is_set():
            try:
                msg = recibir(sock)
                if msg.startswith("CHAT_CLIENTE "):
                    texto = msg.split(" ", 1)[1]
                    print(f"\n  >> {texto}")
                elif msg.startswith("CLIENTE_ASIGNADO "):
                    cliente_actual = msg.split(" ", 1)[1]
                    print(f"\nAsistente: Ahora atiendes a {cliente_actual}.")
                elif msg == "%%FIN%%":
                    pass
                else:
                    print(f"\nAsistente: {msg}")
            except:
                fin_sesion.set()
                break

    hilo_escucha = threading.Thread(target=escuchar_servidor, daemon=True)
    hilo_escucha.start()

    while True:
        if cliente_actual:
            entrada = input(f"{nombre} (atendiendo a {cliente_actual}): ").strip()
        else:
            entrada = input(f"{nombre}: ").strip()

        if entrada == ":estado":
            enviar(sock, "CMD_ESTADO")

        elif entrada == ":detalles":
            enviar(sock, "CMD_DETALLES")

        elif entrada == ":conectar":
            enviar(sock, "CMD_CONECTAR")

        elif entrada == ":historial":
            if not cliente_actual:
                print("Asistente: No estas atendiendo a ningun cliente.")
                continue
            enviar(sock, "CMD_HISTORIAL")

        elif entrada == ":operaciones":
            if not cliente_actual:
                print("Asistente: No estas atendiendo a ningun cliente.")
                continue
            enviar(sock, "CMD_OPERACIONES")

        elif entrada == ":catalogo":
            enviar(sock, "CMD_CATALOGO")

        elif entrada.startswith(":comprar "):
            if not cliente_actual:
                print("Asistente: No estas atendiendo a ningun cliente.")
                continue
            # Formato: :comprar <nombre carta con espacios> <precio>
            # El precio es la ultima palabra, el nombre es todo lo demas
            resto = entrada[len(":comprar "):]
            partes = resto.rsplit(" ", 1)
            if len(partes) < 2:
                print("Asistente: Uso correcto -> :comprar [nombre carta] [precio]")
                continue
            nombre_carta, precio = partes[0], partes[1]
            enviar(sock, f"CMD_COMPRAR {nombre_carta}|{precio}")

        elif entrada.startswith(":publicar "):
            resto = entrada[len(":publicar "):]
            partes = resto.rsplit(" ", 1)
            if len(partes) < 2:
                print("Asistente: Uso correcto -> :publicar [nombre carta] [precio]")
                continue
            nombre_carta, precio = partes[0], partes[1]
            enviar(sock, f"CMD_PUBLICAR {nombre_carta}|{precio}")

        elif entrada == ":desconectar":
            if not cliente_actual:
                print("Asistente: No estas atendiendo a ningun cliente.")
                continue
            enviar(sock, "CMD_DESCONECTAR")
            cliente_actual = None

        elif entrada == ":salir":
            enviar(sock, "CMD_SALIR")
            fin_sesion.set()
            print("Asistente: Hasta luego!")
            break

        elif cliente_actual and not entrada.startswith(":"):
            enviar(sock, f"CHAT_EJECUTIVO {entrada}")

        else:
            print("Asistente: Comando no reconocido.")

# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8002

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        nombre = autenticar_ejecutivo(sock)
        terminal_ejecutivo(sock, nombre)
