"""Testes headless do TURBO RUSH."""
import math
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame
import turbo_rush as t


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k)


def autopilot(g, nitro=False):
    c = t.Controls()
    tgt = g.track.center[(g.idx + 10) % g.track.count]
    want = math.atan2(tgt[1] - g.car.y, tgt[0] - g.car.x)
    diff = (want - g.car.angle + math.pi) % math.tau - math.pi
    c.left, c.right = diff < -0.05, diff > 0.05
    c.throttle = True
    c.nitro = nitro
    return c


def main():
    g = t.Game()
    # menu
    g.draw(); pygame.image.save(g.screen, "/tmp/menu.png")
    g.handle_event(key(pygame.K_s)); assert g.menu_index == 1
    g.handle_event(key(pygame.K_RETURN)); assert g.state == t.CONTROLS
    g.draw(); g.handle_event(key(pygame.K_ESCAPE)); assert g.state == t.MENU
    g.handle_event(key(pygame.K_w)); g.handle_event(key(pygame.K_RETURN))
    assert g.state == t.COUNTDOWN
    # carro parado na contagem
    for _ in range(60):
        g.update(1 / 60, autopilot(g))
    assert g.car.speed == 0 and g.race_time == 0 and g.state == t.COUNTDOWN
    g.draw(); pygame.image.save(g.screen, "/tmp/count.png")
    while g.state == t.COUNTDOWN:
        g.update(1 / 60, autopilot(g))
    assert g.state == t.RACE
    # pausa
    g.handle_event(key(pygame.K_ESCAPE)); assert g.state == t.PAUSED
    rt, pos = g.race_time, (g.car.x, g.car.y)
    for _ in range(30):
        g.update(1 / 60, autopilot(g))
    assert g.race_time == rt and (g.car.x, g.car.y) == pos
    g.draw(); pygame.image.save(g.screen, "/tmp/pause.png")
    g.handle_event(key(pygame.K_RETURN)); assert g.state == t.RACE
    # aceleração, nitro, limites
    for _ in range(120):
        g.update(1 / 60, autopilot(g, nitro=True))
    print("speed", g.car.speed, "nitro", g.car.nitro, "lap", g.laps_done)
    assert g.car.speed > t.CAR_MAX_SPEED * 0.9 and g.car.nitro < t.NITRO_MAX
    # voltas completas
    for i in range(60 * 400):
        if g.state != t.RACE:
            break
        g.update(1 / 60, autopilot(g, nitro=(i % 400 < 60)))
        assert g.track.zone_at(g.car.x, g.car.y) != t.ZONE_WALL
        if i == 1500:
            g.draw(); pygame.image.save(g.screen, "/tmp/race.png")
    print("state", g.state, "laps", g.laps_done, "time", t.format_time(g.race_time))
    assert g.state == t.FINISHED and g.laps_done == 3
    g.update(0.1); g.draw(); pygame.image.save(g.screen, "/tmp/final.png")
    g.handle_event(key(pygame.K_RETURN)); assert g.state == t.COUNTDOWN and g.laps_done == 0
    g.handle_event(key(pygame.K_ESCAPE)); g.handle_event(key(pygame.K_r)); assert g.state == t.COUNTDOWN
    g.handle_event(key(pygame.K_ESCAPE)); g.handle_event(key(pygame.K_ESCAPE)); assert g.state == t.MENU
    # saída da pista: carro andando reto deve ser contido e desacelerado
    g.start_race(); g.state = t.RACE
    c = t.Controls(); c.throttle = True
    for _ in range(60 * 6):
        g.update(1 / 60, c)
        assert g.track.zone_at(g.car.x, g.car.y) != t.ZONE_WALL
    print("reto: pos", int(g.car.x), int(g.car.y), "speed", int(g.car.speed))
    # cruzar a linha sem checkpoint não conta volta
    g.start_race(); g.state = t.RACE
    for _ in range(300):
        g.update(1 / 60, autopilot(g))
    assert g.laps_done == 0
    # obstáculo
    g.reset_race(); g.state = t.RACE
    ox, oy = g.track.obstacles[0]["pos"]; g.car.x, g.car.y, g.car.speed = ox - 20, oy, 300
    g.car.angle = 0; g.update(1 / 60, t.Controls())
    assert g.car.speed < 200 and g.particles
    print("OK")


main()
