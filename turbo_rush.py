"""TURBO RUSH - corrida arcade 2D (Pygame). Rodar: python3 turbo_rush.py"""
import math, random, sys
import pygame

# ---------- configurações ----------
SCREEN_WIDTH, SCREEN_HEIGHT, FPS, WORLD_SCALE, CAMERA_SMOOTH = 1280, 720, 60, 1.8, 8.0   # mapa maior que a tela; câmera segue o carro
WORLD_WIDTH, WORLD_HEIGHT = int(SCREEN_WIDTH * WORLD_SCALE), int(SCREEN_HEIGHT * WORLD_SCALE)
CAR_ACCELERATION, CAR_BRAKE, CAR_FRICTION, CAR_MAX_SPEED, CAR_MAX_REVERSE = 320.0, 600.0, 160.0, 440.0, 130.0
CAR_TURN_RATE, CAR_TURN_RATE_FAST, CAR_TURN_MIN_SPEED, STEER_SMOOTH = 3.3, 1.9, 35.0, 7.0
CAR_LENGTH, CAR_WIDTH, CAR_RADIUS, OBSTACLE_RADIUS = 40, 22, 14, 13
OFFROAD_MAX_SPEED, OFFROAD_DRAG, WALL_BOUNCE = 160.0, 380.0, 0.35
NITRO_MAX, NITRO_DRAIN, NITRO_RECHARGE, NITRO_MAX_SPEED, NITRO_ACCELERATION = 100.0, 38.0, 9.0, 600.0, 650.0
TOTAL_LAPS, COUNTDOWN_STEP, GO_DURATION, START_BACK, SEARCH_WINDOW = 3, 0.9, 0.7, 14, 40
ROAD_WIDTH, CURB_WIDTH, GRASS_MARGIN, BARRIER_WIDTH = 150, 10, 60, 10
RADIUS_GRASS = ROAD_WIDTH // 2 + CURB_WIDTH + GRASS_MARGIN
TRACK_POINTS = [(x * WORLD_SCALE, y * WORLD_SCALE) for x, y in [(640, 630), (1000, 610), (1160, 480), (1080, 330), (900, 262), (985, 135), (760, 90),
                                                               (560, 170), (420, 100), (200, 130), (110, 300), (260, 400), (160, 520), (300, 630)]]
OBSTACLES = [(40, 25, "cone"), (62, -28, "tire"), (110, 0, "barrier"), (150, -30, "cone"), (160, 28, "cone"),
             (205, 20, "tire"), (250, -20, "barrier"), (300, 28, "cone"), (330, -25, "tire"), (370, 15, "barrier")]
ZONE_WALL, ZONE_GRASS, ZONE_ROAD = 0, 1, 2
MENU, CONTROLS, COUNTDOWN, RACE, PAUSED, FINISHED = range(6)
WHITE, BLACK, YELLOW, ORANGE, RED, GREEN = (255, 255, 255), (0, 0, 0), (255, 214, 52), (255, 140, 30), (230, 50, 50), (80, 255, 120)
rnd = random.uniform


def format_time(s):
    return f"{int(max(0, s) // 60):02d}:{int(max(0, s) % 60):02d}"


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


class Particle:
    def __init__(self, pos, vel, color, life, size):
        self.x, self.y, self.vx, self.vy, self.color, self.life, self.max_life, self.size = *pos, *vel, color, life, life, size
    def update(self, dt):
        self.life -= dt
        self.x, self.y, self.vx, self.vy = self.x + self.vx * dt, self.y + self.vy * dt, self.vx * 0.96, self.vy * 0.96
    def draw(self, surface, cam):
        pygame.draw.circle(surface, self.color, (int(self.x - cam[0]), int(self.y - cam[1])), max(1, int(self.size * self.life / self.max_life)))


def burst(particles, pos, colors, count, speed, life, size):
    for _ in range(count):
        a, s = rnd(0, math.tau), rnd(0.3, 1.0) * speed
        particles.append(Particle(pos, (math.cos(a) * s, math.sin(a) * s), random.choice(colors), rnd(0.6, 1) * life, rnd(0.6, 1) * size))


