"""TURBO RUSH - corrida arcade 2D feita com Python + Pygame.

Rodar:  python3 turbo_rush.py
"""
import math
import random
import sys

import pygame

# ============================================================
# CONFIGURAÇÕES
# ============================================================
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
WORLD_SCALE = 1.8              # tamanho do mapa em relação à tela
WORLD_WIDTH = int(SCREEN_WIDTH * WORLD_SCALE)
WORLD_HEIGHT = int(SCREEN_HEIGHT * WORLD_SCALE)
CAMERA_SMOOTH = 8.0
TITLE = "TURBO RUSH"

# Carro
CAR_ACCELERATION = 320.0      # px/s^2
CAR_BRAKE = 600.0
CAR_FRICTION = 160.0          # desaceleração automática
CAR_MAX_SPEED = 440.0         # px/s
CAR_MAX_REVERSE = 130.0
CAR_TURN_RATE = 3.3           # rad/s em baixa velocidade
CAR_TURN_RATE_FAST = 1.9      # rad/s na velocidade máxima (vira menos, mais estável)
CAR_TURN_MIN_SPEED = 35.0     # a partir daqui o carro esterça por completo
STEER_SMOOTH = 7.0            # suavização do volante
CAR_LENGTH = 40
CAR_WIDTH = 22
CAR_RADIUS = 14               # raio usado nos obstáculos
OFFROAD_MAX_SPEED = 160.0
OFFROAD_DRAG = 380.0
WALL_BOUNCE = 0.35            # fração da velocidade mantida ao bater na borda

# Nitro
NITRO_MAX = 100.0
NITRO_DRAIN = 38.0            # por segundo
NITRO_RECHARGE = 9.0          # por segundo
NITRO_MAX_SPEED = 600.0
NITRO_ACCELERATION = 650.0
NITRO_MIN_TO_START = 8.0

# Corrida
TOTAL_LAPS = 3
COUNTDOWN_STEP = 0.9          # segundos por número
GO_DURATION = 0.7
SPEED_DISPLAY_FACTOR = 0.5    # px/s -> "km/h"

# Pista
ROAD_WIDTH = 150
CURB_WIDTH = 10
GRASS_MARGIN = 60             # faixa de grama além da estrada, antes do muro
BARRIER_WIDTH = 10
TRACK_POINTS = [              # pontos de controle (curva fechada)
    (640, 630), (1000, 610), (1160, 480), (1080, 330), (900, 262),
    (985, 135), (760, 90), (560, 170), (420, 100), (200, 130),
    (110, 300), (260, 400), (160, 520), (300, 630),
]
TRACK_POINTS = [(x * WORLD_SCALE, y * WORLD_SCALE) for x, y in TRACK_POINTS]
SPLINE_STEPS = 30
START_BACK = 14               # carro começa N pontos antes da linha
SEARCH_WINDOW = 40            # janela de busca do progresso na pista
OBSTACLES = [                 # (índice na pista, deslocamento lateral, tipo)
    (40, 25, "cone"), (62, -28, "tire"), (110, 0, "barrier"),
    (150, -30, "cone"), (160, 28, "cone"), (205, 20, "tire"),
    (250, -20, "barrier"), (300, 28, "cone"), (330, -25, "tire"),
    (370, 15, "barrier"),
]
OBSTACLE_RADIUS = 13
OBSTACLE_SLOWDOWN = 0.45
OBSTACLE_COOLDOWN = 0.4

# Cores
GRASS = (46, 150, 70)
GRASS_DARK = (36, 126, 58)
OUTSIDE = (28, 100, 50)
ROAD = (62, 64, 74)
ROAD_LINE = (235, 235, 235)
CURB_A = (225, 50, 50)
CURB_B = (245, 245, 245)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
YELLOW = (255, 214, 52)
ORANGE = (255, 140, 30)
RED = (230, 50, 50)
HUD_BG = (0, 0, 0, 150)

# Zonas (canal vermelho da superfície de zonas)
ZONE_WALL, ZONE_GRASS, ZONE_ROAD = 0, 1, 2

# Estados
MENU, CONTROLS, COUNTDOWN, RACE, PAUSED, FINISHED = range(6)


