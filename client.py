import socket

recv_buffer = {}

# ── Helpers de comunicación ──────────────────────────────────────────────

def enviar(sock, msg: str):
    sock.sendall((msg + "\n").encode())

def recibir(sock) -> str:
    fd = sock.fileno()
    buf = recv_buffer.get(fd, b"")
    while b"\n" not in buf:
        fragmento = sock.recv(4096)
        if not fragmento:
            raise ConnectionError("Servidor desconectado.")
        buf += fragmento
    linea, resto = buf.split(b"\n", 1)
    recv_buffer[fd] = resto
    return linea.decode().strip()

def recibir_bloque(sock) -> str:
    lineas = []
    while True:
        linea = recibir(sock)
        if linea == "FIN":
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
    print(f"Asistente:\n{recibir_bloque(sock)}")

def menu_catalogo(sock, usuario):
    enviar(sock, "VER_CATALOGO")
    bloque = recibir_bloque(sock)
    print(f"Asistente: Catálogo disponible:\n{bloque}")

    # Parse catalog into list of (num, name, price, stock)
    catalog_list = []
    for line in bloque.splitlines():
        if line.startswith('[') and ']' in line:
            num_str = line[1:line.index(']')].strip()
            if num_str.isdigit():
                num = int(num_str)
                rest = line[line.index(']')+1:].strip()
                if ': $' in rest:
                    name, rest2 = rest.split(': $', 1)
                    if ' (stock: ' in rest2:
                        price_str, stock_str = rest2.split(' (stock: ', 1)
                        stock_str = stock_str.rstrip(')')
                        try:
                            price = float(price_str)
                            stock = int(stock_str)
                            catalog_list.append((num, name.strip(), price, stock))
                        except ValueError:
                            pass

    while True:
        input_str = input("Ingrese el nombre del producto, número o palabra clave (0 = Cancelar): ").strip()
        if input_str == "0":
            enviar(sock, "COMPRA_CANCELADA")
            return

        producto = None
        if input_str.isdigit():
            num = int(input_str)
            if 1 <= num <= len(catalog_list):
                producto = catalog_list[num-1][1]
            else:
                print("Asistente: Número inválido.")
                continue
        else:
            # Search for matches
            matches = [item for item in catalog_list if input_str.lower() in item[1].lower()]
            if not matches:
                print("Asistente: No se encontraron cartas con esa palabra.")
                continue
            if len(matches) == 1:
                producto = matches[0][1]
            else:
                print("Asistente: Múltiples coincidencias:")
                for num, name, price, stock in matches:
                    print(f"[{num}] {name}: ${price} (stock: {stock})")
                choice = input("Seleccione el número: ").strip()
                if choice.isdigit():
                    choice_num = int(choice)
                    match = next((m for m in matches if m[0] == choice_num), None)
                    if match:
                        producto = match[1]
                    else:
                        print("Asistente: Selección inválida.")
                        continue
                else:
                    print("Asistente: Selección inválida.")
                    continue

        # Now have producto, ask for cantidad
        cantidad_str = input("Ingrese la cantidad: ").strip()
        try:
            cantidad = int(cantidad_str)
        except ValueError:
            print("Asistente: Cantidad inválida.")
            continue

        enviar(sock, f"COMPRAR {producto} {cantidad}")
        print(f"Asistente: {recibir(sock)}")
        return

def menu_devolucion(sock, usuario):
    enviar(sock, "DEVOLVER")
    print(f"Asistente: Sus compras:\n{recibir_bloque(sock)}")
    opcion = input("Ingrese el número de operación a devolver (0 = Cancelar): ").strip()
    if opcion == "0":
        enviar(sock, "DEVOLUCION_CANCELADA")
        return
    enviar(sock, f"DEVOLVER {opcion}")
    print(f"Asistente: {recibir(sock)}")

def menu_confirmar_envio(sock, usuario):
    enviar(sock, "VER_ENVIOS_PENDIENTES")
    bloque = recibir_bloque(sock)
    print(f"Asistente: Envíos pendientes:\n{bloque}")

    if bloque.strip() == "No tienes envíos pendientes de confirmación.":
        enviar(sock, "CONFIRMACION_CANCELADA")
        return

    opciones_validas = {"0"}
    for linea in bloque.splitlines():
        if linea.startswith("[") and "]" in linea:
            opcion_num = linea[1:linea.index("]")].strip()
            if opcion_num.isdigit():
                opciones_validas.add(opcion_num)

    while True:
        opcion = input("Ingrese el número de envío a confirmar (0 = Cancelar): ").strip()
        if opcion == "0":
            enviar(sock, "CONFIRMACION_CANCELADA")
            return
        if opcion not in opciones_validas:
            print("Asistente: Opción inválida. Por favor ingrese un número válido de la lista.")
            continue

        enviar(sock, f"CONFIRMAR_ENVIO {opcion}")
        print(f"Asistente: {recibir(sock)}")
        return

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
