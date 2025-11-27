"""
batalha_p2p_pygame.py
Jogo P2P Batalha Naval - Pygame + UDP(5000)/TCP(5001)
Como usar: python3 batalha_p2p_pygame.py
"""

import socket
import threading
import pygame
import random
import time
import ast
import sys
import traceback

# CONFIGURAÇÕES

GRID_SIZE = 10
CELL = 48
SIDEBAR = 320
WIDTH = GRID_SIZE * CELL + SIDEBAR
HEIGHT = GRID_SIZE * CELL + 260
FPS = 30

UDP_PORT = 5000
TCP_PORT = 5001
COOLDOWN = 5.0

ship_x = random.randint(0, GRID_SIZE - 1)
ship_y = random.randint(0, GRID_SIZE - 1)

participants = []
participants_lock = threading.Lock()

pending_action = None
pending_lock = threading.Lock()

last_sent_time = 0.0
last_sent_lock = threading.Lock()

hits_received = 0
hits_by_us = {}
hits_lock = threading.Lock()

message_log = []
log_lock = threading.Lock()
MAX_LOG = 200

RUNNING = True


# LOG

def log(s):
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {s}"
    with log_lock:
        message_log.append(entry)
        if len(message_log) > MAX_LOG:
            message_log.pop(0)
    print(entry)


# UTILITÁRIOS DE REDE

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

OWN_IP = get_local_ip()


def safe_add_participant(ip):
    if ip == OWN_IP:
        return False
    with participants_lock:
        if ip in participants:
            return False
        participants.append(ip)
    log(f"Participante adicionado: {ip} -> {participants}")
    return True


def safe_remove_participant(ip):
    with participants_lock:
        if ip in participants:
            participants.remove(ip)
            log(f"Participante removido: {ip}")


# SOCKETS

def make_udp_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    except Exception:
        pass
    s.bind(('', UDP_PORT))
    return s


def make_tcp_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    s.bind(('', TCP_PORT))
    s.listen(5)
    return s


# HANDLERS UDP e TCP

def handle_udp_message(msg, addr_ip):
    global hits_received

    msg = msg.strip()
    log(f"UDP <- {addr_ip}: '{msg}'")

    if msg == "Conectando":
        added = safe_add_participant(addr_ip)
        with participants_lock:
            plist = [p for p in participants if p != OWN_IP]
        if addr_ip not in plist:
            plist.append(addr_ip)

        payload = f"participantes: {plist}"
        threading.Thread(target=send_tcp, args=(addr_ip, payload), daemon=True).start()

    elif msg.startswith("shot:"):
        try:
            tail = msg.split(":", 1)[1]
            x_str, y_str = tail.split(",")
            x = int(x_str)
            y = int(y_str)
        except:
            log("Formato inválido de 'shot'")
            return

        if x == ship_x and y == ship_y:
            threading.Thread(target=send_tcp, args=(addr_ip, "hit"), daemon=True).start()
            with hits_lock:
                hits_received += 1
            log(f"Fui atingido por {addr_ip} em ({x},{y})")
        else:
            log(f"Tiro de {addr_ip} em ({x},{y}) -> errou")

    elif msg == "moved":
        log(f"{addr_ip} se moveu.")

    elif msg == "saindo":
        safe_remove_participant(addr_ip)

    else:
        log(f"Mensagem UDP desconhecida: {msg}")


def handle_tcp_message(msg, addr_ip, reply_socket=None):
    global hits_received

    msg = msg.strip()
    log(f"TCP <- {addr_ip}: '{msg}'")

    if msg.startswith("participantes:"):
        try:
            rhs = msg.split(":", 1)[1].strip()
            plist = ast.literal_eval(rhs)
            for ip in plist:
                if isinstance(ip, str) and ip != OWN_IP:
                    safe_add_participant(ip)
            safe_add_participant(addr_ip)
        except Exception as e:
            log(f"Erro parse participantes: {e}")

    elif msg.startswith("scout:"):
        try:
            rhs = msg.split(":", 1)[1]
            x_str, y_str = rhs.split(",")
            x = int(x_str)
            y = int(y_str)
        except:
            log("Formato inválido de scout.")
            return

        if x == ship_x and y == ship_y:
            threading.Thread(target=send_tcp, args=(addr_ip, "hit"), daemon=True).start()
            with hits_lock:
                hits_received += 1
        else:
            x_rel = 1 if ship_x > x else -1
            y_rel = 1 if ship_y > y else -1
            payload = f"info:{x_rel},{y_rel}"
            threading.Thread(target=send_tcp, args=(addr_ip, payload), daemon=True).start()

    elif msg == "hit":
        with hits_lock:
            hits_by_us.setdefault(addr_ip, 0)
            hits_by_us[addr_ip] += 1

    elif msg.startswith("info:"):
        try:
            rhs = msg.split(":", 1)[1]
            xr, yr = rhs.split(",")
            xr = int(xr)
            yr = int(yr)
            log(f"Dica recebida de {addr_ip}: x_rel={xr}, y_rel={yr}")
        except:
            log("Formato inválido info.")

    else:
        log(f"TCP desconhecido: {msg}")


