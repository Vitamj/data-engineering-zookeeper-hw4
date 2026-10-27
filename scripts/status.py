import socket


def command(port, text="srvr"):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5) as sock:
            sock.sendall(text.encode())
            sock.settimeout(1.5)
            data = sock.recv(8192).decode(errors="replace")
            return data.strip()
    except OSError as error:
        return f"UNAVAILABLE ({type(error).__name__})"


for server, port in enumerate((2181, 2182, 2183), start=1):
    result = command(port)
    role = next((line for line in result.splitlines() if line.startswith("Mode:")), "")
    print(f"server={server} port={port} {role or result.splitlines()[0] if result else 'NO RESPONSE'}")
