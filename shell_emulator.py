#!/usr/bin/env python3
import os
import shlex
import socket
import sys
import re
import argparse
import zipfile
import base64

# --- ХРАНЕНИЕ ИСТОРИИ ---
command_history = []

# -------------------------------------------------------------
# VFS — виртуальная файловая система
# -------------------------------------------------------------
class VFS:
    def __init__(self):
        self.root = {}          # корень — dict
        self.cwd = []           # текущий путь в виде списка: ["home", "user"]

    # Добавление файла
    def add_file(self, path, data):
        parts = path.split('/')
        cur = self.root
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = {'type': 'file', 'data': data}

    # Добавление каталогов
    def add_dir(self, path):
        parts = path.split('/')
        cur = self.root
        for p in parts:
            cur = cur.setdefault(p, {})

    # Нахождение узла по пути (теперь всегда абсолютный путь от корня)
    def resolve(self, path):
        if isinstance(path, str):
            # Если строка, она должна быть абсолютной
            if path.startswith('/'):
                parts = path.strip('/').split('/') if path.strip('/') else []
            else:
                # Относительный путь не поддерживается в resolve, только абсолютный
                # Для текущего пути используем self.cwd
                raise ValueError("Use resolve([]) for current path or pass absolute path list.")
        else:
            # Предполагаем, что это список (абсолютный путь от корня)
            parts = path

        cur = self.root
        for p in parts:
            if p == '' or p == '.':
                continue
            # .. не обрабатывается здесь
            if p not in cur or not isinstance(cur[p], dict):
                return None
            cur = cur[p]
        return cur

    # Переход в каталог
    def cd(self, path):
        # --- ИСПРАВЛЕНИЕ CD: Обработка относительного и абсолютного пути ---
        if path.startswith('/'):
            new_parts = path.strip('/').split('/') if path.strip('/') else []
        else:
            # Относительный путь: добавляем к текущему
            new_parts = self.cwd + (path.split('/') if path else [])

        # --- ИСПРАВЛЕНИЕ CD: Обработка . и .. ---
        resolved_cwd = []
        for part in new_parts:
            if part == '.' or part == '':
                continue
            elif part == '..':
                if resolved_cwd:
                    resolved_cwd.pop()
                # else: уже на вершине, остаёмся на месте
            else:
                resolved_cwd.append(part)

        # --- ИСПРАВЛЕНИЕ CD: Проверка, что путь существует и это каталог ---
        target_node = self.resolve(resolved_cwd)
        if target_node is None:
            # Путь не существует
            return False
        if 'type' in target_node and target_node['type'] == 'file':
            # Это файл, а не каталог
            return False

        # Применяем путь
        self.cwd = resolved_cwd
        return True


    # Список файлов
    def ls(self):
        node = self.resolve(self.cwd) # Используем текущий путь как абсолютный
        if node is None:
            return []
        # Проверяем, что это каталог, а не файл
        if 'type' in node and node['type'] == 'file':
            print("ls: not a directory")
            return []
        return list(node.keys()) if node else []

    # Текущий путь
    def pwd(self):
        return "/" + "/".join(self.cwd)


# -------------------------------------------------------------
# Утилиты
# -------------------------------------------------------------
def expand_env(token):
    token = token.replace(r'\$', '\0')
    pattern = re.compile(r'\$(\w+)|\$\{([^}]+)\}')
    def repl(m):
        name = m.group(1) or m.group(2)
        return os.environ.get(name, '')
    result = pattern.sub(repl, token)
    return result.replace('\0', '$')


def make_prompt(vfs, prompt_override=None):
    user = os.environ.get('USER') or os.environ.get('USERNAME') or 'user'
    host = socket.gethostname()
    cwd = vfs.pwd() if vfs else "~"

    if prompt_override:
        return prompt_override.replace('%u', user).replace('%h', host).replace('%d', cwd)
    return f"{user}@{host}:{cwd}$ "


def parse_input(line):
    try:
        parts = shlex.split(line)
    except ValueError as e:
        print(f"Parse error: {e}")
        return None, None
    expanded = [expand_env(tok) for tok in parts]
    if not expanded:
        return '', []
    return expanded[0], expanded[1:]


# -------------------------------------------------------------
# Загрузка VFS из ZIP
# -------------------------------------------------------------
def load_vfs_from_zip(path):
    v = VFS()
    try:
        with zipfile.ZipFile(path, 'r') as z:
            for name in z.namelist():
                if name.endswith('/'):
                    v.add_dir(name.rstrip('/'))
                else:
                    raw = z.read(name)
                    # Если файл — base64-данные — попробуем декодировать
                    try:
                        raw = base64.b64decode(raw)
                    except Exception:
                        pass
                    v.add_file(name, raw)
        return v
    except Exception as e:
        print(f"VFS load error: {e}")
        return None


