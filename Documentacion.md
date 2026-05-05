# Documentación del Proyecto TC5G

Esta documentación integra los principales archivos del proyecto:

- `server.py`
- `client.py`
- `ejecutivo.py`
- `multicliente.py`

Incluye descripción de la arquitectura, el protocolo de comunicación y los comandos admitidos.

---

## Estructura de archivos

- `server.py` — servidor principal
- `client.py` — interfaz para clientes finales que usan el servicio.
- `ejecutivo.py` — interfaz para ejecutivos que atienden a clientes mediante chat y comandos administrativos.
- `multicliente.py` — lanzador de múltiples instancias de clientes simultáneos
- `accounts.json` — base de datos de clientes
- `ejecutivos.json` — base de datos de ejecutivos y secretos 2FA
- `Cartas.json` — datos del catálogo de productos
- `servidor_log.txt` — registro de eventos del servidor

---

# 1. `server.py`

## Visión general

`server.py` es la aplicación central que

- acepta conexiones TCP
- autentica usuarios y ejecutivos
- procesa comandos de clientes
- maneja solicitudes de ejecutivos
- coordina chat entre cliente y ejecutivo
- mantiene estado compartido seguro entre hilos

## Requisitos

- Python 3.13 o superior
- `pyotp` para verificación TOTP de ejecutivos

El script intenta instalar `pyotp` automáticamente si no está presente.

## Ejecución

Desde la carpeta del proyecto:

```powershell
python server.py
```

El servidor escucha en `127.0.0.1:8002`.

## Protocolo de comunicación

- Usa TCP con mensajes terminados en `\n`.
- Cada línea de texto es un comando o respuesta.
- Para respuestas largas, el servidor envía un bloque de líneas y termina con `FIN`.

### Funciones principales

- `enviar(conn, msg)` — envía una línea acabada en `\n`
- `enviar_bloque(conn, lineas)` — envía múltiples líneas y finaliza con `FIN`
- `recibir(conn)` — recibe una línea completa del socket

## Autenticación

### Cliente

- Envía: `AUTH <usuario> <contraseña>`
- Si es correcto, recibe: `AUTH_OK <nombre>`

### Ejecutivo

- Envía: `AUTH_EJECUTIVO <usuario> <contraseña> <codigo>`
- El servidor verifica el TOTP con `pyotp`
- Si es correcto, recibe: `AUTH_OK <nombre>`

## Comandos para clientes

- `CAMBIAR_CLAVE <nueva_clave>` — inicia cambio de contraseña
- `VER_HISTORIAL` — consulta historial reciente
- `VER_CATALOGO` — muestra catálogo de productos
- `VER_ENVIOS_PENDIENTES` — muestra envíos pendientes
- `DEVOLVER` — inicia una devolución
- `SOLICITAR_EJECUTIVO` — entra a la cola de atención
- `SALIR` — desconecta al cliente

### Compra de productos

Después de `VER_CATALOGO`, el cliente puede enviar:

```text
COMPRAR <producto> <cantidad>
```

### Confirmación de envíos

- El servidor muestra envíos pendientes.
- El cliente puede confirmar o cancelar.
- Se usa `CONFIRMACION_CANCELADA` para cancelar.

## Comandos para ejecutivos

- `CMD_ESTADO` — muestra clientes conectados y cola
- `CMD_DETALLES` — muestra detalles de clientes activos
- `CMD_CONECTAR` — atiende el siguiente cliente en cola
- `CMD_HISTORIAL` — historial de acciones del cliente actual
- `CMD_OPERACIONES` — historial de operaciones del cliente actual
- `CMD_CATALOGO` — muestra el catálogo
- `CMD_PUBLICAR <nombre carta>|<precio>` — publica o agrega stock
- `CMD_SALIR` — desconecta al ejecutivo

## Chat cliente-ejecutivo

Cuando un cliente solicita atención:

1. Se añade a `cola_espera`.
2. El ejecutivo usa `CMD_CONECTAR`.
3. El cliente recibe `EJECUTIVO_CONECTADO <nombre>`.
4. Se habla mediante:
   - `CHAT_CLIENTE <nombre>: <mensaje>`
   - `CHAT_EJECUTIVO <mensaje>`

### Comandos internos en chat

- `CMD_DESCONECTAR` — cierra la sesión
- `CMD_COMPRAR <nombre carta>|<precio>` — registra una venta
- `CMD_PUBLICAR <nombre carta>|<precio>` — publica un producto

## Concurrencia y bloqueos

El servidor usa bloqueos para proteger:

- `lock_cola` — cola de clientes a ejecutivos
- `lock_stock` — actualización de stock
- `lock_clientes` — estado de `clientes_activos`
- `lock_log` — escritura de logs

Cada cliente o ejecutivo se maneja en su hilo daemon.

## Logging

`escribir_log()` escribe en `servidor_log.txt` y en consola.
Los registros incluyen fecha, hora y descripción de la acción.

## Almacenamiento de datos

- `accounts.json` — datos de clientes y su historial
- `ejecutivos.json` — usuarios ejecutivos y secretos 2FA
- `Cartas.json` — catálogo de cartas y precios

---

# 2. `client.py`

## Visión general

`client.py` es la interfaz de cliente final que permite interactuar con el servidor mediante menús y enviar comandos apropiados.

## Ejecución

```powershell
python client.py
```

### Flujo de autenticación

1. El usuario ingresa su `usuario`.
2. El usuario ingresa su `contraseña`.
3. Se envía `AUTH <usuario> <contraseña>` al servidor.
4. Si la autenticación es correcta, el servidor responde `AUTH_OK <nombre>`.

