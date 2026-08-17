"""Reach Windows-localhost Ollama from WSL.

WSL2 NAT cannot connect to a Windows process bound to 127.0.0.1, and office
firewalls often block the hypervisor vNIC even when Ollama listens on 0.0.0.0.
Windows curl.exe uses the Windows network stack, so ``http://127.0.0.1:11434``
works from WSL without admin or system environment variables.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

WIN_CURL = Path("/mnt/c/Windows/System32/curl.exe")


def running_in_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def use_windows_ollama_bridge(base_url: str) -> bool:
    if not running_in_wsl() or not WIN_CURL.is_file():
        return False
    host = (urlparse(base_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def ollama_transport(
    explicit: httpx.AsyncBaseTransport | None, base_url: str
) -> httpx.AsyncBaseTransport | None:
    if explicit is not None:
        return explicit
    if use_windows_ollama_bridge(base_url):
        return WindowsLocalhostCurlTransport()
    return None


def _windows_url(url: httpx.URL) -> str:
    parsed = urlparse(str(url))
    host = "127.0.0.1"
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    return urlunparse(parsed._replace(netloc=netloc))


class _ProcStream(httpx.AsyncByteStream):
    def __init__(self, proc: asyncio.subprocess.Process, first: bytes):
        self._proc = proc
        self._first = first

    async def __aiter__(self):
        if self._first:
            yield self._first
            self._first = b""
        assert self._proc.stdout is not None
        while True:
            chunk = await self._proc.stdout.read(2048)
            if not chunk:
                break
            yield chunk

    async def aclose(self) -> None:
        if self._proc.returncode is None:
            self._proc.kill()
            await self._proc.wait()


class WindowsLocalhostCurlTransport(httpx.AsyncBaseTransport):
    """httpx transport that issues requests through Windows curl.exe."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = _windows_url(request.url)
        body = await request.aread()
        cmd: list[str] = [
            str(WIN_CURL),
            "-sS",
            "-N",
            "--http1.1",
            "-i",
            "-X",
            request.method,
            url,
        ]
        for key, value in request.headers.items():
            if key.lower() in {"host", "content-length", "connection"}:
                continue
            cmd.extend(["-H", f"{key}: {value}"])
        if body:
            cmd.extend(["--data-binary", "@-"])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            raise httpx.ConnectError(f"windows curl.exe failed to start: {exc}") from exc

        if proc.stdin is not None:
            if body:
                proc.stdin.write(body)
            proc.stdin.close()

        assert proc.stdout is not None
        header_blob, remainder = await _read_header_block(proc.stdout)
        if not header_blob:
            await proc.wait()
            raise httpx.ConnectError("windows curl.exe returned no response from Ollama")

        status, headers = _parse_headers(header_blob)
        return httpx.Response(
            status,
            headers=headers,
            stream=_ProcStream(proc, remainder),
            request=request,
        )


async def _read_header_block(stdout: asyncio.StreamReader) -> tuple[bytes, bytes]:
    buf = b""
    while True:
        for sep in (b"\r\n\r\n", b"\n\n"):
            if sep in buf:
                header, rest = buf.split(sep, 1)
                return header, rest
        chunk = await stdout.read(256)
        if not chunk:
            return buf, b""
        buf += chunk


def _parse_headers(header_blob: bytes) -> tuple[int, list[tuple[bytes, bytes]]]:
    lines = header_blob.replace(b"\r\n", b"\n").split(b"\n")
    # curl -i may include HTTP/1.1 100 Continue; take the last status line block
    status = 502
    headers: list[tuple[bytes, bytes]] = []
    current: list[tuple[bytes, bytes]] = []
    for line in lines:
        if line.upper().startswith(b"HTTP/"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                status = int(parts[1])
                current = []
            continue
        if b":" in line:
            key, value = line.split(b":", 1)
            current.append((key.strip(), value.strip()))
    headers = current
    return status, headers