# ENVIO

def send_udp(ip, text):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(text.encode(), (ip, UDP_PORT))
        s.close()
        log(f"UDP -> {ip}: '{text}'")
    except Exception as e:
        log(f"Erro UDP: {e}")


def broadcast_conectar():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(b"Conectando", ('<broadcast>', UDP_PORT))
        s.close()
        log("Broadcast enviado.")
    except Exception as e:
        log(f"Erro broadcast: {e}")


def send_tcp(ip, text):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((ip, TCP_PORT))
        s.sendall(text.encode())
        try:
            data = s.recv(4096)
            if data:
                handle_tcp_message(data.decode(), ip)
        except:
            pass
        s.close()
        log(f"TCP -> {ip}: '{text}'")
    except Exception as e:
        log(f"Erro TCP -> {ip}: {e}")


# THREADS

def udp_listener_thread():
    try:
        s = make_udp_socket()
    except Exception as e:
        log(f"Erro socket UDP: {e}")
        traceback.print_exc()
        return

    log(f"UDP ativo porta {UDP_PORT}")
    while RUNNING:
        try:
            data, addr = s.recvfrom(4096)
            msg = data.decode(errors="ignore")
            addr_ip = addr[0]
            threading.Thread(target=handle_udp_message, args=(msg, addr_ip), daemon=True).start()
        except Exception as e:
            log(f"Erro UDP listener: {e}")


def tcp_listener_thread():
    try:
        s = make_tcp_socket()
    except Exception as e:
        log(f"Erro socket TCP: {e}")
        traceback.print_exc()
        return

    log(f"TCP ativo porta {TCP_PORT}")

    while RUNNING:
        try:
            conn, addr = s.accept()
            addr_ip = addr[0]
            data = b""
            try:
                conn.settimeout(2.0)
                while True:
                    part = conn.recv(4096)
                    if not part:
                        break
                    data += part
            except:
                pass
            conn.close()
            if data:
                threading.Thread(target=handle_tcp_message, args=(data.decode(errors="ignore"), addr_ip), daemon=True).start()
        except Exception as e:
            log(f"Erro TCP listener: {e}")


def sender_thread():
    global pending_action, ship_x, ship_y, last_sent_time

    log("Sender thread iniciada.")

    while RUNNING:
        time.sleep(0.1)
        with pending_lock:
            action = pending_action
            pending_action = None

        if not action:
            continue

        with last_sent_lock:
            now = time.time()
            wait = COOLDOWN - (now - last_sent_time)
        if wait > 0:
            time.sleep(wait)

        try:
            if action[0] == "shot":
                _, x, y = action
                with participants_lock:
                    targets = participants.copy()
                for ip in targets:
                    send_udp(ip, f"shot:{x},{y}")

            elif action[0] == "scout":
                _, x, y, ip = action
                send_tcp(ip, f"scout:{x},{y}")

            elif action[0] == "move":
                _, sign, axis = action
                if axis == "X":
                    ship_x = max(0, min(GRID_SIZE - 1, ship_x + (1 if sign == "+" else -1)))
                else:
                    ship_y = max(0, min(GRID_SIZE - 1, ship_y + (1 if sign == "+" else -1)))

                with participants_lock:
                    targets = participants.copy()
                for ip in targets:
                    send_udp(ip, "moved")

        except Exception as e:
            log(f"Erro ao enviar ação: {e}")

        with last_sent_lock:
            last_sent_time = time.time()