class Track:
    """Pista fechada: linha central (spline), imagem pronta e mapa de zonas (muro/grama/estrada)."""
    def __init__(self):
        pts, n = TRACK_POINTS, len(TRACK_POINTS)
        self.center = [tuple(0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (3 * b - a - 3 * c + d) * t ** 3)
                             for a, b, c, d in zip(pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]))
                       for i in range(n) for t in [s / 30 for s in range(30)]]
        self.count = len(self.center)
        self.tangents = [math.atan2(self.center[(i + 1) % self.count][1] - y, self.center[(i + 1) % self.count][0] - x)
                         for i, (x, y) in enumerate(self.center)]
        self.zones = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))                      # canal vermelho = zona
        self._circles(self.zones, (ZONE_GRASS, 0, 0), RADIUS_GRASS)
        self._circles(self.zones, (ZONE_ROAD, 0, 0), ROAD_WIDTH // 2 + CURB_WIDTH // 2)
        self.obstacles = [{"pos": (self.center[i][0] + math.cos(self.tangents[i] + 1.57) * o * ROAD_WIDTH / 96,
                                   self.center[i][1] + math.sin(self.tangents[i] + 1.57) * o * ROAD_WIDTH / 96), "kind": k}
                          for i, o, k in OBSTACLES]
        random.seed(7)
        self.image = self._build_image()
        random.seed()
    def _circles(self, surf, color, radius, alt=None):
        for i, p in enumerate(self.center):
            pygame.draw.circle(surf, alt[i // 3 % 2] if alt else color, p, radius)
    def _build_image(self):
        img = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))
        img.fill((32, 108, 54))
        self._circles(img, (210, 210, 210), RADIUS_GRASS + BARRIER_WIDTH)
        self._circles(img, (46, 150, 70), RADIUS_GRASS)
        self._circles(img, None, ROAD_WIDTH // 2 + CURB_WIDTH, [(225, 50, 50), (245, 245, 245)])
        self._circles(img, (62, 64, 74), ROAD_WIDTH // 2)
        for i in range(0, self.count, 8):
            pygame.draw.line(img, (235, 235, 235), self.center[i], self.center[(i + 3) % self.count], 3)
        (x, y), a, k = self.center[0], self.tangents[0], 14                                # linha de largada xadrez
        for c in range(10):
            for r in range(2):
                px, py = x + math.cos(a + 1.57) * (c - 5) * k + math.cos(a) * (r - 1) * k, y + math.sin(a + 1.57) * (c - 5) * k + math.sin(a) * (r - 1) * k
                pygame.draw.rect(img, WHITE if (c + r) % 2 else BLACK, (px - k // 2, py - k // 2, k, k))
        for _ in range(500):                                                                # árvores fora da pista
            x, y = random.randint(20, WORLD_WIDTH - 20), random.randint(20, WORLD_HEIGHT - 20)
            if all(math.hypot(x - cx, y - cy) > RADIUS_GRASS + BARRIER_WIDTH + 24 for cx, cy in self.center[::4]):
                pygame.draw.circle(img, (20, 80, 40), (x + 4, y + 5), 20)
                pygame.draw.circle(img, (34, 139, 64), (x, y - 4), 18)
                pygame.draw.circle(img, (60, 170, 80), (x - 5, y - 9), 8)
        return img
    def zone_at(self, x, y):
        return self.zones.get_at((int(x), int(y)))[0] if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT else ZONE_WALL
    def nearest_index(self, x, y, around):
        return min(((around + k) % self.count for k in range(-SEARCH_WINDOW, SEARCH_WINDOW + 1)),
                   key=lambda i: (self.center[i][0] - x) ** 2 + (self.center[i][1] - y) ** 2)
    def draw(self, surface, cam):
        surface.blit(self.image, (-int(cam[0]), -int(cam[1])))
        for o in self.obstacles:
            p = (int(o["pos"][0] - cam[0]), int(o["pos"][1] - cam[1]))
            pygame.draw.ellipse(surface, (20, 20, 20), (p[0] - 12, p[1] - 4, 28, 20))
            if o["kind"] == "cone":
                pygame.draw.polygon(surface, ORANGE, [(p[0], p[1] - 14), (p[0] - 10, p[1] + 8), (p[0] + 10, p[1] + 8)])
            else:                                                                           # pneu ou barreira
                pygame.draw.circle(surface, (25, 25, 25) if o["kind"] == "tire" else RED, p, OBSTACLE_RADIUS)
                pygame.draw.circle(surface, (90, 90, 90) if o["kind"] == "tire" else WHITE, p, OBSTACLE_RADIUS - 5, 3)


class Car:
    def __init__(self, pos, angle):
        self.start_pos, self.start_angle = pos, angle
        self.sprite = pygame.Surface((CAR_LENGTH, CAR_WIDTH), pygame.SRCALPHA)
        pygame.draw.rect(self.sprite, (230, 40, 50), (0, 0, CAR_LENGTH, CAR_WIDTH), border_radius=8)
        pygame.draw.rect(self.sprite, WHITE, (6, CAR_WIDTH // 2 - 2, CAR_LENGTH - 14, 4))
        pygame.draw.rect(self.sprite, (60, 170, 230), (17, 3, 9, CAR_WIDTH - 6), border_radius=3)
        pygame.draw.rect(self.sprite, YELLOW, (CAR_LENGTH - 4, 2, 3, CAR_WIDTH - 4))
        self.reset()
    def reset(self):
        self.x, self.y = self.start_pos
        self.angle, self.speed, self.steer, self.nitro, self.hit_cooldown = self.start_angle, 0.0, 0.0, NITRO_MAX, 0.0
        self.nitro_on = self.offroad = self.braking = False
    def update(self, dt, c, track, particles):
        self.hit_cooldown, self.braking = max(0.0, self.hit_cooldown - dt), False
        want = c.nitro and not c.brake                                                     # nitro liga/desliga
        self.nitro_on = want and self.nitro > 0 and (self.nitro_on or self.nitro >= 8)
        self.nitro = max(0.0, self.nitro - NITRO_DRAIN * dt) if self.nitro_on else min(NITRO_MAX, self.nitro + NITRO_RECHARGE * dt)
        top = OFFROAD_MAX_SPEED if self.offroad else NITRO_MAX_SPEED if self.nitro_on else CAR_MAX_SPEED
        if self.nitro_on or c.throttle:                                                    # acelera / freia / atrito
            self.speed += (NITRO_ACCELERATION if self.nitro_on else CAR_ACCELERATION) * dt
        elif c.brake:
            self.braking = self.speed > 60
            self.speed -= (CAR_BRAKE if self.speed > 0 else CAR_ACCELERATION * 0.6) * dt
        else:
            self.speed -= math.copysign(min(abs(self.speed), CAR_FRICTION * dt), self.speed)
        if self.offroad and self.speed > top:
            self.speed -= min(self.speed - top, OFFROAD_DRAG * dt)
        self.speed = max(-CAR_MAX_REVERSE, min(top, self.speed))
        self.steer += ((c.right - c.left) - self.steer) * min(1.0, STEER_SMOOTH * dt)     # volante suave
        rate = CAR_TURN_RATE + (CAR_TURN_RATE_FAST - CAR_TURN_RATE) * min(1.0, abs(self.speed) / CAR_MAX_SPEED)
        self.angle += self.steer * rate * min(1.0, abs(self.speed) / CAR_TURN_MIN_SPEED) * dt * (1 if self.speed >= 0 else -1)
        dx, dy = math.cos(self.angle), math.sin(self.angle)
        nx, ny = self.x + dx * self.speed * dt, self.y + dy * self.speed * dt
        if track.zone_at(nx, ny) == ZONE_WALL:                                             # muro: desliza em um eixo
            nx, ny = (nx, self.y) if track.zone_at(nx, self.y) else (self.x, ny) if track.zone_at(self.x, ny) else (self.x, self.y)
            if abs(self.speed) > 80:
                burst(particles, (self.x + dx * 18, self.y + dy * 18), [(230, 230, 230)], 12, 220, 0.45, 4)
            self.speed *= -WALL_BOUNCE if self.speed > 150 else WALL_BOUNCE
        self.x, self.y, self.offroad = nx, ny, track.zone_at(nx, ny) == ZONE_GRASS
        for o in track.obstacles:                                                          # obstáculos
            ox, oy = o["pos"]
            dist = max(math.hypot(self.x - ox, self.y - oy), 0.1)
            if dist < CAR_RADIUS + OBSTACLE_RADIUS:
                if self.hit_cooldown <= 0:
                    self.speed, self.hit_cooldown = self.speed * 0.45, 0.4
                    burst(particles, (ox, oy), [ORANGE, YELLOW, WHITE], 12, 220, 0.45, 4)
                px, py = self.x + (self.x - ox) / dist * (CAR_RADIUS + OBSTACLE_RADIUS - dist), self.y + (self.y - oy) / dist * (CAR_RADIUS + OBSTACLE_RADIUS - dist)
                if track.zone_at(px, py):
                    self.x, self.y = px, py
        bx, by = self.x - dx * CAR_LENGTH / 2, self.y - dy * CAR_LENGTH / 2                # fumaça, poeira, chamas
        if self.braking:
            particles += [Particle((bx - dy * s * 8, by + dx * s * 8), (rnd(-25, 25), rnd(-25, 25)), (200, 200, 200), 0.6, 8) for s in (-1, 1)]
        if self.offroad and abs(self.speed) > 60 and random.random() < 0.5:
            particles.append(Particle((bx, by), (rnd(-30, 30), rnd(-30, 30)), (140, 190, 110), 0.4, 5))
        if self.nitro_on:
            particles += [Particle((bx, by), (-dx * 260 - dy * s * 120, -dy * 260 + dx * s * 120), random.choice([ORANGE, YELLOW, (255, 90, 30)]), 0.25, 7)
                          for s in (rnd(-0.25, 0.25), rnd(-0.25, 0.25))]
    def draw(self, surface, cam):
        rot = pygame.transform.rotate(self.sprite, -math.degrees(self.angle))
        pos = (self.x - cam[0], self.y - cam[1])
        surface.blit(rot, rot.get_rect(center=pos))


class Game:
    def __init__(self, screen=None):
        pygame.init()
        pygame.display.set_caption("TURBO RUSH")
        self.screen, self.clock = screen or pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT)), pygame.time.Clock()
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
        for i, (v, view, world) in enumerate(((x, SCREEN_WIDTH, WORLD_WIDTH), (y, SCREEN_HEIGHT, WORLD_HEIGHT))):
            self.cam[i] += (max(0, min(world - view, v - view / 2)) - self.cam[i]) * (1.0 if dt is None else min(1.0, CAMERA_SMOOTH * dt))
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        if event.type != pygame.KEYDOWN:
            return
        k, s = event.key, self.state
        enter, esc = k in (pygame.K_RETURN, pygame.K_KP_ENTER), k == pygame.K_ESCAPE
        if s == MENU:
            self.menu_index = (self.menu_index + (k in (pygame.K_s, pygame.K_DOWN)) - (k in (pygame.K_w, pygame.K_UP))) % 3
            if enter or k == pygame.K_SPACE:
                [self.start_race, lambda: setattr(self, "state", CONTROLS), lambda: setattr(self, "running", False)][self.menu_index]()
        elif s in (COUNTDOWN, RACE) and esc:
            self.paused_from, self.state = s, PAUSED
        elif s == PAUSED and enter:
            self.state = self.paused_from
        elif s in (PAUSED, FINISHED) and (enter and s == FINISHED or k == pygame.K_r and s == PAUSED):
            self.start_race()
        elif s in (CONTROLS, PAUSED, FINISHED) and esc:
            self.state = MENU
    def update(self, dt, controls=None):
        self.ticks += dt
        controls = controls or Controls.from_keyboard()
        if self.state in (MENU, CONTROLS):                                                 # menu: câmera passeia pela pista
            return self.follow_camera(*self.track.center[int(self.ticks * 8) % self.track.count], dt)
        if self.state == COUNTDOWN:
            self.count_timer += dt
            if self.count_timer >= COUNTDOWN_STEP * 3:
                self.state, self.go_timer = RACE, GO_DURATION
        elif self.state in (RACE, FINISHED):
            racing = self.state == RACE
            self.go_timer, self.race_time = max(0.0, self.go_timer - dt), self.race_time + dt * racing
            self.car.update(dt, controls if racing else Controls(), self.track, self.particles)
            if racing:
                self.update_laps()
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
            self.checkpoint = True                                                         # passou pelo lado oposto
        if prev > n * 0.85 and self.idx < n * 0.15 and self.checkpoint:                    # volta válida
            self.checkpoint, self.laps_done = False, self.laps_done + 1
            self.last_lap_time, self.lap_start, self.banner_timer, self.flash = self.race_time - self.lap_start, self.race_time, 2.0, 0.35
            burst(self.particles, self.track.center[0], [YELLOW, WHITE, RED, (80, 200, 255), ORANGE], 50, 320, 1.0, 5)
            self.state = FINISHED if self.laps_done >= TOTAL_LAPS else self.state
        elif prev < n * 0.15 and self.idx > n * 0.85:
            self.checkpoint = False
    def draw(self):
        s, cx, ov = self.screen, SCREEN_WIDTH // 2, pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        text = lambda size, msg, y, color=WHITE, x=cx, center=True: draw_text(s, self.fonts[size], msg, (x, y), color, center)
        self.track.draw(s, self.cam)
        if self.state in (MENU, CONTROLS):
            ov.fill((0, 0, 0, 150))
            s.blit(ov, (0, 0))
            text(140, "TURBO RUSH", 170 + math.sin(self.ticks * 3) * 6, YELLOW)
            lines = ["JOGAR", "CONTROLES", "SAIR"] if self.state == MENU else ["CONTROLES", "WASD = dirigir", "SHIFT = nitro", "ESC = pausa", "Pressione ESC para voltar"]
            for i, line in enumerate(lines):
                sel = self.state == MENU and i == self.menu_index
                text(72 if i == 0 or self.state == MENU else 48, f"> {line} <" if sel else line, 320 + i * 70, YELLOW if sel or i in (1, 2, 3) and self.state == CONTROLS else WHITE)
            return
        for p in self.particles:
            p.draw(s, self.cam)
        self.car.draw(s, self.cam)
        ov.fill((0, 0, 0, 150))
        s.blit(ov, (16, 16), (0, 0, 300, 150))                                             # HUD
        for size, msg, y, col in [(48, f"VOLTA {min(self.laps_done + 1, TOTAL_LAPS)}/{TOTAL_LAPS}", 24, YELLOW), (34, f"TEMPO {format_time(self.race_time)}", 64, WHITE),
                                  (34, f"VELOCIDADE {int(abs(self.car.speed) * 0.5)}", 92, WHITE), (34, "NITRO", 124, WHITE)]:
            text(size, msg, y, col, 30, False)
        pygame.draw.rect(s, (40, 40, 40), (126, 128, 164, 16))
        pygame.draw.rect(s, ORANGE if self.car.nitro_on else (60, 200, 255), (126, 128, int(164 * self.car.nitro / NITRO_MAX), 16))
        pygame.draw.rect(s, WHITE, (126, 128, 164, 16), 2)
        if self.flash > 0:
            ov.fill((255, 255, 255, int(160 * self.flash / 0.35)))
            s.blit(ov, (0, 0))
        step = int(self.count_timer // COUNTDOWN_STEP)
        screens = {COUNTDOWN: [(140, str(3 - step) if step < 3 else "GO!", 360, YELLOW if step < 3 else GREEN)],
                   RACE: [(140, "GO!", 360, GREEN)] if self.go_timer > 0 else [],
                   PAUSED: [(140, "PAUSADO", 230, WHITE)] + [(48, m, 340 + i * 55, YELLOW) for i, m in enumerate(["ENTER = continuar", "R = reiniciar", "ESC = menu"])],
                   FINISHED: [(72, "CORRIDA FINALIZADA!", 220, YELLOW), (140, f"TEMPO: {format_time(self.race_time)}", 330, WHITE),
                              (48, "Pressione ENTER para jogar novamente.", 450, WHITE), (48, "Pressione ESC para voltar ao menu.", 500, WHITE)]}
        if self.state in (PAUSED, FINISHED):
            ov.fill((0, 0, 0, 170))
            s.blit(ov, (0, 0))
        if self.banner_timer > 0 and self.state != FINISHED:
            text(72, f"VOLTA {self.laps_done} COMPLETA!  {format_time(self.last_lap_time)}", 110, YELLOW)
        for size, msg, y, color in screens.get(self.state, []):
            text(size, msg, y, color)
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