# -------------------------------------------------------------
# Обработка команд
# -------------------------------------------------------------
def handle_command(cmd, args, vfs, script_mode=False):
    global command_history # Для доступа к глобальной истории

    # exit
    if cmd == 'exit':
        return False

    # echo
    if cmd == 'echo':
        print(" ".join(args))
        return True

    # pwd
    if cmd == 'pwd':
        print(vfs.pwd())
        return True

    # ls
    if cmd == 'ls':
        items = vfs.ls()
        # Вывод уже производится в ls, если это файл
        if items: # Только если список не пустой (и не None)
            print("  ".join(items))
        return True

    # cd
    if cmd == 'cd':
        if not args:
            print("cd: missing argument")
            return False if script_mode else True
        if not vfs.cd(args[0]):
            print(f"cd: no such directory: {args[0]}")
            return False if script_mode else True
        return True

    # find
    if cmd == 'find':
        if not args:
            print("find: missing argument")
            return False if script_mode else True
        search_name = args[0]

        results = []
        def find_recursive(node, current_path):
            for key, value in node.items():
                full_path = current_path + '/' + key if current_path else key
                if key == search_name:
                    results.append(full_path)
                if isinstance(value, dict) and 'type' not in value:
                    find_recursive(value, full_path)

        find_recursive(vfs.root, '')
        for res in results:
            print(res)
        return True

    # history
    if cmd == 'history':
        for i, entry in enumerate(command_history, 1):
            print(f"{i:3}: {entry}")
        return True

    # help
    if cmd == 'help':
        print("Available commands:")
        print("  exit")
        print("  echo <arg>")
        print("  pwd")
        print("  ls")
        print("  cd <path>")
        print(" cd .. (возврат)")
        print("  find <file_or_catalog>")
        print("  history")
        print("  help")
        return True

    # неизвестная команда
    print(f"Command not found: {cmd}")
    return False if script_mode else True


# -------------------------------------------------------------
# Выполнение стартового скрипта
# -------------------------------------------------------------
def run_startup_script(path, prompt, vfs):
    if not os.path.exists(path):
        print(f"Startup script not found: {path}")
        return False

    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Script read error: {e}")
        return False

    for raw in lines:
        line = raw.rstrip("\n")
        if line.strip().startswith('#'):
            print(f"# {line.strip()[1:].strip()}")
            continue

        print(make_prompt(vfs, prompt) + line)
        cmd, args = parse_input(line)
        if cmd is None:
            print("Script: parse error")
            return False

        # --- ДОБАВЛЕНО: Сохранение команды в историю ---
        command_history.append(line)

        ok = handle_command(cmd, args, vfs, script_mode=True)
        if not ok:
            print(f"Script stopped at: {line}")
            return False

    return True


# -------------------------------------------------------------
# REPL
# -------------------------------------------------------------
def repl(prompt_override, vfs):
    while True:
        try:
            line = input(make_prompt(vfs, prompt_override))
        except (EOFError, KeyboardInterrupt):
            print()
            break

        cmd, args = parse_input(line)
        if cmd is None:
            continue

        # --- ДОБАВЛЕНО: Сохранение команды в историю ---
        command_history.append(line)

        cont = handle_command(cmd, args, vfs, script_mode=False)
        if not cont:
            break


# -------------------------------------------------------------
# main()
# -------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Shell emulator with VFS (Stage 4)")
    parser.add_argument("--vfs-path", help="ZIP file containing VFS", required=True)
    parser.add_argument("--prompt", help="Custom prompt (%u,%h,%d)", default=None)
    parser.add_argument("--startup-script", help="Script to run before REPL", default=None)
    args = parser.parse_args()

    print("=== Debug parameters ===")
    print("vfs-path:", args.vfs_path)
    print("prompt  :", args.prompt)
    print("script  :", args.startup_script)
    print("========================\n")

    vfs = load_vfs_from_zip(args.vfs_path)
    if not vfs:
        print("Failed to load VFS.")
        sys.exit(1)

    # Стартовый скрипт
    if args.startup_script:
        ok = run_startup_script(args.startup_script, args.prompt, vfs)
        if not ok:
            print("Startup script failed.")
            sys.exit(1)
        print("Startup script OK.\n")

    # REPL
    repl(args.prompt, vfs)


if __name__ == "__main__":
    main()