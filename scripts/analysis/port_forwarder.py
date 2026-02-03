#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Simple port forwarder for backend access"""

import os
import socket
import threading


def forward_connection(client_socket, target_host, target_port):
    """Forward data between client and target server"""
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect((target_host, target_port))

        def forward_data(source, destination):
            while True:
                try:
                    data = source.recv(4096)
                    if not data:
                        break
                    destination.send(data)
                except Exception:
                    break

        # Start forwarding in both directions
        client_to_server = threading.Thread(
            target=forward_data, args=(client_socket, server_socket)
        )
        server_to_client = threading.Thread(
            target=forward_data, args=(server_socket, client_socket)
        )

        client_to_server.daemon = True
        server_to_client.daemon = True

        client_to_server.start()
        server_to_client.start()

        client_to_server.join()
        server_to_client.join()

    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        client_socket.close()
        if "server_socket" in locals():
            server_socket.close()


def start_forwarder(listen_host, listen_port, target_host, target_port):
    """Start the port forwarder"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((listen_host, listen_port))
        server.listen(5)
        print(
            f"Port forwarder started: {listen_host}:{listen_port} -> {target_host}:{target_port}"
        )

        while True:
            client_socket, addr = server.accept()
            print(f"Connection from {addr}")

            thread = threading.Thread(
                target=forward_connection,
                args=(client_socket, target_host, target_port),
            )
            thread.daemon = True
            thread.start()

    except KeyboardInterrupt:
        print("\nShutting down forwarder...")
    except Exception as e:
        print(f"Forwarder error: {e}")
    finally:
        server.close()


if __name__ == "__main__":
    # Get configuration from environment variables
    listen_host = os.getenv("FORWARD_LISTEN_HOST", "127.0.0.3")
    listen_port = int(os.getenv("FORWARD_LISTEN_PORT", "8001"))
    target_host = os.getenv("FORWARD_TARGET_HOST", "127.0.0.1")
    target_port = int(os.getenv("FORWARD_TARGET_PORT", "8001"))

    start_forwarder(listen_host, listen_port, target_host, target_port)
