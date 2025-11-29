import os
import shlex
import socket
import sys
import re

# Расширяет переменные окружения вида $VAR или ${VAR}
def expand_env(token):
    # поддержка экранирования \$ -> $
    token = token.replace(r'\$', '\0')  # временно пометить экранированные $
    pattern = re.compile(r'\$(\w+)|\$\{([^}]+)\}')
    def repl(m):
        name = m.group(1) or m.group(2)
        return os.environ.get(name, '')
    result = pattern.sub(repl, token)
    result = result.replace('\0', '$')
    return result

# Формирует приглашение вида user@host:cwd$
def make_prompt():
    user = os.environ.get('USER') or os.environ.get('USERNAME') or 'user'
    host = socket.gethostname()
    cwd = os.getcwd()
    home = os.path.expanduser('~')
    if cwd.startswith(home):
        cwd_display = '~' + cwd[len(home):] if cwd != home else '~'
    else:
        cwd_display = cwd
    return f"{user}@{host}:{cwd_display}$ "

# Обрабатывает одну команду (name и список аргументов)
def handle_command(cmd_name, args):
    if cmd_name == '':
        return True  # пустая строка -> продолжить
    if cmd_name == 'exit':
        return False  # завершить REPL
    if cmd_name in ('ls', 'cd'):
        # заглушка: выводим имя команды и аргументы
        print(f"[stub] {cmd_name} {' '.join(args) if args else '(no args)'}")
        # Для cd можно попытаться сменить каталог, но так как требование — заглушка, не обязательно.
        # Здесь сделаем попытку смены каталога если указан аргумент и он существует (удобно для демо).
        if cmd_name == 'cd' and args:
            try:
                os.chdir(args[0])
            except Exception as e:
                print(f"cd: {e}")
        return True
    # неизвестная команда
    print(f"Command not found: {cmd_name}")
    return True

# Парсер строки ввода: разбиваем, расширяем переменные
def parse_input(line):
    try:
        parts = shlex.split(line)
    except ValueError as e:
        # ошибка разбора (например, незакрытая кавычка)
        print(f"Parse error: {e}")
        return None, None
    expanded = [expand_env(tok) for tok in parts]
    if not expanded:
        return '', []
    return expanded[0], expanded[1:]

# Главный REPL
def repl():
    while True:
        try:
            prompt = make_prompt()
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()  # перевод строки при Ctrl+D/Ctrl+C
            break
        name, args = parse_input(line)
        if name is None:
            # ошибка парсера -> продолжить
            continue
        cont = handle_command(name, args)
        if not cont:
            break

if __name__ == '__main__':
    repl()
