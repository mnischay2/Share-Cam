import os
import pty
import socket
import select

HOST = '127.0.0.1'
PORT = 9999

def main():
    # Create a pseudo-terminal (PTY) pair
    master, slave = pty.openpty()
    slave_name = os.ttyname(slave)
    
    print(f"[*] Dummy device created at: {slave_name}")
    print(f"[*] You can read/write to this device using standard tools (e.g., cat, echo, or PySerial).")
    
    # Setup TCP Server Socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(1)
    
    print(f"[*] Listening for TCP connections on {HOST}:{PORT}...")
    
    while True:
        client_socket, addr = server_socket.accept()
        print(f"[+] Socket client connected from {addr}")
        
        # Monitor both the PTY master file descriptor and the socket for incoming data
        inputs = [master, client_socket]
        
        try:
            while True:
                readable, _, _ = select.select(inputs, [], [])
                
                for fd in readable:
                    if fd is master:
                        # Data received from the dummy device -> Send to Socket
                        data = os.read(master, 1024)
                        if data:
                            client_socket.sendall(data)
                    
                    elif fd is client_socket:
                        # Data received from the Socket -> Write to Dummy device
                        data = client_socket.recv(1024)
                        if data:
                            os.write(master, data)
                        else:
                            # Client disconnected (empty byte string)
                            raise ConnectionResetError
        except (ConnectionResetError, BrokenPipeError):
            print("[-] Client disconnected. Waiting for new connection...")
        finally:
            client_socket.close()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[*] Exiting...")