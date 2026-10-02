"""TURBO RUSH - corrida arcade 2D (Pygame). Rodar: python3 turbo_rush.py"""
import math
import random
import sys

import pygame

# ---------- configurações ----------
SCREEN_WIDTH, SCREEN_HEIGHT, FPS = 1280, 720, 60
WORLD_SCALE = 1.8                                   # mapa maior que a tela, câmera segue o carro
WORLD_WIDTH, WORLD_HEIGHT = int(SCREEN_WIDTH * WORLD_SCALE), int(SCREEN_HEIGHT * WORLD_SCALE)
CAMERA_SMOOTH = 8.0
CAR_ACCELERATION, CAR_BRAKE, CAR_FRICTION = 320.0, 600.0, 160.0
CAR_MAX_SPEED, CAR_MAX_REVERSE = 440.0, 130.0
CAR_TURN_RATE, CAR_TURN_RATE_FAST, CAR_TURN_MIN_SPEED, STEER_SMOOTH = 3.3, 1.9, 35.0, 7.0
CAR_LENGTH, CAR_WIDTH, CAR_RADIUS = 40, 22, 14
OFFROAD_MAX_SPEED, OFFROAD_DRAG, WALL_BOUNCE = 160.0, 380.0, 0.35
NITRO_MAX, NITRO_DRAIN, NITRO_RECHARGE = 100.0, 38.0, 9.0
NITRO_MAX_SPEED, NITRO_ACCELERATION, NITRO_MIN_TO_START = 600.0, 650.0, 8.0
TOTAL_LAPS, COUNTDOWN_STEP, GO_DURATION = 3, 0.9, 0.7
ROAD_WIDTH, CURB_WIDTH, GRASS_MARGIN, BARRIER_WIDTH = 150, 10, 60, 10
RADIUS_GRASS = ROAD_WIDTH // 2 + CURB_WIDTH + GRASS_MARGIN
TRACK_POINTS = [(x * WORLD_SCALE, y * WORLD_SCALE) for x, y in [
    (640, 630), (1000, 610), (1160, 480), (1080, 330), (900, 262), (985, 135), (760, 90),
    (560, 170), (420, 100), (200, 130), (110, 300), (260, 400), (160, 520), (300, 630)]]
START_BACK, SEARCH_WINDOW = 14, 40
OBSTACLES = [(40, 25, "cone"), (62, -28, "tire"), (110, 0, "barrier"), (150, -30, "cone"), (160, 28, "cone"),
             (205, 20, "tire"), (250, -20, "barrier"), (300, 28, "cone"), (330, -25, "tire"), (370, 15, "barrier")]
OBSTACLE_RADIUS = 13
ZONE_WALL, ZONE_GRASS, ZONE_ROAD = 0, 1, 2
MENU, CONTROLS, COUNTDOWN, RACE, PAUSED, FINISHED = range(6)
WHITE, BLACK, YELLOW, ORANGE, RED = (255, 255, 255), (0, 0, 0), (255, 214, 52), (255, 140, 30), (230, 50, 50)


def format_time(s):
    s = max(0.0, s)
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def draw_text(surface, font, s, pos, color=WHITE, center=False):
    img = font.render(s, True, color)
    rect = img.get_rect(**{"center" if center else "topleft": pos})
    surface.blit(font.render(s, True, BLACK), rect.move(3, 3))
    surface.blit(img, rect)


class Controls:
    """Estado dos controles (separado do teclado para facilitar testes)."""

    def __init__(self, throttle=False, brake=False, left=False, right=False, nitro=False):
        self.throttle, self.brake, self.left, self.right, self.nitro = throttle, brake, left, right, nitro

    @classmethod
    def from_keyboard(cls):
        k = pygame.key.get_pressed()
        return cls(k[pygame.K_w] or k[pygame.K_UP], k[pygame.K_s] or k[pygame.K_DOWN], k[pygame.K_a] or k[pygame.K_LEFT],
                   k[pygame.K_d] or k[pygame.K_RIGHT], k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT])


# ---------- partículas ----------
class Particle:
    def __init__(self, pos, vel, color, life, size):
        self.x, self.y = pos
        self.vx, self.vy = vel
        self.color, self.life, self.max_life, self.size = color, life, life, size

    def update(self, dt):
        self.life -= dt
        self.x, self.y = self.x + self.vx * dt, self.y + self.vy * dt
        self.vx, self.vy = self.vx * 0.96, self.vy * 0.96

    def draw(self, surface, cam):
        pygame.draw.circle(surface, self.color, (int(self.x - cam[0]), int(self.y - cam[1])),
                           max(1, int(self.size * max(0.0, self.life / self.max_life))))