## Menú principal

Opciones disponibles:

1. Cambio de contraseña
2. Historial de operaciones
3. Catálogo / Comprar productos
4. Solicitar devolución
5. Confirmar envío
6. Contactar con un ejecutivo
7. Salir

## Funciones principales

### Cambio de contraseña

- Envía `CAMBIAR_CLAVE <nueva_clave>`.
- Envía luego `CONFIRMAR_CLAVE <confirmacion>`.
- Muestra la respuesta del servidor.

### Historial

- Envía `VER_HISTORIAL`.
- Muestra el bloque de respuesta.
- Envía `DETALLE_HISTORIAL <opcion>` para ver detalles.

### Catálogo y compra

- Envía `VER_CATALOGO`.
- Recibe y muestra el catálogo.
- Permite buscar por número, nombre o palabra clave.
- Envía `COMPRAR <producto> <cantidad>`.

### Devolución

- Envía `DEVOLVER`.
- Muestra las operaciones disponibles.
- Envía `DEVOLVER <numero>` o `DEVOLUCION_CANCELADA`.

### Confirmar envío

- Envía `VER_ENVIOS_PENDIENTES`.
- Selecciona un envío pendiente.
- Envía `CONFIRMAR_ENVIO <numero>` o `CONFIRMACION_CANCELADA`.

### Solicitar ejecutivo

- Envía `SOLICITAR_EJECUTIVO`.
- Espera la respuesta del servidor.
- Si se conecta un ejecutivo, el cliente entra al chat.

### Salir

- Envía `SALIR`.
- Termina la sesión del cliente.

---

# 3. `ejecutivo.py`

## Visión general

`ejecutivo.py` es la interfaz para ejecutivos encargados de atender clientes en cola.

## Ejecución

```powershell
python ejecutivo.py
```

### Autenticación

1. El ejecutivo ingresa `usuario`.
2. Ingresa `contraseña`.
3. Ingresa `codigo 2FA`.
4. Se envía `AUTH_EJECUTIVO <usuario> <contraseña> <codigo>`.
5. Si es correcto, el servidor responde `AUTH_OK <nombre>`.

## Interfaz principal

Comandos disponibles:

- `:status` — estado general y cola de clientes
- `:details` — detalles de clientes conectados
- `:connect` — atiende al próximo cliente en cola
- `:history` — historial del cliente actual
- `:operations` — operaciones del cliente actual
- `:catalogue` — muestra el catálogo de productos
- `:buy [carta] [precio]` — registra una compra para el cliente
- `:publish [carta] [precio]` — publica o agrega stock
- `:disconnect` — termina la sesión con el cliente actual
- `:exit` — desconecta al ejecutivo

## Chat con el cliente

- El ejecutivo recibe `CHAT_CLIENTE ...` cuando el cliente envía mensajes.
- El ejecutivo puede escribir texto sin `:` para enviar chat al cliente.
- `:disconnect` cierra la sesión de chat con el cliente.

## Manejo del cliente actual

- `CLIENTE_ASIGNADO <nombre>` indica el cliente atendido.
- Mientras hay cliente, los mensajes sin `:` se envían al cliente.
- Los comandos que comienzan con `:` se interpretan localmente.

---

# 4. `multicliente.py`

## Visión general

`multicliente.py` es un lanzador que permite ejecutar múltiples instancias de `client.py` simultáneamente desde una única interfaz. Facilita pruebas concurrentes, demostraciones o simulaciones del sistema con varios clientes.

## Ejecución

```powershell
python multicliente.py
```

### Solicitud de clientes

Al ejecutarse, solicita la cantidad de clientes a lanzar:

```
¿Cuántos clientes desea lanzar? <número>
```

Ingrese un número entero mayor a 0. El programa lanzará esa cantidad de procesos independientes de `client.py`.

## Interfaz de control

Una vez lanzados los clientes, aparece un menú con las opciones:

### Enviar comandos a un cliente específico

```
<número>:<comando>
```

Ejemplo:
```
1:COMPRAR Carta1 2
2:SOLICITAR_EJECUTIVO
3:VER_HISTORIAL
```

### Enviar comandos a todos los clientes

```
*:<comando>
```

Ejemplo:
```
*:VER_CATALOGO
*:SOLICITAR_EJECUTIVO
```

### Salir

```
q
```

Termina todos los procesos de clientes y finaliza el lanzador.

## Funcionalidad técnica

- **Subprocesos**: Cada cliente se ejecuta en su propio proceso independiente.
- **Colas de entrada**: Se usa una cola thread-safe para comunicarse con cada cliente.
- **Lectura de salida**: Los mensajes de cada cliente se capturan y se muestran prefijados con `[ClienteN]`.
- **Codificación**: Soporta `latin-1` y UTF-8 para mayor compatibilidad.

## Casos de uso

- **Pruebas concurrentes**: Simular múltiples usuarios usando el sistema simultáneamente.
- **Demostraciones**: Mostrar interacciones complejas con varios clientes al mismo tiempo.
- **Validación de carga**: Verificar que el servidor maneja múltiples conexiones correctamente.
- **Desarrollo y debugging**: Interactuar con múltiples clientes sin abrir múltiples terminales.

---

## Observaciones finales

- El servidor debe ejecutarse antes de iniciar clientes o ejecutivos.
- `client.py` es para usuarios finales y `ejecutivo.py` para personal.
- Todos los mensajes usan terminación `\n`.
- El sistema funciona en localhost y no está diseñado para redes públicas.
