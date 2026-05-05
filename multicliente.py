import subprocess
import sys
import threading
import queue
import time
 
def pipe_to_process(proc, input_queue, name):
    while True:
        line = input_queue.get()
        if line is None:
            break
        try:
            proc.stdin.write((line + "\n").encode("latin-1"))
            proc.stdin.flush()
        except:
            break
 
def read_output(proc, name):
    for line in proc.stdout:
        try:
            text = line.decode("latin-1")
        except:
            text = line.decode("utf-8", errors="replace")
        print(f"[{name}] {text}", end="")
 
# Ask how many clients to launch
while True:
    try:
        n = int(input("¿Cuántos clientes desea lanzar? "))
        if n < 1:
            print("Ingrese un número mayor a 0.")
        else:
            break
    except ValueError:
        print("Por favor ingrese un número válido.")
 
# Start N client processes
processes = []
queues = []
 
for i in range(n):
    p = subprocess.Popen(
        [sys.executable, "client.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    q = queue.Queue()
    name = f"Cliente{i+1}"
 
    threading.Thread(target=pipe_to_process, args=(p, q, name), daemon=True).start()
    threading.Thread(target=read_output, args=(p, name), daemon=True).start()
 
    processes.append(p)
    queues.append(q)
 
print(f"\n=== Lanzador de {n} cliente(s) ===")
print("Comandos:")
for i in range(1, n+1):
    print(f"  {i}:<input>   -> enviar al Cliente {i} solamente")
print("  *:<input>    -> enviar a TODOS los clientes al mismo tiempo")
print("  q            -> salir")
print("=" * 30 + "\n")
 
time.sleep(0.5)
 
while True:
    try:
        cmd = input()
    except EOFError:
        break
 
    if cmd == "q":
        for q in queues:
            q.put(None)
        break
    elif cmd.startswith("*:"):
        msg = cmd[2:]
        for q in queues:
            q.put(msg)
    else:
        if ":" in cmd:
            prefix, msg = cmd.split(":", 1)
            if prefix.isdigit():
                idx = int(prefix) - 1
                if 0 <= idx < n:
                    queues[idx].put(msg)
                else:
                    print(f"Número de cliente inválido. Elija entre 1 y {n}.")
            else:
                print(f"Use  <número>:<input>  o  *:<input>")
        else:
            print(f"Use  <número>:<input>  o  *:<input>")
 
for p in processes:
    p.terminate()
 
