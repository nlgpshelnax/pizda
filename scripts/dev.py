"""Local development launcher. No secrets, dotenv files, or external paid APIs needed."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "divannie-analytiki"
FRONT = ROOT / "front" / "frontend"
PYTHON = AGENT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MODEL = "qwen2.5:7b-instruct"
CHILDREN = []
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def run(args, cwd=ROOT):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def get_json(url):
    with HTTP.open(url, timeout=3) as response:
        return json.load(response)


def available(url):
    try:
        return get_json(url)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def spawn(args, cwd=ROOT, env=None):
    process = subprocess.Popen([str(a) for a in args], cwd=cwd, env=env)
    CHILDREN.append(process)
    return process


def wait_for(url, process, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Процесс завершился до готовности: {url}")
        value = available(url)
        if value is not None:
            return value
        time.sleep(0.5)
    raise RuntimeError(f"Не дождались запуска: {url}")


def port_free(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            raise RuntimeError(f"Порт {port} занят. Остановите старый процесс: lsof -nP -iTCP:{port} -sTCP:LISTEN") from None


def prerequisites():
    for binary in ("node", "npm", "ollama"):
        if not shutil.which(binary):
            raise RuntimeError(f"Не найдена команда {binary}. Установите её по инструкции README.md.")
    major = int(subprocess.check_output(["node", "-p", "process.versions.node.split('.')[0]"], text=True).strip())
    if major < 22:
        raise RuntimeError("Нужен Node.js 22.12+ (рекомендуется 24 LTS).")
    if sys.version_info < (3, 10):
        raise RuntimeError("Нужен Python 3.10+ (рекомендуется 3.12).")


def ollama_ready():
    if available("http://localhost:11434/v1/models") is None:
        print("Запускаю Ollama…", flush=True)
        process = spawn(["ollama", "serve"])
        wait_for("http://localhost:11434/v1/models", process)
    models = get_json("http://localhost:11434/v1/models")
    if not any(item["id"] == MODEL for item in models.get("data", [])):
        print("Скачиваю Qwen (первый раз — несколько ГБ)…", flush=True)
        run(["ollama", "pull", MODEL])


def dependencies(force=False):
    if not PYTHON.exists():
        run([sys.executable, "-m", "venv", AGENT / ".venv"])
        force = True
    if force or subprocess.run([str(PYTHON), "-c", "import fastapi,uvicorn,pydantic,httpx"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run([PYTHON, "-m", "pip", "install", "-r", AGENT / "requirements-local.txt"])
    if force or not (FRONT / "node_modules" / "vite" / "bin" / "vite.js").exists():
        run(["npm", "ci"], FRONT)


def check():
    run([PYTHON, ROOT / "scripts" / "check_backend.py"])
    run(["node", "node_modules/typescript/bin/tsc", "-b"], FRONT)
    run(["node", "node_modules/vite/bin/vite.js", "build"], FRONT)
    run(["node", "node_modules/vitest/vitest.mjs", "run"], FRONT)


def start():
    # Refuse occupied ports before starting any component. Never kill unrelated processes.
    port_free(8000)
    port_free(8080)
    dependencies()
    ollama_ready()
    env = dict(os.environ, OLLAMA_HOST="http://localhost:11434/v1", OLLAMA_MODEL=MODEL,
               VITE_AGENT_API_URL="http://localhost:8000")
    api = spawn([PYTHON, "-m", "uvicorn", "agent_api:app", "--host", "127.0.0.1", "--port", "8000"], AGENT, env)
    wait_for("http://localhost:8000/api/health", api)
    ui = spawn(["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "8080", "--strictPort"], FRONT, env)
    wait_for("http://localhost:8080/health", ui)
    print("\nГОТОВО: откройте http://localhost:8080\nОстановка всех запущенных скриптом компонентов: Ctrl+C\n", flush=True)
    while True:
        for process in CHILDREN:
            if process.poll() is not None:
                raise RuntimeError("Один из компонентов завершился. Смотрите ошибку выше.")
        time.sleep(0.5)


def cleanup():
    for process in reversed(CHILDREN):
        if process.poll() is None:
            process.terminate()
    for process in reversed(CHILDREN):
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description="Запуск UI + Agent API + Ollama")
    parser.add_argument("command", choices=["setup", "start", "check"])
    command = parser.parse_args().command
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        prerequisites()
        if command == "setup":
            dependencies(force=True)
            ollama_ready()
            print("Готово. Для запуска: bash start.sh")
        elif command == "check":
            dependencies()
            check()
        else:
            start()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"\nОшибка: {exc}", file=sys.stderr)
        return 1
    finally:
        cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
