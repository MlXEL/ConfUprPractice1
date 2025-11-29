import os
import shlex
import socket
import sys
import re
import argparse

# Расширяет переменные окружения вида $VAR или ${VAR}
def expand_env(token):
    token = token.replace(r'\$', '\0')  # временно пометить экранированные $
    pattern = re.compile(r'\$(\w+)|\$\{([^}]+)\}')
    def repl(m):
        name = m.group(1) or m.group(2)
        return os.environ.get(name, '')
    result = pattern.sub(repl, token)
    result = result.replace('\0', '$')
    return result

# Формирует приглашение вида user@host:cwd$
# Если передан prompt_override — используем его (может содержать %u %h %d для user, host, cwd)
def make_prompt(prompt_override=None):
    user = os.environ.get('USER') or os.environ.get('USERNAME') or 'user'
    host = socket.gethostname()
    cwd = os.getcwd()
    home = os.path.expanduser('~')
    if cwd.startswith(home):
        cwd_display = '~' + cwd[len(home):] if cwd != home else '~'
    else:
        cwd_display = cwd
    if prompt_override:
        # Простая подстановка маркеров
        return prompt_override.replace('%u', user).replace('%h', host).replace('%d', cwd_display)
    return f"{user}@{host}:{cwd_display}$ "

# Обрабатывает одну команду (name и список аргументов)
# script_mode: если True -> при ошибке возвращаем False чтобы остановить исполнение скрипта
def handle_command(cmd_name, args, script_mode=False):
    if cmd_name == '':
        return True
    if cmd_name == 'exit':
        return False
    if cmd_name in ('ls', 'cd'):
        print(f"[stub] {cmd_name} {' '.join(args) if args else '(no args)'}")
        if cmd_name == 'cd' and args:
            try:
                os.chdir(args[0])
            except Exception as e:
                print(f"cd: {e}")
                return False if script_mode else True
        return True
    # неизвестная команда
    msg = f"Command not found: {cmd_name}"
    print(msg)
    # в режиме скрипта неизвестная команда считается ошибкой
    return False if script_mode else True

# Парсер строки ввода: разбиваем, расширяем переменные
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

# Выполнение стартового скрипта: останавливается при первой ошибке
# Каждый выполняемый шаг печатает строку как будто её ввёл пользователь
def run_startup_script(path, prompt_override):
    if not os.path.exists(path):
        print(f"Startup script not found: {path}")
        return False
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading startup script: {e}")
        return False

    for raw_line in lines:
        line = raw_line.rstrip('\n')
        # строку пустую или комментарий пропускаем (но по условию показываем ввод — покажем всё кроме комментариев)
        if line.strip().startswith('#'):
            # показать комментарий как комментарий скрипта
            print(f"# {line.strip()[1:].strip()}")
            continue
        # показать как ввод пользователя (prompt + команда)
        prompt = make_prompt(prompt_override)
        print(f"{prompt}{line}")
        name, args = parse_input(line)
        if name is None:
            print(f"Error: parse error in startup script at line: {line}")
            return False
        cont = handle_command(name, args, script_mode=True)
        if not cont:
            print(f"Error: stopped on command: {name} {(' '.join(args)) if args else ''}")
            return False
    return True

# Главный REPL
def repl(prompt_override=None):
    while True:
        try:
            prompt = make_prompt(prompt_override)
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        name, args = parse_input(line)
        if name is None:
            continue
        cont = handle_command(name, args, script_mode=False)
        if not cont:
            break

# Точка входа: парсим параметры и запускаем
def main():
    parser = argparse.ArgumentParser(description='Minimal shell emulator (stage 2)')
    parser.add_argument('--vfs-path', help='Path to physical VFS (ZIP file)', default=None)
    parser.add_argument('--prompt', help='Custom prompt (use %u user, %h host, %d cwd)', default=None)
    parser.add_argument('--startup-script', help='Path to startup script to execute', default=None)
    args = parser.parse_args()

    # Отладочный вывод всех параметров
    print("Debug: emulator start parameters")
    print(f"VFS path      : {args.vfs_path}")
    print(f"Prompt override: {args.prompt}")
    print(f"Startup script : {args.startup_script}")
    print("End debug\n")

    # Если задан стартовый скрипт — выполнить и остановиться если ошибка
    if args.startup_script:
        ok = run_startup_script(args.startup_script, args.prompt)
        if not ok:
            print("Startup script execution failed.")
            sys.exit(1)
        else:
            print("Startup script finished successfully.\n")

    # Запуск интерактивного REPL
    repl(args.prompt)

if __name__ == '__main__':
    main()