# ============================================================
# UTILIDADES
# ============================================================
def catmull_rom(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return tuple(
        0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2
               + (-a + 3 * b - 3 * c + d) * t3)
        for a, b, c, d in zip(p0, p1, p2, p3)
    )


def format_time(seconds):
    seconds = max(0.0, seconds)
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def draw_text(surface, font, text, pos, color=WHITE, center=False, shadow=True):
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    if shadow:
        surface.blit(font.render(text, True, BLACK), rect.move(3, 3))
    surface.blit(img, rect)
    return rect


class Controls:
    """Estado dos controles (separado do teclado para facilitar testes)."""

    def __init__(self):
        self.throttle = self.brake = self.left = self.right = self.nitro = False

    @classmethod
    def from_keyboard(cls):
        keys = pygame.key.get_pressed()
        c = cls()
        c.throttle = keys[pygame.K_w] or keys[pygame.K_UP]
        c.brake = keys[pygame.K_s] or keys[pygame.K_DOWN]
        c.left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        c.right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        c.nitro = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        return c


# ============================================================
# PARTÍCULAS
# ============================================================
class Particle:
    def __init__(self, pos, vel, color, life, size, shrink=True):
        self.x, self.y = pos
        self.vx, self.vy = vel
        self.color = color
        self.life = self.max_life = life
        self.size = size
        self.shrink = shrink

    @property
    def alive(self):
        return self.life > 0

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.96
        self.vy *= 0.96

    def draw(self, surface, cam):
        frac = max(0.0, self.life / self.max_life)
        radius = max(1, int(self.size * (frac if self.shrink else 1)))
        pygame.draw.circle(surface, self.color, (int(self.x - cam[0]), int(self.y - cam[1])), radius)


def spawn_burst(particles, pos, colors, count, speed, life, size):
    for _ in range(count):
        a = random.uniform(0, math.tau)
        s = random.uniform(0.3, 1.0) * speed
        particles.append(Particle(pos, (math.cos(a) * s, math.sin(a) * s),
                                  random.choice(colors), random.uniform(0.6, 1) * life,
                                  random.uniform(0.6, 1) * size))


