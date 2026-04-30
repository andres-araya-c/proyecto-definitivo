import socket
import threading
#_________________________
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
        if linea == "FIN":
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
    print("  :status               -> clientes conectados y solicitudes en cola")
    print("  :details            -> clientes conectados y su ultima accion")
    print("  :connect             -> atender al proximo cliente en cola")
    print("  :history            -> historial de acciones del cliente actual")
    print("  :operations         -> historial completo de compras del cliente actual")
    print("  :catalogue           -> ver catalogo de cartas y precios")
    print("  :buy [carta] [precio] -> comprarle carta al cliente")
    print("  :publish [carta] [precio] -> poner carta a la venta")
    print("  :disconnect          -> terminar sesion con el cliente actual")
    print("  :exit                -> desconectarse del servidor\n")

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
                elif msg == "FIN":
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

        if entrada == ":status":
            enviar(sock, "CMD_ESTADO")

        elif entrada == ":details":
            enviar(sock, "CMD_DETALLES")

        elif entrada == ":connect":
            enviar(sock, "CMD_CONECTAR")

        elif entrada == ":history":
            if not cliente_actual:
                print("Asistente: No estas atendiendo a ningun cliente.")
                continue
            enviar(sock, "CMD_HISTORIAL")

        elif entrada == ":operations":
            if not cliente_actual:
                print("Asistente: No estas atendiendo a ningun cliente.")
                continue
            enviar(sock, "CMD_OPERACIONES")

        elif entrada == ":catalogue":
            enviar(sock, "CMD_CATALOGO")

        elif entrada.startswith(":buy "):
            if not cliente_actual:
                print("Asistente: No estas atendiendo a ningun cliente.")
                continue

            resto = entrada[len(":buy "):]
            partes = resto.rsplit(" ", 1)
            if len(partes) < 2:
                print("Asistente: Uso correcto -> :buy [nombre carta] [precio]")
                continue
            nombre_carta, precio = partes[0], partes[1]
            enviar(sock, f"CMD_COMPRAR {nombre_carta}|{precio}")

        elif entrada.startswith(":publish "):
            resto = entrada[len(":publish "):]
            partes = resto.rsplit(" ", 1)
            if len(partes) < 2:
                print("Asistente: Uso correcto -> :publish  [nombre carta] [precio]")
                continue
            nombre_carta, precio = partes[0], partes[1]
            enviar(sock, f"CMD_PUBLICAR {nombre_carta}|{precio}")

        elif entrada == ":disconnect":
            if not cliente_actual:
                print("Asistente: No estas atendiendo a ningun cliente.")
                continue
            enviar(sock, "CMD_DESCONECTAR")
            cliente_actual = None

        elif entrada == ":exit":
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