# PYGAME UI

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Batalha Naval P2P")
font = pygame.font.SysFont("consolas", 16)
bigfont = pygame.font.SysFont("consolas", 20)

selected_cell = None
input_ip = ""
input_active = False

buttons = {}

def init_buttons():
    global buttons
    x0 = GRID_SIZE * CELL + 12
    base = HEIGHT - 180
    buttons = {
        "shot": (pygame.Rect(x0, base, 120, 34), "SHOT"),
        "scout": (pygame.Rect(x0 + 130, base, 120, 34), "SCOUT"),
        "move+X": (pygame.Rect(x0, base + 44, 56, 34), "+ X"),
        "move-X": (pygame.Rect(x0 + 64, base + 44, 56, 34), "- X"),
        "move+Y": (pygame.Rect(x0 + 130, base + 44, 56, 34), "+ Y"),
        "move-Y": (pygame.Rect(x0 + 196, base + 44, 56, 34), "- Y"),
        "ping": (pygame.Rect(x0, base + 92, 120, 34), "PING"),
        "leave": (pygame.Rect(x0 + 130, base + 92, 120, 34), "SAIR"),
    }

init_buttons()


def draw_button(rect, label, hovered=False):
    color = (40, 120, 40) if not hovered else (60, 150, 60)
    pygame.draw.rect(screen, color, rect)
    pygame.draw.rect(screen, (180, 180, 180), rect, 2)
    text = font.render(label, True, (255, 255, 255))
    screen.blit(text, (rect.x + (rect.width - text.get_width()) // 2,
                       rect.y + (rect.height - text.get_height()) // 2))


def draw_ui_controls():
    mouse = pygame.mouse.get_pos()
    for key, (rect, label) in buttons.items():
        draw_button(rect, label, hovered=rect.collidepoint(mouse))


def draw():
    screen.fill((10, 10, 30))

    for gx in range(GRID_SIZE):
        for gy in range(GRID_SIZE):
            rect = pygame.Rect(gx * CELL, gy * CELL, CELL, CELL)
            pygame.draw.rect(screen, (50, 50, 90), rect)
            pygame.draw.rect(screen, (80, 80, 110), rect, 1)

    srect = pygame.Rect(ship_x * CELL + 4, ship_y * CELL + 4, CELL - 8, CELL - 8)
    pygame.draw.rect(screen, (20, 140, 220), srect)

    sidebar_rect = pygame.Rect(GRID_SIZE * CELL, 0, SIDEBAR, HEIGHT)
    pygame.draw.rect(screen, (18, 18, 25), sidebar_rect)

    x0 = GRID_SIZE * CELL + 12
    y = 8

    screen.blit(bigfont.render("Batalha Naval P2P", True, (220, 220, 220)), (x0, y)); y += 28
    screen.blit(font.render(f"Meu IP: {OWN_IP}", True, (200, 200, 200)), (x0, y)); y += 20
    screen.blit(font.render(f"Minha posição: ({ship_x},{ship_y})", True, (200, 200, 200)), (x0, y)); y += 24

    with last_sent_lock:
        passed = time.time() - last_sent_time
    cd = max(0.0, COOLDOWN - passed)
    screen.blit(font.render(f"Cooldown: {cd:.1f}s", True, (255, 200, 50)), (x0, y)); y += 26

    screen.blit(bigfont.render("Participantes", True, (200, 200, 220)), (x0, y)); y += 24

    with participants_lock:
        for p in participants[-10:]:
            screen.blit(font.render(p, True, (170, 170, 170)), (x0, y)); y += 18

    y += 8

    with hits_lock:
        screen.blit(font.render(f"Fui atingido: {hits_received}", True, (255, 120, 120)), (x0, y)); y += 20
        screen.blit(font.render("Hits que causei:", True, (150, 220, 150)), (x0, y)); y += 20
        for ip, h in hits_by_us.items():
            screen.blit(font.render(f"{ip}: {h}", True, (150, 220, 150)), (x0, y)); y += 18

    draw_ui_controls()

    with log_lock:
        lines = message_log[-12:]

    lx = 6
    ly = HEIGHT - (18 * 13) - 6
    box = pygame.Rect(4, ly - 6, GRID_SIZE * CELL - 8, 18 * 13 + 12)

    pygame.draw.rect(screen, (8, 8, 20), box)
    pygame.draw.rect(screen, (40, 40, 60), box, 1)

    for i, line in enumerate(lines):
        screen.blit(font.render(line, True, (200, 200, 200)), (lx, ly + i * 18))

    # input box corrigido
    ibox = pygame.Rect(x0, HEIGHT - 40, 250, 28)
    pygame.draw.rect(screen, (22, 22, 30), ibox)
    pygame.draw.rect(screen, (120, 120, 120), ibox, 2)
    txt = font.render("IP (scout): " + input_ip, True, (210, 210, 210))
    screen.blit(txt, (ibox.x + 6, ibox.y + 5))


def on_click_ui(pos):
    global pending_action, selected_cell, input_ip, input_active, RUNNING
    x, y = pos

    if x < GRID_SIZE * CELL and y < GRID_SIZE * CELL:
        gx = x // CELL
        gy = y // CELL
        selected_cell = (gx, gy)
        log(f"Célula selecionada: {selected_cell}")
        return

    for k, (rect, _) in buttons.items():
        if rect.collidepoint(pos):
            log(f"Botão: {k}")

            if k == "shot":
                if selected_cell:
                    with pending_lock:
                        pending_action = ("shot", selected_cell[0], selected_cell[1])
                else:
                    log("Selecione uma célula.")

            elif k == "scout":
                if input_ip.strip() and selected_cell:
                    with pending_lock:
                        pending_action = ("scout", selected_cell[0], selected_cell[1], input_ip.strip())
                else:
                    log("Digite IP e selecione uma célula.")

            elif k.startswith("move"):
                sign = "+" if "+" in k else "-"
                axis = "X" if "X" in k else "Y"
                with pending_lock:
                    pending_action = ("move", sign, axis)

            elif k == "ping":
                broadcast_conectar()

            elif k == "leave":
                with participants_lock:
                    for ip in participants:
                        send_udp(ip, "saindo")
                finish_and_exit()

            return

    x0 = GRID_SIZE * CELL + 12
    ibox = pygame.Rect(x0, HEIGHT - 40, 250, 28)
    input_active = ibox.collidepoint(pos)


def finish_and_exit():
    global RUNNING
    RUNNING = False
    pygame.quit()

    with hits_lock:
        unique_hit_players = len([ip for ip, h in hits_by_us.items() if h > 0])
        total_hits = sum(hits_by_us.values())
        final = unique_hit_players - hits_received

    print("\n=== SCORE FINAL ===")
    print(f"Fui atingido: {hits_received}")
    print("Hits por jogador:")
    for ip, h in hits_by_us.items():
        print(f"  {ip}: {h}")
    print(f"Jogadores atingidos: {unique_hit_players}")
    print(f"Total hits: {total_hits}")
    print(f"Score final = {unique_hit_players} - {hits_received} = {final}")

    sys.exit(0)


# INICIAR THREADS

t_udp = threading.Thread(target=udp_listener_thread, daemon=True)
t_tcp = threading.Thread(target=tcp_listener_thread, daemon=True)
t_sender = threading.Thread(target=sender_thread, daemon=True)
t_udp.start()
t_tcp.start()
t_sender.start()

time.sleep(0.3)
broadcast_conectar()

clock = pygame.time.Clock()
input_ip = ""
typing_ip = False

# LOOP PRINCIPAL

while RUNNING:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            with participants_lock:
                for ip in participants:
                    send_udp(ip, "saindo")
            finish_and_exit()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                on_click_ui(event.pos)

        elif event.type == pygame.KEYDOWN:
            if input_active:
                if event.key == pygame.K_BACKSPACE:
                    input_ip = input_ip[:-1]
                else:
                    ch = event.unicode
                    if ch.isdigit() or ch in ".:" or ch.isalpha() or ch == "-":
                        input_ip += ch

            if event.key == pygame.K_p:
                broadcast_conectar()

            if event.key == pygame.K_ESCAPE:
                with participants_lock:
                    for ip in participants:
                        send_udp(ip, "saindo")
                finish_and_exit()

    draw()

    if selected_cell:
        rx = selected_cell[0] * CELL
        ry = selected_cell[1] * CELL
        rect = pygame.Rect(rx + 2, ry + 2, CELL - 4, CELL - 4)
        pygame.draw.rect(screen, (255, 255, 0), rect, 3)

    pygame.display.flip()
    clock.tick(FPS)

finish_and_exit()