# ============================================================
# PISTA
# ============================================================
class Track:
    """Pista fechada. Guarda a linha central, a imagem pronta e o mapa de zonas."""

    def __init__(self):
        pts = TRACK_POINTS
        n = len(pts)
        self.center = []
        for i in range(n):
            p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
            for s in range(SPLINE_STEPS):
                self.center.append(catmull_rom(p0, p1, p2, p3, s / SPLINE_STEPS))
        self.count = len(self.center)
        self.tangents = []
        for i, (x, y) in enumerate(self.center):
            nx, ny = self.center[(i + 1) % self.count]
            ang = math.atan2(ny - y, nx - x)
            self.tangents.append(ang)

        self.zones = self._build_zones()
        self.obstacles = [self._make_obstacle(*o) for o in OBSTACLES]
        random.seed(7)  # decoração sempre igual
        self.image = self._build_image()
        random.seed()

    # --- construção ---
    def _build_zones(self):
        zones = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))
        zones.fill((ZONE_WALL, 0, 0))
        r_grass = ROAD_WIDTH // 2 + CURB_WIDTH + GRASS_MARGIN
        for x, y in self.center:
            pygame.draw.circle(zones, (ZONE_GRASS, 0, 0), (x, y), r_grass)
        for x, y in self.center:
            pygame.draw.circle(zones, (ZONE_ROAD, 0, 0), (x, y), ROAD_WIDTH // 2 + CURB_WIDTH // 2)
        return zones

    def _make_obstacle(self, idx, offset, kind):
        x, y = self.center[idx]
        ang = self.tangents[idx] + math.pi / 2
        offset *= ROAD_WIDTH / 96  # proporcional à largura da estrada
        return {"pos": (x + math.cos(ang) * offset, y + math.sin(ang) * offset),
                "kind": kind, "angle": self.tangents[idx]}

    def _dist_to_track(self, x, y):
        return min(math.hypot(x - cx, y - cy) for cx, cy in self.center[::4])

    def _build_image(self):
        img = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))
        img.fill(OUTSIDE)
        # decoração de fundo (listras suaves)
        for y in range(0, WORLD_HEIGHT, 48):
            pygame.draw.rect(img, (32, 108, 54), (0, y, WORLD_WIDTH, 24))

        r_road = ROAD_WIDTH // 2
        r_curb = r_road + CURB_WIDTH
        r_grass = r_curb + GRASS_MARGIN
        # muro de pneus/barreira (borda externa da grama)
        for x, y in self.center:
            pygame.draw.circle(img, (210, 210, 210), (x, y), r_grass + BARRIER_WIDTH)
        for x, y in self.center:
            pygame.draw.circle(img, GRASS, (x, y), r_grass)
        # listras de grama
        stripe = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT), pygame.SRCALPHA)
        for i in range(0, self.count, 6):
            x, y = self.center[i]
            pygame.draw.circle(stripe, (*GRASS_DARK, 120), (x, y), r_grass)
        img.blit(stripe, (0, 0))
        # zebras (curb) alternadas
        for i, (x, y) in enumerate(self.center):
            col = CURB_A if (i // 3) % 2 == 0 else CURB_B
            pygame.draw.circle(img, col, (x, y), r_curb)
        # marcas vermelhas/brancas só valem nas bordas: pinta a estrada por cima
        for x, y in self.center:
            pygame.draw.circle(img, ROAD, (x, y), r_road)
        # linha central tracejada
        for i in range(0, self.count, 8):
            a, b = self.center[i], self.center[(i + 3) % self.count]
            pygame.draw.line(img, ROAD_LINE, a, b, 3)
        # linha de largada/chegada (xadrez)
        self._draw_finish_line(img)
        # árvores, prédios e placas fora da pista
        self._decorate(img)
        # sombra das bordas externas
        return img.convert()

    def _draw_finish_line(self, img):
        x, y = self.center[0]
        ang = self.tangents[0]
        tx, ty = math.cos(ang), math.sin(ang)
        nx, ny = -ty, tx
        cell = 14
        cols = ROAD_WIDTH // cell
        for c in range(cols):
            for r in range(2):
                off = (c - cols / 2) * cell
                px = x + nx * off + tx * (r - 1) * cell
                py = y + ny * off + ty * (r - 1) * cell
                pts = [(px, py), (px + nx * cell, py + ny * cell),
                       (px + nx * cell + tx * cell, py + ny * cell + ty * cell),
                       (px + tx * cell, py + ty * cell)]
                pygame.draw.polygon(img, WHITE if (c + r) % 2 == 0 else BLACK, pts)

    def _decorate(self, img):
        min_dist = ROAD_WIDTH // 2 + CURB_WIDTH + GRASS_MARGIN + BARRIER_WIDTH + 24
        placed = 0
        tries = 0
        while placed < 220 and tries < 8000:
            tries += 1
            x, y = random.randint(10, WORLD_WIDTH - 10), random.randint(10, WORLD_HEIGHT - 10)
            if self._dist_to_track(x, y) < min_dist:
                continue
            kind = random.random()
            if kind < 0.7:  # árvore
                pygame.draw.circle(img, (20, 80, 40), (x + 4, y + 5), 20)
                pygame.draw.rect(img, (110, 70, 40), (x - 3, y, 6, 14))
                pygame.draw.circle(img, (34, 139, 64), (x, y - 4), 18)
                pygame.draw.circle(img, (60, 170, 80), (x - 5, y - 9), 8)
            elif kind < 0.88:  # prédio
                w, h = random.randint(36, 60), random.randint(30, 50)
                col = random.choice([(180, 90, 90), (90, 120, 190), (200, 170, 80), (130, 90, 170)])
                pygame.draw.rect(img, (20, 60, 35), (x - w // 2 + 5, y - h // 2 + 5, w, h))
                pygame.draw.rect(img, col, (x - w // 2, y - h // 2, w, h))
                for wx in range(x - w // 2 + 6, x + w // 2 - 6, 12):
                    for wy in range(y - h // 2 + 6, y + h // 2 - 6, 12):
                        pygame.draw.rect(img, (250, 240, 170), (wx, wy, 6, 6))
            else:  # placa
                pygame.draw.rect(img, (90, 90, 90), (x - 2, y, 4, 16))
                pygame.draw.rect(img, YELLOW, (x - 18, y - 12, 36, 16))
                pygame.draw.rect(img, BLACK, (x - 18, y - 12, 36, 16), 2)
                pygame.draw.line(img, BLACK, (x - 10, y - 4), (x + 10, y - 4), 2)
            placed += 1

    # --- consulta ---
    def zone_at(self, x, y):
        ix, iy = int(x), int(y)
        if ix < 0 or iy < 0 or ix >= WORLD_WIDTH or iy >= WORLD_HEIGHT:
            return ZONE_WALL
        return self.zones.get_at((ix, iy))[0]

    def nearest_index(self, x, y, around):
        best, best_d = around, 1e18
        for k in range(-SEARCH_WINDOW, SEARCH_WINDOW + 1):
            i = (around + k) % self.count
            cx, cy = self.center[i]
            d = (cx - x) ** 2 + (cy - y) ** 2
            if d < best_d:
                best, best_d = i, d
        return best

    def draw(self, surface, cam):
        surface.blit(self.image, (-int(cam[0]), -int(cam[1])))
        for o in self.obstacles:
            self._draw_obstacle(surface, o, cam)

    def _draw_obstacle(self, surface, o, cam):
        x, y = int(o["pos"][0] - cam[0]), int(o["pos"][1] - cam[1])
        pygame.draw.ellipse(surface, (20, 20, 20), (x - 12, y - 4, 28, 20))
        if o["kind"] == "cone":
            pygame.draw.polygon(surface, ORANGE, [(x, y - 14), (x - 10, y + 8), (x + 10, y + 8)])
            pygame.draw.polygon(surface, WHITE, [(x, y - 5), (x - 5, y + 2), (x + 5, y + 2)])
            pygame.draw.rect(surface, (200, 100, 20), (x - 12, y + 7, 24, 4))
        elif o["kind"] == "tire":
            pygame.draw.circle(surface, (25, 25, 25), (x, y), OBSTACLE_RADIUS)
            pygame.draw.circle(surface, (90, 90, 90), (x, y), OBSTACLE_RADIUS - 4, 2)
            pygame.draw.circle(surface, (60, 60, 60), (x, y), 4)
        else:  # barreira listrada, perpendicular à pista
            surf = pygame.Surface((14, 34), pygame.SRCALPHA)
            for i in range(0, 34, 8):
                pygame.draw.rect(surf, RED if (i // 8) % 2 == 0 else WHITE, (0, i, 14, 8))
            pygame.draw.rect(surf, BLACK, surf.get_rect(), 1)
            rot = pygame.transform.rotate(surf, -math.degrees(o["angle"]))
            surface.blit(rot, rot.get_rect(center=(x, y)))


# ============================================================
# CARRO
# ============================================================
class Car:
    def __init__(self, pos, angle):
        self.start_pos, self.start_angle = pos, angle
        self.sprite = self._make_sprite()
        self.reset()

    def reset(self):
        self.x, self.y = self.start_pos
        self.angle = self.start_angle
        self.speed = 0.0
        self.steer = 0.0
        self.nitro = NITRO_MAX
        self.nitro_on = False
        self.offroad = False
        self.braking = False
        self.hit_cooldown = 0.0

    @staticmethod
    def _make_sprite():
        s = pygame.Surface((CAR_LENGTH + 6, CAR_WIDTH + 6), pygame.SRCALPHA)
        ox, oy = 3, 3
        pygame.draw.rect(s, (15, 15, 15), (ox + 4, oy - 2, 10, 4), border_radius=2)   # rodas
        pygame.draw.rect(s, (15, 15, 15), (ox + 4, oy + CAR_WIDTH - 2, 10, 4), border_radius=2)
        pygame.draw.rect(s, (15, 15, 15), (ox + CAR_LENGTH - 14, oy - 2, 10, 4), border_radius=2)
        pygame.draw.rect(s, (15, 15, 15), (ox + CAR_LENGTH - 14, oy + CAR_WIDTH - 2, 10, 4), border_radius=2)
        pygame.draw.rect(s, (230, 40, 50), (ox, oy, CAR_LENGTH, CAR_WIDTH), border_radius=8)
        pygame.draw.rect(s, (255, 255, 255), (ox + 6, oy + CAR_WIDTH // 2 - 2, CAR_LENGTH - 14, 4))  # faixa
        pygame.draw.rect(s, (60, 170, 230), (ox + 17, oy + 3, 9, CAR_WIDTH - 6), border_radius=3)    # vidro
        pygame.draw.rect(s, YELLOW, (ox + CAR_LENGTH - 4, oy + 2, 3, 5))                              # faróis
        pygame.draw.rect(s, YELLOW, (ox + CAR_LENGTH - 4, oy + CAR_WIDTH - 7, 3, 5))
        pygame.draw.rect(s, (120, 10, 20), (ox, oy + 2, 3, 5))                                        # lanternas
        pygame.draw.rect(s, (120, 10, 20), (ox, oy + CAR_WIDTH - 7, 3, 5))
        return s

    @property
    def direction(self):
        return math.cos(self.angle), math.sin(self.angle)

    def back_position(self):
        dx, dy = self.direction
        return self.x - dx * CAR_LENGTH / 2, self.y - dy * CAR_LENGTH / 2

    def update(self, dt, controls, track, particles):
        self.hit_cooldown = max(0.0, self.hit_cooldown - dt)
        self.braking = False

        # nitro
        want_nitro = controls.nitro and not controls.brake
        if self.nitro_on and (not want_nitro or self.nitro <= 0):
            self.nitro_on = False
        elif not self.nitro_on and want_nitro and self.nitro >= NITRO_MIN_TO_START:
            self.nitro_on = True
        if self.nitro_on:
            self.nitro = max(0.0, self.nitro - NITRO_DRAIN * dt)
        else:
            self.nitro = min(NITRO_MAX, self.nitro + NITRO_RECHARGE * dt)

        # velocidade
        max_speed = NITRO_MAX_SPEED if self.nitro_on else CAR_MAX_SPEED
        if self.offroad:
            max_speed = OFFROAD_MAX_SPEED
        if self.nitro_on:
            self.speed += NITRO_ACCELERATION * dt
        elif controls.throttle:
            self.speed += CAR_ACCELERATION * dt
        elif controls.brake:
            if self.speed > 0:
                self.speed -= CAR_BRAKE * dt
                self.braking = self.speed > 60
            else:
                self.speed -= CAR_ACCELERATION * 0.6 * dt
        else:  # desaceleração automática
            drop = CAR_FRICTION * dt
            self.speed = max(0.0, self.speed - drop) if self.speed > 0 else min(0.0, self.speed + drop)
        if controls.throttle and controls.brake and self.speed > 0:
            self.braking = True
        if self.offroad and self.speed > max_speed:
            self.speed = max(max_speed, self.speed - OFFROAD_DRAG * dt)
        self.speed = max(-CAR_MAX_REVERSE, min(max_speed, self.speed))

        # direção
        # volante suave: segue a tecla aos poucos e volta ao centro ao soltar
        target = (1 if controls.right else 0) - (1 if controls.left else 0)
        self.steer += (target - self.steer) * min(1.0, STEER_SMOOTH * dt)
        grip = min(1.0, abs(self.speed) / CAR_TURN_MIN_SPEED)
        fast = min(1.0, abs(self.speed) / CAR_MAX_SPEED)  # em alta velocidade vira menos
        rate = CAR_TURN_RATE + (CAR_TURN_RATE_FAST - CAR_TURN_RATE) * fast
        self.angle += self.steer * rate * grip * dt * (1 if self.speed >= 0 else -1)

        # movimento com colisão nas bordas (eixos separados para deslizar)
        dx, dy = self.direction
        nx, ny = self.x + dx * self.speed * dt, self.y + dy * self.speed * dt
        hit_wall = False
        if track.zone_at(nx, ny) == ZONE_WALL:
            hit_wall = True
            if track.zone_at(nx, self.y) != ZONE_WALL:
                ny = self.y
            elif track.zone_at(self.x, ny) != ZONE_WALL:
                nx = self.x
            else:
                nx, ny = self.x, self.y
        if hit_wall:
            if abs(self.speed) > 80:
                self._impact(particles, (self.x + dx * 18, self.y + dy * 18), (230, 230, 230))
            self.speed *= -WALL_BOUNCE if self.speed > 150 else WALL_BOUNCE
        self.x, self.y = nx, ny
        self.offroad = track.zone_at(self.x, self.y) == ZONE_GRASS

        # obstáculos
        for o in track.obstacles:
            ox, oy = o["pos"]
            dist = math.hypot(self.x - ox, self.y - oy)
            if dist < CAR_RADIUS + OBSTACLE_RADIUS:
                if self.hit_cooldown <= 0:
                    self.speed *= OBSTACLE_SLOWDOWN
                    self.hit_cooldown = OBSTACLE_COOLDOWN
                    self._impact(particles, (ox, oy), (ORANGE, YELLOW, WHITE))
                if dist > 0.1:  # empurra o carro para fora do obstáculo
                    push = CAR_RADIUS + OBSTACLE_RADIUS - dist
                    px, py = self.x + (self.x - ox) / dist * push, self.y + (self.y - oy) / dist * push
                    if track.zone_at(px, py) != ZONE_WALL:
                        self.x, self.y = px, py

        self._emit_particles(dt, particles)

    def _impact(self, particles, pos, colors):
        if not isinstance(colors[0], tuple):
            colors = [colors]
        spawn_burst(particles, pos, list(colors), 12, 220, 0.45, 4)

    def _emit_particles(self, dt, particles):
        bx, by = self.back_position()
        dx, dy = self.direction
        if self.braking:  # fumaça ao frear
            for side in (-1, 1):
                px, py = bx - dy * side * 8, by + dx * side * 8
                particles.append(Particle((px, py), (random.uniform(-25, 25), random.uniform(-25, 25)),
                                          (200, 200, 200), 0.6, 8))
        if self.offroad and abs(self.speed) > 60 and random.random() < 0.5:  # poeira
            particles.append(Particle((bx, by), (random.uniform(-30, 30), random.uniform(-30, 30)),
                                      (140, 190, 110), 0.4, 5))
        if self.nitro_on:  # chamas
            for _ in range(2):
                col = random.choice([ORANGE, YELLOW, (255, 90, 30), (120, 200, 255)])
                spread = random.uniform(-0.25, 0.25)
                vx = -dx * 260 + (-dy) * spread * 120
                vy = -dy * 260 + dx * spread * 120
                particles.append(Particle((bx, by), (vx, vy), col, 0.25, 7))

    def draw(self, surface, cam):
        cx, cy = self.x - cam[0], self.y - cam[1]
        rot = pygame.transform.rotate(self.sprite, -math.degrees(self.angle))
        shadow = pygame.transform.rotate(self.sprite, -math.degrees(self.angle))
        shadow.fill((0, 0, 0, 90), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(shadow, shadow.get_rect(center=(cx + 4, cy + 5)))
        surface.blit(rot, rot.get_rect(center=(cx, cy)))


# ============================================================
# JOGO
# ============================================================
class Game:
    MENU_ITEMS = ["JOGAR", "CONTROLES", "SAIR"]

    def __init__(self, screen=None):
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = screen or pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.Font(None, 140)
        self.font_title = pygame.font.Font(None, 72)
        self.font_mid = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 34)
        self.hud_panel = pygame.Surface((300, 150), pygame.SRCALPHA)
        self.hud_panel.fill(HUD_BG)

        self.track = Track()
        start_angle = self.track.tangents[-START_BACK]
        sx, sy = self.track.center[-START_BACK]
        self.car = Car((sx, sy), start_angle)
        self.particles = []
        self.state = MENU
        self.menu_index = 0
        self.running = True
        self.ticks = 0.0
        self.cam = [0.0, 0.0]
        self.reset_race()

    # --- controle de estado ---
    def reset_race(self):
        self.car.reset()
        self.particles = []
        self.idx = self.track.count - START_BACK
        self.checkpoint = False
        self.laps_done = 0
        self.race_time = 0.0
        self.lap_start = 0.0
        self.last_lap_time = 0.0
        self.banner_timer = 0.0
        self.flash = 0.0
        self.count_timer = 0.0

    def start_race(self):
        self.reset_race()
        self.state = COUNTDOWN
        self.follow_camera(self.car.x, self.car.y, None)

    def follow_camera(self, x, y, dt):
        tx = max(0, min(WORLD_WIDTH - SCREEN_WIDTH, x - SCREEN_WIDTH / 2))
        ty = max(0, min(WORLD_HEIGHT - SCREEN_HEIGHT, y - SCREEN_HEIGHT / 2))
        k = 1.0 if dt is None else min(1.0, CAMERA_SMOOTH * dt)
        self.cam[0] += (tx - self.cam[0]) * k
        self.cam[1] += (ty - self.cam[1]) * k

    @property
    def current_lap(self):
        return min(self.laps_done + 1, TOTAL_LAPS)

    @property
    def countdown_label(self):
        step = int(self.count_timer // COUNTDOWN_STEP)
        return str(3 - step) if step < 3 else "GO!"

    # --- eventos ---
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if self.state == MENU:
            if key in (pygame.K_w, pygame.K_UP):
                self.menu_index = (self.menu_index - 1) % len(self.MENU_ITEMS)
            elif key in (pygame.K_s, pygame.K_DOWN):
                self.menu_index = (self.menu_index + 1) % len(self.MENU_ITEMS)
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                choice = self.MENU_ITEMS[self.menu_index]
                if choice == "JOGAR":
                    self.start_race()
                elif choice == "CONTROLES":
                    self.state = CONTROLS
                else:
                    self.running = False
        elif self.state == CONTROLS:
            if key == pygame.K_ESCAPE:
                self.state = MENU
        elif self.state in (COUNTDOWN, RACE):
            if key == pygame.K_ESCAPE:
                self.paused_from = self.state
                self.state = PAUSED
        elif self.state == PAUSED:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.state = self.paused_from
            elif key == pygame.K_r:
                self.start_race()
            elif key == pygame.K_ESCAPE:
                self.state = MENU
        elif self.state == FINISHED:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.start_race()
            elif key == pygame.K_ESCAPE:
                self.state = MENU

    # --- atualização ---
    def update(self, dt, controls=None):
        self.ticks += dt
        controls = controls or Controls.from_keyboard()
        if self.state in (MENU, CONTROLS):  # menu: câmera passeia pela pista
            px, py = self.track.center[int(self.ticks * 8) % self.track.count]
            self.follow_camera(px, py, dt)
        else:
            self.follow_camera(self.car.x, self.car.y, dt)
        if self.state == COUNTDOWN:
            self.count_timer += dt
            if self.count_timer >= COUNTDOWN_STEP * 3:  # "GO!" libera o carro
                self.state = RACE
                self.go_timer = GO_DURATION
        elif self.state == RACE:
            self.go_timer = max(0.0, getattr(self, "go_timer", 0.0) - dt)
            self.race_time += dt
            self.car.update(dt, controls, self.track, self.particles)
            self.update_laps()
        elif self.state == FINISHED:
            # o carro desliza até parar
            self.car.update(dt, Controls(), self.track, self.particles)
        self.banner_timer = max(0.0, self.banner_timer - dt)
        self.flash = max(0.0, self.flash - dt)
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive]

    def update_laps(self):
        prev = self.idx
        self.idx = self.track.nearest_index(self.car.x, self.car.y, prev)
        n = self.track.count
        if self.idx >= n // 2 and prev < n // 2 + SEARCH_WINDOW:
            self.checkpoint = True  # passou pelo lado oposto da pista
        if prev > n * 0.85 and self.idx < n * 0.15 and self.checkpoint:
            self.checkpoint = False
            self.laps_done += 1
            self.last_lap_time = self.race_time - self.lap_start
            self.lap_start = self.race_time
            self.finish_line_effect()
            if self.laps_done >= TOTAL_LAPS:
                self.state = FINISHED
        elif prev < n * 0.15 and self.idx > n * 0.85:
            self.checkpoint = self.checkpoint and False  # voltou pra trás da linha

    def finish_line_effect(self):
        self.banner_timer = 2.0
        self.flash = 0.35
        fx, fy = self.track.center[0]
        spawn_burst(self.particles, (fx, fy), [YELLOW, WHITE, RED, (80, 200, 255), ORANGE],
                    50, 320, 1.0, 5)

    # --- desenho ---
    def draw(self):
        s = self.screen
        if self.state in (MENU, CONTROLS):
            self.draw_menu()
            return
        self.track.draw(s, self.cam)
        for p in self.particles:
            p.draw(s, self.cam)
        self.car.draw(s, self.cam)
        self.draw_hud()
        if self.flash > 0:
            fl = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            fl.fill((255, 255, 255, int(160 * self.flash / 0.35)))
            s.blit(fl, (0, 0))
        if self.banner_timer > 0 and self.state != FINISHED:
            draw_text(s, self.font_title, f"VOLTA {self.laps_done} COMPLETA!  {format_time(self.last_lap_time)}",
                      (SCREEN_WIDTH // 2, 110), YELLOW, center=True)
        if self.state == COUNTDOWN:
            self.draw_overlay(80)
            label = self.countdown_label
            color = YELLOW if label != "GO!" else (80, 255, 120)
            draw_text(s, self.font_big, label, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2), color, center=True)
        elif self.state == RACE and self.go_timer > 0:
            draw_text(s, self.font_big, "GO!", (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2),
                      (80, 255, 120), center=True)
        elif self.state == PAUSED:
            self.draw_overlay(170)
            cx = SCREEN_WIDTH // 2
            draw_text(s, self.font_big, "PAUSADO", (cx, 230), WHITE, center=True)
            for i, line in enumerate(["ENTER = continuar", "R = reiniciar", "ESC = menu"]):
                draw_text(s, self.font_mid, line, (cx, 340 + i * 55), YELLOW, center=True)
        elif self.state == FINISHED:
            self.draw_overlay(170)
            cx = SCREEN_WIDTH // 2
            draw_text(s, self.font_title, "CORRIDA FINALIZADA!", (cx, 220), YELLOW, center=True)
            draw_text(s, self.font_big, f"TEMPO: {format_time(self.race_time)}", (cx, 330), WHITE, center=True)
            draw_text(s, self.font_mid, "Pressione ENTER para jogar novamente.", (cx, 450), WHITE, center=True)
            draw_text(s, self.font_mid, "Pressione ESC para voltar ao menu.", (cx, 500), WHITE, center=True)

    def draw_overlay(self, alpha):
        ov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, alpha))
        self.screen.blit(ov, (0, 0))

    def draw_hud(self):
        s = self.screen
        s.blit(self.hud_panel, (16, 16))
        draw_text(s, self.font_mid, f"VOLTA {self.current_lap}/{TOTAL_LAPS}", (30, 24), YELLOW)
        draw_text(s, self.font_small, f"TEMPO {format_time(self.race_time)}", (30, 64))
        speed = int(abs(self.car.speed) * SPEED_DISPLAY_FACTOR)
        draw_text(s, self.font_small, f"VELOCIDADE {speed}", (30, 92))
        draw_text(s, self.font_small, "NITRO", (30, 124))
        bar = pygame.Rect(110, 128, 180, 16)
        pygame.draw.rect(s, (40, 40, 40), bar)
        fill = bar.copy()
        fill.width = int(bar.width * self.car.nitro / NITRO_MAX)
        pygame.draw.rect(s, (255, 120, 30) if self.car.nitro_on else (60, 200, 255), fill)
        pygame.draw.rect(s, WHITE, bar, 2)

    def draw_menu(self):
        s = self.screen
        self.track.draw(s, self.cam)
        self.draw_overlay(150)
        cx = SCREEN_WIDTH // 2
        bob = math.sin(self.ticks * 3) * 6
        draw_text(s, self.font_big, "TURBO RUSH", (cx, 170 + bob), YELLOW, center=True)
        if self.state == MENU:
            for i, item in enumerate(self.MENU_ITEMS):
                sel = i == self.menu_index
                label = f"> {item} <" if sel else item
                draw_text(s, self.font_title, label, (cx, 320 + i * 80),
                          YELLOW if sel else WHITE, center=True)
            draw_text(s, self.font_small, "W/S = escolher   ENTER = confirmar",
                      (cx, SCREEN_HEIGHT - 50), (200, 200, 200), center=True)
        else:
            draw_text(s, self.font_title, "CONTROLES", (cx, 300), WHITE, center=True)
            for i, line in enumerate(["WASD = dirigir", "SHIFT = nitro", "ESC = pausa"]):
                draw_text(s, self.font_mid, line, (cx, 380 + i * 55), YELLOW, center=True)
            draw_text(s, self.font_small, "Pressione ESC para voltar", (cx, SCREEN_HEIGHT - 50),
                      (200, 200, 200), center=True)

    # --- loop principal ---
    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30)  # limita dt para estabilidade
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
