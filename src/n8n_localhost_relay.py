"""Optional TCP relay so ``localhost:5678`` works inside the API container.

When the API runs in Docker and n8n is published on the host (:5678), a
loopback listener forwards to ``host.docker.internal:5678``. Application code
keeps calling ``http://localhost:5678/...`` - no URL rewrite to internal hosts.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from pathlib import Path

log = logging.getLogger("edifact.n8n_localhost_relay")

_relay_started = False
_relay_lock = threading.Lock()


def _running_in_docker() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("IN_DOCKER", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _relay_enabled() -> bool:
    raw = (os.environ.get("N8N_LOCALHOST_RELAY") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            src.shutdown(socket.SHUT_RD)
        except OSError:
            pass
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _serve_client(client: socket.socket, upstream_host: str, upstream_port: int) -> None:
    upstream: socket.socket | None = None
    try:
        upstream = socket.create_connection((upstream_host, upstream_port), timeout=10)
        t1 = threading.Thread(target=_pipe, args=(client, upstream), daemon=True)
        t2 = threading.Thread(target=_pipe, args=(upstream, client), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except OSError as exc:
        log.debug("n8n localhost relay connection failed: %s", exc)
    finally:
        try:
            client.close()
        except OSError:
            pass
        if upstream is not None:
            try:
                upstream.close()
            except OSError:
                pass


def _listen_loop(listen_host: str, listen_port: int, upstream_host: str, upstream_port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((listen_host, listen_port))
        sock.listen(32)
        log.info(
            "n8n localhost relay: %s:%s → %s:%s",
            listen_host,
            listen_port,
            upstream_host,
            upstream_port,
        )
        while True:
            client, _addr = sock.accept()
            threading.Thread(
                target=_serve_client,
                args=(client, upstream_host, upstream_port),
                daemon=True,
            ).start()
    except OSError as exc:
        log.warning("n8n localhost relay stopped: %s", exc)
    finally:
        try:
            sock.close()
        except OSError:
            pass


def start_n8n_localhost_relay() -> bool:
    """Start once: 127.0.0.1:5678 → host.docker.internal:5678 (Docker only)."""
    global _relay_started
    with _relay_lock:
        if _relay_started:
            return True
        if not _running_in_docker() or not _relay_enabled():
            return False

        listen_host = (os.environ.get("N8N_LOCALHOST_RELAY_BIND") or "127.0.0.1").strip()
        listen_port = int(os.environ.get("N8N_LOCALHOST_RELAY_PORT") or "5678")
        upstream_host = (os.environ.get("N8N_LOCALHOST_RELAY_UPSTREAM_HOST") or "host.docker.internal").strip()
        upstream_port = int(os.environ.get("N8N_LOCALHOST_RELAY_UPSTREAM_PORT") or "5678")

        # Fail fast if port already taken (another process / previous relay).
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((listen_host, listen_port))
        except OSError as exc:
            log.info("n8n localhost relay skipped (bind %s:%s): %s", listen_host, listen_port, exc)
            return False
        finally:
            probe.close()

        thread = threading.Thread(
            target=_listen_loop,
            args=(listen_host, listen_port, upstream_host, upstream_port),
            name="n8n-localhost-relay",
            daemon=True,
        )
        thread.start()
        _relay_started = True
        return True