def burst(particles, pos, colors, count, speed, life, size):
    for _ in range(count):
        a, s = random.uniform(0, math.tau), random.uniform(0.3, 1.0) * speed
        particles.append(Particle(pos, (math.cos(a) * s, math.sin(a) * s), random.choice(colors),
                                  random.uniform(0.6, 1) * life, random.uniform(0.6, 1) * size))


# ---------- pista ----------
class Track:
    """Pista fechada: linha central (spline), imagem pronta e mapa de zonas (muro/grama/estrada)."""

    def __init__(self):
        pts, n = TRACK_POINTS, len(TRACK_POINTS)
        self.center = []
        for i in range(n):
            for s in range(30):
                t = s / 30
                self.center.append(tuple(0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (3 * b - a - 3 * c + d) * t ** 3)
                                         for a, b, c, d in zip(pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n])))
        self.count = len(self.center)
        self.tangents = [math.atan2(self.center[(i + 1) % self.count][1] - y, self.center[(i + 1) % self.count][0] - x)
                         for i, (x, y) in enumerate(self.center)]
        self.zones = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))   # canal vermelho = zona
        self._circles(self.zones, (ZONE_GRASS, 0, 0), RADIUS_GRASS)
        self._circles(self.zones, (ZONE_ROAD, 0, 0), ROAD_WIDTH // 2 + CURB_WIDTH // 2)
        self.obstacles = []
        for idx, off, kind in OBSTACLES:
            a, off = self.tangents[idx] + math.pi / 2, off * ROAD_WIDTH / 96
            x, y = self.center[idx]
            self.obstacles.append({"pos": (x + math.cos(a) * off, y + math.sin(a) * off), "kind": kind, "angle": self.tangents[idx]})
        random.seed(7)
        self.image = self._build_image()
        random.seed()

    def _circles(self, surf, color, radius, alternate=None):
        for i, p in enumerate(self.center):
            pygame.draw.circle(surf, alternate[(i // 3) % 2] if alternate else color, p, radius)

    def _build_image(self):
        img = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))
        img.fill((28, 100, 50))
        for y in range(0, WORLD_HEIGHT, 48):
            pygame.draw.rect(img, (32, 108, 54), (0, y, WORLD_WIDTH, 24))
        r_road = ROAD_WIDTH // 2
        self._circles(img, (210, 210, 210), RADIUS_GRASS + BARRIER_WIDTH)
        self._circles(img, (46, 150, 70), RADIUS_GRASS)
        self._circles(img, None, r_road + CURB_WIDTH, alternate=[(225, 50, 50), (245, 245, 245)])
        self._circles(img, (62, 64, 74), r_road)
        for i in range(0, self.count, 8):
            pygame.draw.line(img, (235, 235, 235), self.center[i], self.center[(i + 3) % self.count], 3)
        (x, y), a, k = self.center[0], self.tangents[0], 14       # linha de largada xadrez
        tx, ty = math.cos(a), math.sin(a)
        for c in range(10):
            for r in range(2):
                px, py = x - ty * (c - 5) * k + tx * (r - 1) * k, y + tx * (c - 5) * k + ty * (r - 1) * k
                pygame.draw.polygon(img, WHITE if (c + r) % 2 == 0 else BLACK, [
                    (px, py), (px - ty * k, py + tx * k), (px - ty * k + tx * k, py + tx * k + ty * k), (px + tx * k, py + ty * k)])
        placed = 0
        for _ in range(8000):                                      # árvores e prédios fora da pista
            if placed >= 220:
                break
            x, y = random.randint(20, WORLD_WIDTH - 20), random.randint(20, WORLD_HEIGHT - 20)
            if any(math.hypot(x - cx, y - cy) < RADIUS_GRASS + BARRIER_WIDTH + 24 for cx, cy in self.center[::4]):
                continue
            if random.random() < 0.75:
                pygame.draw.circle(img, (20, 80, 40), (x + 4, y + 5), 20)
                pygame.draw.rect(img, (110, 70, 40), (x - 3, y, 6, 14))
                pygame.draw.circle(img, (34, 139, 64), (x, y - 4), 18)
                pygame.draw.circle(img, (60, 170, 80), (x - 5, y - 9), 8)
            else:
                w, h = random.randint(36, 60), random.randint(30, 50)
                pygame.draw.rect(img, (20, 60, 35), (x - w // 2 + 5, y - h // 2 + 5, w, h))
                pygame.draw.rect(img, random.choice([(180, 90, 90), (90, 120, 190), (200, 170, 80), (130, 90, 170)]), (x - w // 2, y - h // 2, w, h))
                for wx in range(x - w // 2 + 6, x + w // 2 - 6, 12):
                    for wy in range(y - h // 2 + 6, y + h // 2 - 6, 12):
                        pygame.draw.rect(img, (250, 240, 170), (wx, wy, 6, 6))
            placed += 1
        return img

    def zone_at(self, x, y):
        if not (0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT):
            return ZONE_WALL
        return self.zones.get_at((int(x), int(y)))[0]

    def nearest_index(self, x, y, around):
        return min(((around + k) % self.count for k in range(-SEARCH_WINDOW, SEARCH_WINDOW + 1)),
                   key=lambda i: (self.center[i][0] - x) ** 2 + (self.center[i][1] - y) ** 2)

    def draw(self, surface, cam):
        surface.blit(self.image, (-int(cam[0]), -int(cam[1])))
        for o in self.obstacles:
            x, y = int(o["pos"][0] - cam[0]), int(o["pos"][1] - cam[1])
            pygame.draw.ellipse(surface, (20, 20, 20), (x - 12, y - 4, 28, 20))
            if o["kind"] == "cone":
                pygame.draw.polygon(surface, ORANGE, [(x, y - 14), (x - 10, y + 8), (x + 10, y + 8)])
                pygame.draw.polygon(surface, WHITE, [(x, y - 5), (x - 5, y + 2), (x + 5, y + 2)])
            elif o["kind"] == "tire":
                pygame.draw.circle(surface, (25, 25, 25), (x, y), OBSTACLE_RADIUS)
                pygame.draw.circle(surface, (90, 90, 90), (x, y), OBSTACLE_RADIUS - 4, 2)
            else:  # barreira listrada
                bar = pygame.Surface((14, 34))
                for i in range(0, 34, 8):
                    pygame.draw.rect(bar, RED if (i // 8) % 2 == 0 else WHITE, (0, i, 14, 8))
                bar = pygame.transform.rotate(bar, -math.degrees(o["angle"]))
                surface.blit(bar, bar.get_rect(center=(x, y)))


# ---------- carro ----------
class Car:
    def __init__(self, pos, angle):
        self.start_pos, self.start_angle = pos, angle
        s = pygame.Surface((CAR_LENGTH + 6, CAR_WIDTH + 6), pygame.SRCALPHA)
        for wx in (7, CAR_LENGTH - 11):
            pygame.draw.rect(s, (15, 15, 15), (wx, 1, 10, 4), border_radius=2)
            pygame.draw.rect(s, (15, 15, 15), (wx, CAR_WIDTH + 1, 10, 4), border_radius=2)
        pygame.draw.rect(s, (230, 40, 50), (3, 3, CAR_LENGTH, CAR_WIDTH), border_radius=8)
        pygame.draw.rect(s, WHITE, (9, 3 + CAR_WIDTH // 2 - 2, CAR_LENGTH - 14, 4))
        pygame.draw.rect(s, (60, 170, 230), (20, 6, 9, CAR_WIDTH - 6), border_radius=3)
        pygame.draw.rect(s, YELLOW, (CAR_LENGTH - 1, 5, 3, 5))
        pygame.draw.rect(s, YELLOW, (CAR_LENGTH - 1, CAR_WIDTH - 4, 3, 5))
        self.sprite = s
        self.reset()

    def reset(self):
        self.x, self.y = self.start_pos
        self.angle, self.speed, self.steer, self.nitro = self.start_angle, 0.0, 0.0, NITRO_MAX
        self.nitro_on = self.offroad = self.braking = False
        self.hit_cooldown = 0.0

    def update(self, dt, c, track, particles):
        self.hit_cooldown, self.braking = max(0.0, self.hit_cooldown - dt), False
        want = c.nitro and not c.brake                                   # nitro
        if self.nitro_on and (not want or self.nitro <= 0):
            self.nitro_on = False
        elif not self.nitro_on and want and self.nitro >= NITRO_MIN_TO_START:
            self.nitro_on = True
        self.nitro = max(0.0, self.nitro - NITRO_DRAIN * dt) if self.nitro_on else min(NITRO_MAX, self.nitro + NITRO_RECHARGE * dt)
        top = OFFROAD_MAX_SPEED if self.offroad else NITRO_MAX_SPEED if self.nitro_on else CAR_MAX_SPEED
        if self.nitro_on:                                                # aceleração / freio / atrito
            self.speed += NITRO_ACCELERATION * dt
        elif c.throttle:
            self.speed += CAR_ACCELERATION * dt
        elif c.brake:
            self.braking = self.speed > 60
            self.speed -= (CAR_BRAKE if self.speed > 0 else CAR_ACCELERATION * 0.6) * dt
        else:
            self.speed = max(0.0, self.speed - CAR_FRICTION * dt) if self.speed > 0 else min(0.0, self.speed + CAR_FRICTION * dt)
        if self.offroad and self.speed > top:
            self.speed = max(top, self.speed - OFFROAD_DRAG * dt)
        self.speed = max(-CAR_MAX_REVERSE, min(top, self.speed))
        # volante suave; vira menos em alta velocidade
        self.steer += ((c.right - c.left) - self.steer) * min(1.0, STEER_SMOOTH * dt)
        rate = CAR_TURN_RATE + (CAR_TURN_RATE_FAST - CAR_TURN_RATE) * min(1.0, abs(self.speed) / CAR_MAX_SPEED)
        self.angle += self.steer * rate * min(1.0, abs(self.speed) / CAR_TURN_MIN_SPEED) * dt * (1 if self.speed >= 0 else -1)
        # movimento com colisão no muro (eixos separados para deslizar)
        dx, dy = math.cos(self.angle), math.sin(self.angle)
        nx, ny = self.x + dx * self.speed * dt, self.y + dy * self.speed * dt
        if track.zone_at(nx, ny) == ZONE_WALL:
            if track.zone_at(nx, self.y) != ZONE_WALL:
                ny = self.y
            elif track.zone_at(self.x, ny) != ZONE_WALL:
                nx = self.x
            else:
                nx, ny = self.x, self.y
            if abs(self.speed) > 80:
                burst(particles, (self.x + dx * 18, self.y + dy * 18), [(230, 230, 230)], 12, 220, 0.45, 4)
            self.speed *= -WALL_BOUNCE if self.speed > 150 else WALL_BOUNCE
        self.x, self.y = nx, ny
        self.offroad = track.zone_at(nx, ny) == ZONE_GRASS
        for o in track.obstacles:                                        # obstáculos
            ox, oy = o["pos"]
            dist = math.hypot(self.x - ox, self.y - oy)
            if dist < CAR_RADIUS + OBSTACLE_RADIUS:
                if self.hit_cooldown <= 0:
                    self.speed, self.hit_cooldown = self.speed * 0.45, 0.4
                    burst(particles, (ox, oy), [ORANGE, YELLOW, WHITE], 12, 220, 0.45, 4)
                push = (CAR_RADIUS + OBSTACLE_RADIUS - dist) / max(dist, 0.1)
                px, py = self.x + (self.x - ox) * push, self.y + (self.y - oy) * push
                if dist > 0.1 and track.zone_at(px, py) != ZONE_WALL:
                    self.x, self.y = px, py
        bx, by = self.x - dx * CAR_LENGTH / 2, self.y - dy * CAR_LENGTH / 2   # fumaça, poeira e chamas
        rnd = random.uniform
        if self.braking:
            for side in (-1, 1):
                particles.append(Particle((bx - dy * side * 8, by + dx * side * 8), (rnd(-25, 25), rnd(-25, 25)), (200, 200, 200), 0.6, 8))
        if self.offroad and abs(self.speed) > 60 and random.random() < 0.5:
            particles.append(Particle((bx, by), (rnd(-30, 30), rnd(-30, 30)), (140, 190, 110), 0.4, 5))
        if self.nitro_on:
            for _ in range(2):
                s = rnd(-0.25, 0.25)
                particles.append(Particle((bx, by), (-dx * 260 - dy * s * 120, -dy * 260 + dx * s * 120),
                                          random.choice([ORANGE, YELLOW, (255, 90, 30), (120, 200, 255)]), 0.25, 7))

    def draw(self, surface, cam):
        rot = pygame.transform.rotate(self.sprite, -math.degrees(self.angle))
        shadow = rot.copy()
        shadow.fill((0, 0, 0, 90), special_flags=pygame.BLEND_RGBA_MULT)
        pos = (self.x - cam[0], self.y - cam[1])
        surface.blit(shadow, shadow.get_rect(center=(pos[0] + 4, pos[1] + 5)))
        surface.blit(rot, rot.get_rect(center=pos))


# ---------- jogo ----------
class Game:
    MENU_ITEMS = ["JOGAR", "CONTROLES", "SAIR"]

    def __init__(self, screen=None):
        pygame.init()
        pygame.display.set_caption("TURBO RUSH")
        self.screen = screen or pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.fonts = {s: pygame.font.Font(None, s) for s in (140, 72, 48, 34)}
        self.track = Track()
        i = self.track.count - START_BACK
        self.car = Car(self.track.center[i], self.track.tangents[i])
        self.state, self.menu_index, self.running, self.ticks, self.cam = MENU, 0, True, 0.0, [0.0, 0.0]
        self.reset_race()

    def reset_race(self):
        self.car.reset()
        self.particles, self.idx, self.checkpoint, self.laps_done = [], self.track.count - START_BACK, False, 0
        self.race_time = self.lap_start = self.last_lap_time = self.banner_timer = self.flash = self.count_timer = self.go_timer = 0.0

    def start_race(self):
        self.reset_race()
        self.state = COUNTDOWN
        self.follow_camera(self.car.x, self.car.y, None)

    def follow_camera(self, x, y, dt):
        k = 1.0 if dt is None else min(1.0, CAMERA_SMOOTH * dt)
        for i, (v, size, world) in enumerate(((x, SCREEN_WIDTH, WORLD_WIDTH), (y, SCREEN_HEIGHT, WORLD_HEIGHT))):
            self.cam[i] += (max(0, min(world - size, v - size / 2)) - self.cam[i]) * k

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        if event.type != pygame.KEYDOWN:
            return
        k, s = event.key, self.state
        enter = k in (pygame.K_RETURN, pygame.K_KP_ENTER)
        if s == MENU:
            if k in (pygame.K_w, pygame.K_UP):
                self.menu_index = (self.menu_index - 1) % 3
            elif k in (pygame.K_s, pygame.K_DOWN):
                self.menu_index = (self.menu_index + 1) % 3
            elif enter or k == pygame.K_SPACE:
                if self.menu_index == 0:
                    self.start_race()
                elif self.menu_index == 1:
                    self.state = CONTROLS
                else:
                    self.running = False
        elif s == CONTROLS and k == pygame.K_ESCAPE:
            self.state = MENU
        elif s in (COUNTDOWN, RACE) and k == pygame.K_ESCAPE:
            self.paused_from, self.state = s, PAUSED
        elif s == PAUSED:
            if enter:
                self.state = self.paused_from
            elif k == pygame.K_r:
                self.start_race()
            elif k == pygame.K_ESCAPE:
                self.state = MENU
        elif s == FINISHED:
            if enter:
                self.start_race()
            elif k == pygame.K_ESCAPE:
                self.state = MENU

    def update(self, dt, controls=None):
        self.ticks += dt
        controls = controls or Controls.from_keyboard()
        if self.state in (MENU, CONTROLS):                       # menu: câmera passeia pela pista
            self.follow_camera(*self.track.center[int(self.ticks * 8) % self.track.count], dt)
            return
        if self.state == COUNTDOWN:
            self.count_timer += dt
            if self.count_timer >= COUNTDOWN_STEP * 3:
                self.state, self.go_timer = RACE, GO_DURATION
        elif self.state == RACE:
            self.go_timer = max(0.0, self.go_timer - dt)
            self.race_time += dt
            self.car.update(dt, controls, self.track, self.particles)
            self.update_laps()
        elif self.state == FINISHED:
            self.car.update(dt, Controls(), self.track, self.particles)
        if self.state != PAUSED:
            self.banner_timer, self.flash = max(0.0, self.banner_timer - dt), max(0.0, self.flash - dt)
            self.follow_camera(self.car.x, self.car.y, dt)
            for p in self.particles:
                p.update(dt)
            self.particles = [p for p in self.particles if p.life > 0]

    def update_laps(self):
        prev, n = self.idx, self.track.count
        self.idx = self.track.nearest_index(self.car.x, self.car.y, prev)
        if self.idx >= n // 2 and prev < n // 2 + SEARCH_WINDOW:
            self.checkpoint = True                               # passou pelo lado oposto da pista
        if prev > n * 0.85 and self.idx < n * 0.15 and self.checkpoint:
            self.checkpoint = False
            self.laps_done += 1
            self.last_lap_time, self.lap_start = self.race_time - self.lap_start, self.race_time
            self.banner_timer, self.flash = 2.0, 0.35
            burst(self.particles, self.track.center[0], [YELLOW, WHITE, RED, (80, 200, 255), ORANGE], 50, 320, 1.0, 5)
            if self.laps_done >= TOTAL_LAPS:
                self.state = FINISHED
        elif prev < n * 0.15 and self.idx > n * 0.85:
            self.checkpoint = False

    def shade(self, alpha):
        ov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, alpha))
        self.screen.blit(ov, (0, 0))

    def draw(self):
        s, f, cx = self.screen, self.fonts, SCREEN_WIDTH // 2
        t = lambda size, msg, y, color=WHITE: draw_text(s, f[size], msg, (cx, y), color, True)
        self.track.draw(s, self.cam)
        if self.state in (MENU, CONTROLS):
            self.shade(150)
            t(140, "TURBO RUSH", 170 + math.sin(self.ticks * 3) * 6, YELLOW)
            if self.state == MENU:
                for i, item in enumerate(self.MENU_ITEMS):
                    t(72, f"> {item} <" if i == self.menu_index else item, 320 + i * 80, YELLOW if i == self.menu_index else WHITE)
            else:
                t(72, "CONTROLES", 300)
                for i, line in enumerate(["WASD = dirigir", "SHIFT = nitro", "ESC = pausa"]):
                    t(48, line, 380 + i * 55, YELLOW)
                t(34, "Pressione ESC para voltar", SCREEN_HEIGHT - 50, (200, 200, 200))
            return
        for p in self.particles:
            p.draw(s, self.cam)
        self.car.draw(s, self.cam)
        panel = pygame.Surface((300, 150), pygame.SRCALPHA)       # HUD
        panel.fill((0, 0, 0, 150))
        s.blit(panel, (16, 16))
        draw_text(s, f[48], f"VOLTA {min(self.laps_done + 1, TOTAL_LAPS)}/{TOTAL_LAPS}", (30, 24), YELLOW)
        draw_text(s, f[34], f"TEMPO {format_time(self.race_time)}", (30, 64))
        draw_text(s, f[34], f"VELOCIDADE {int(abs(self.car.speed) * 0.5)}", (30, 92))
        draw_text(s, f[34], "NITRO", (30, 124))
        bar = pygame.Rect(126, 128, 164, 16)
        pygame.draw.rect(s, (40, 40, 40), bar)
        pygame.draw.rect(s, (255, 120, 30) if self.car.nitro_on else (60, 200, 255), (126, 128, int(164 * self.car.nitro / NITRO_MAX), 16))
        pygame.draw.rect(s, WHITE, bar, 2)
        if self.flash > 0:
            fl = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            fl.fill((255, 255, 255, int(160 * self.flash / 0.35)))
            s.blit(fl, (0, 0))
        if self.banner_timer > 0 and self.state != FINISHED:
            t(72, f"VOLTA {self.laps_done} COMPLETA!  {format_time(self.last_lap_time)}", 110, YELLOW)
        if self.state == COUNTDOWN:
            self.shade(80)
            step = int(self.count_timer // COUNTDOWN_STEP)
            t(140, str(3 - step) if step < 3 else "GO!", SCREEN_HEIGHT // 2, YELLOW if step < 3 else (80, 255, 120))
        elif self.state == RACE and self.go_timer > 0:
            t(140, "GO!", SCREEN_HEIGHT // 2, (80, 255, 120))
        elif self.state == PAUSED:
            self.shade(170)
            t(140, "PAUSADO", 230)
            for i, line in enumerate(["ENTER = continuar", "R = reiniciar", "ESC = menu"]):
                t(48, line, 340 + i * 55, YELLOW)
        elif self.state == FINISHED:
            self.shade(170)
            t(72, "CORRIDA FINALIZADA!", 220, YELLOW)
            t(140, f"TEMPO: {format_time(self.race_time)}", 330)
            t(48, "Pressione ENTER para jogar novamente.", 450)
            t(48, "Pressione ESC para voltar ao menu.", 500)

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30)
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
