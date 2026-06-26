"""
ARCANE CPU CIVILIZATION - Zero-Player Ambient Simulation
Architecture: Grid-based logic (Ticks) decoupled from GPU Render Loop (FPS).
Dependencies: pygame (pip install pygame)
"""

import pygame
import random
import math
import time
import sys

# ==========================================
# CONSTANTS & CONFIGURATION
# ==========================================
WINDOW_W, WINDOW_H = 1280, 720
GRID_W, GRID_H = 100, 100
TILE_SIZE = 24

TICK_RATE = 0.3  # Logic updates every 0.3 seconds (~3.3 Hz)
FPS = 60         # Visuals update at 60 FPS

# Colors
C_BG_DAY = (20, 20, 30)
C_BG_NIGHT = (5, 5, 10)
C_UI_BG = (10, 10, 15, 200)
C_TEXT = (220, 220, 220)

C_CORE = (220, 50, 50)     # Order of the Core (Red/Amber)
C_CACHE = (50, 200, 220)   # Cache Wardens (Cyan)
C_RENDER = (180, 50, 220)  # Render Cult (Purple)
C_GOLD = (255, 215, 0)     # Chosen One / Monument
C_GLITCH = (0, 255, 0)     # Awakened One

# Bitmasks for States
ST_WANDERING = 1 << 0
ST_STUDYING  = 1 << 1
ST_DUELING   = 1 << 2
ST_RAID      = 1 << 3

# Pre-calculated LUT for Aura circles (saves CPU trig math)
LUT_CIRCLE = [(math.cos(math.radians(d)), math.sin(math.radians(d))) for d in range(0, 360, 15)]

# Faction Data
FACTIONS = {
    0: {"name": "Order of the Core", "color": C_CORE, "spell": "OVERCLOCK"},
    1: {"name": "Cache Wardens", "color": C_CACHE, "spell": "READ/WRITE SHIELD"},
    2: {"name": "Render Cult", "color": C_RENDER, "spell": "FRAME-DROP"}
}

# Diablo-style Loot Wheel
PREFIXES = [("Overclocked", "atk", 1.3), ("Cache-Stored", "mana", 1.2), ("Volatile", "atk", 1.5), ("Stable", "def", 1.2)]
BASES = ["Wand", "Codex", "Staff", "Amulet", "Core"]
SUFFIXES = ["of the Core", "of the Cache", "of the Render", "of the Root"]
NAMES_POOL = ["Ignis", "Faust", "Ada", "Linus", "Turing", "Grace", "Albus", "Babbage", "Gibson", "Hex"]

# ==========================================
# ENGINE CLASSES
# ==========================================

class Entity:
    def __init__(self, x, y, uid):
        self.uid = uid
        self.grid_x = x
        self.grid_y = y
        self.old_x = x
        self.old_y = y
        
        self.faction = random.randint(0, 2)
        self.name = f"{random.choice(NAMES_POOL)}-{uid}"
        self.state = ST_WANDERING
        self.target_x, self.target_y = None, None
        
        # IV Generation (Pokemon-style limits applied to CPU theme: Max 66 total points, Max 32 per stat)
        self.iv_atk = random.randint(5, 32)
        self.iv_def = random.randint(5, min(32, 66 - self.iv_atk))
        self.iv_mana = min(32, max(5, 66 - self.iv_atk - self.iv_def))
        
        self.is_chosen = (self.iv_atk + self.iv_def + self.iv_mana >= 60)
        
        self.hp = 100
        self.max_hp = 100
        self.knowledge = 0
        self.rank = "Novice"
        self.equipment = None
        self.duel_target = None

    def get_color(self):
        if self.state == ST_RAID: return C_GLITCH
        return FACTIONS[self.faction]["color"]

    def tick_logic(self, world):
        if self.state == ST_DUELING:
            self.process_combat(world)
            return

        if self.state == ST_RAID:
            # Move towards raid boss
            if world.awakened_entity:
                self.move_towards(world.awakened_entity.grid_x, world.awakened_entity.grid_y, world)
            return

        # Routine Wandering / Studying
        self.knowledge += 2 if self.is_chosen else 1
        if self.knowledge > 500: self.rank = "Adept"
        if self.knowledge > 1500: self.rank = "Professor"

        # Check 4th Wall Break (Root Awakening) for Max Level
        if self.rank == "Professor" and random.randint(1, 100000) == 1 and not world.raid_active:
            world.trigger_root_awakening(self)
            return

        # Grid Movement (Random walk)
        self.old_x, self.old_y = self.grid_x, self.grid_y
        moves = [(0,1), (0,-1), (1,0), (-1,0)]
        random.shuffle(moves)
        
        for dx, dy in moves:
            nx, ny = self.grid_x + dx, self.grid_y + dy
            if 0 <= nx < GRID_W and 0 <= ny < GRID_H:
                # Check for enemies to duel
                occupant = world.grid[nx][ny]
                if occupant and occupant.faction != self.faction and occupant.state == ST_WANDERING:
                    if world.is_night or random.random() < 0.2: # Higher aggression at night
                        self.initiate_duel(occupant, world)
                        return
                
                if not occupant:
                    world.grid[self.grid_x][self.grid_y] = None
                    self.grid_x, self.grid_y = nx, ny
                    world.grid[nx][ny] = self
                    break

    def move_towards(self, tx, ty, world):
        self.old_x, self.old_y = self.grid_x, self.grid_y
        dx = 1 if tx > self.grid_x else -1 if tx < self.grid_x else 0
        dy = 1 if ty > self.grid_y else -1 if ty < self.grid_y else 0
        
        if random.random() < 0.5 and dx != 0:
            nx, ny = self.grid_x + dx, self.grid_y
        else:
            nx, ny = self.grid_x, self.grid_y + dy

        if 0 <= nx < GRID_W and 0 <= ny < GRID_H and not world.grid[nx][ny]:
            world.grid[self.grid_x][self.grid_y] = None
            self.grid_x, self.grid_y = nx, ny
            world.grid[nx][ny] = self

    def initiate_duel(self, target, world):
        self.state = ST_DUELING
        target.state = ST_DUELING
        self.duel_target = target
        target.duel_target = self
        world.log_event(f"⚔️ {self.name} engaged {target.name} in a Logic Duel!")

    def process_combat(self, world):
        if not self.duel_target or self.duel_target.hp <= 0:
            self.resolve_combat_win(world)
            return
            
        # Math-only turn based calculation
        spell = FACTIONS[self.faction]["spell"]
        dmg = max(1, int((self.iv_atk * 1.5) - (self.duel_target.iv_def * 0.5) + random.randint(0, 5)))
        self.duel_target.hp -= dmg
        
        # GPU Particle Request
        world.particles.append({"x": self.grid_x, "y": self.grid_y, "tx": self.duel_target.grid_x, "ty": self.duel_target.grid_y, "life": 1.0, "color": self.get_color()})
        world.popups.append({"txt": f"{spell}! (-{dmg})", "x": self.grid_x, "y": self.grid_y, "life": 1.5})

    def resolve_combat_win(self, world):
        self.state = ST_WANDERING
        world.log_event(f"💀 {self.name} deleted {self.duel_target.name}'s HP!")
        
        # Loot Generation
        if random.random() < 0.3:
            pfx = random.choice(PREFIXES)
            base = random.choice(BASES)
            sfx = random.choice(SUFFIXES)
            self.equipment = (pfx[0], base, sfx)
            world.log_event(f"✨ {self.name} looted [{pfx[0]} {base} {sfx}]")
            
        # Reset target
        world.grid[self.duel_target.grid_x][self.duel_target.grid_y] = None
        world.entities.remove(self.duel_target)
        self.duel_target = None
        self.hp = self.max_hp

    def draw(self, surface, cam_x, cam_y, lerp_alpha):
        # Linear Interpolation for smooth 60FPS movement
        screen_x = (self.old_x + (self.grid_x - self.old_x) * lerp_alpha) * TILE_SIZE - cam_x
        screen_y = (self.old_y + (self.grid_y - self.old_y) * lerp_alpha) * TILE_SIZE - cam_y

        if screen_x < -TILE_SIZE or screen_x > WINDOW_W or screen_y < -TILE_SIZE or screen_y > WINDOW_H:
            return # Frustum culling

        rect = pygame.Rect(int(screen_x), int(screen_y), TILE_SIZE-2, TILE_SIZE-2)
        
        if self.state == ST_RAID and self.uid == 9999: # Boss visual
            color = (random.randint(50,255), 0, random.randint(50,255))
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, C_TEXT, rect, 1)
        else:
            pygame.draw.rect(surface, self.get_color(), rect)
            
        if self.is_chosen:
            pygame.draw.rect(surface, C_GOLD, rect, 2)
            
        if self.state == ST_DUELING and self.duel_target:
            pygame.draw.circle(surface, self.get_color(), rect.center, int(TILE_SIZE * 1.5), 1)

class World:
    def __init__(self):
        self.grid = [[None for _ in range(GRID_H)] for _ in range(GRID_W)]
        self.entities = []
        self.particles = []
        self.popups = []
        self.event_log = []
        
        self.tick_count = 0
        self.is_night = False
        self.raid_active = False
        self.awakened_entity = None
        
        # Populate World
        for i in range(120):
            x, y = random.randint(0, GRID_W-1), random.randint(0, GRID_H-1)
            if not self.grid[x][y]:
                ent = Entity(x, y, i)
                self.grid[x][y] = ent
                self.entities.append(ent)
                
    def log_event(self, text):
        self.event_log.append(text)
        if len(self.event_log) > 5:
            self.event_log.pop(0)

    def trigger_root_awakening(self, entity):
        self.raid_active = True
        self.awakened_entity = entity
        entity.state = ST_RAID
        entity.uid = 9999
        entity.max_hp = 9999
        entity.hp = 9999
        entity.name = f"AWAKENED_{entity.name}"
        self.log_event(f"⚠️ CRITICAL EXCEPTION: {entity.name} gained ROOT PRIVILEGES!")
        
        # Update all entities to target the boss
        for e in self.entities:
            if e != entity:
                e.state = ST_RAID

    def tick(self):
        self.tick_count += 1
        if self.tick_count % 100 == 0:
            self.is_night = not self.is_night
            self.log_event("🌙 Night falls. Aggression rising." if self.is_night else "☀️ Day breaks. Cycle resets.")

        for e in self.entities:
            e.tick_logic(self)

        # Remove dead particles/popups
        self.particles = [p for p in self.particles if p["life"] > 0]
        self.popups = [p for p in self.popups if p["life"] > 0]

class Engine:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Arcane CPU Civilization")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Consolas', 14, bold=True)
        self.title_font = pygame.font.SysFont('Consolas', 20, bold=True)
        
        self.world = World()
        self.last_tick_time = time.time()
        
        # Camera
        self.cam_x, self.cam_y = 0.0, 0.0
        self.target_ent = random.choice(self.world.entities)
        self.cam_timer = 0

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            now = time.time()
            if now - self.last_tick_time >= TICK_RATE:
                self.world.tick()
                self.last_tick_time = now
                
                # Camera tracking logic
                self.cam_timer += TICK_RATE
                if self.cam_timer > 20 or self.target_ent not in self.world.entities:
                    if self.world.entities:
                        self.target_ent = random.choice(self.world.entities)
                    self.cam_timer = 0
                    
            # Lerp calculation for frames between ticks
            lerp_alpha = min(1.0, (now - self.last_tick_time) / TICK_RATE)
            
            self.render(lerp_alpha, dt)
            
        pygame.quit()
        sys.exit()

    def render(self, lerp_alpha, dt):
        bg_color = C_BG_NIGHT if self.world.is_night else C_BG_DAY
        if self.world.raid_active: bg_color = (40, 10, 10) # Red flash for raid
        self.screen.fill(bg_color)
        
        # Camera Lerp
        if self.target_ent:
            # Interpolate entity position to target camera
            ent_screen_x = (self.target_ent.old_x + (self.target_ent.grid_x - self.target_ent.old_x) * lerp_alpha) * TILE_SIZE
            ent_screen_y = (self.target_ent.old_y + (self.target_ent.grid_y - self.target_ent.old_y) * lerp_alpha) * TILE_SIZE
            target_cx = ent_screen_x - WINDOW_W / 2
            target_cy = ent_screen_y - WINDOW_H / 2
            self.cam_x += (target_cx - self.cam_x) * 0.05
            self.cam_y += (target_cy - self.cam_y) * 0.05

        # Draw Grid (Optional aesthetic)
        for x in range(0, GRID_W * TILE_SIZE, TILE_SIZE):
            if -TILE_SIZE < x - self.cam_x < WINDOW_W:
                pygame.draw.line(self.screen, (30, 30, 40), (x - self.cam_x, 0), (x - self.cam_x, WINDOW_H))
        for y in range(0, GRID_H * TILE_SIZE, TILE_SIZE):
            if -TILE_SIZE < y - self.cam_y < WINDOW_H:
                pygame.draw.line(self.screen, (30, 30, 40), (0, y - self.cam_y), (WINDOW_W, y - self.cam_y))

        # Draw Entities
        for e in self.world.entities:
            e.draw(self.screen, self.cam_x, self.cam_y, lerp_alpha)
            
        # Draw GPU Particles & Text
        for p in self.world.particles:
            p["life"] -= dt
            sx = p["x"] * TILE_SIZE - self.cam_x + TILE_SIZE/2
            sy = p["y"] * TILE_SIZE - self.cam_y + TILE_SIZE/2
            tx = p["tx"] * TILE_SIZE - self.cam_x + TILE_SIZE/2
            ty = p["ty"] * TILE_SIZE - self.cam_y + TILE_SIZE/2
            pygame.draw.line(self.screen, p["color"], (sx, sy), (tx, ty), max(1, int(p["life"] * 5)))
            
        for p in self.world.popups:
            p["life"] -= dt * 1.5
            sx = p["x"] * TILE_SIZE - self.cam_x
            sy = p["y"] * TILE_SIZE - self.cam_y - (20 - p["life"] * 10)
            txt = self.font.render(p["txt"], True, C_TEXT)
            self.screen.blit(txt, (sx, sy))

        self.draw_ui()
        pygame.display.flip()

    def draw_ui(self):
        # Event Logger
        y_offset = WINDOW_H - 120
        for log in self.world.event_log:
            txt = self.font.render(log, True, C_TEXT)
            self.screen.blit(txt, (20, y_offset))
            y_offset += 20
            
        # HUD for Tracked Entity
        if self.target_ent:
            hud_rect = pygame.Surface((300, 220), pygame.SRCALPHA)
            hud_rect.fill(C_UI_BG)
            self.screen.blit(hud_rect, (WINDOW_W - 320, 20))
            
            e = self.target_ent
            title = self.title_font.render(f"SYS_TRACE: {e.name}", True, C_GOLD if e.is_chosen else C_TEXT)
            self.screen.blit(title, (WINDOW_W - 300, 30))
            
            stats = [
                f"Faction: {FACTIONS[e.faction]['name']}",
                f"Rank: {e.rank} (XP: {e.knowledge})",
                f"State: {'DUELING' if e.state == ST_DUELING else 'WANDERING'}",
                f"HP: {e.hp}/{e.max_hp}",
                f"ATK: {e.iv_atk} | DEF: {e.iv_def} | MP: {e.iv_mana}",
                f"Equip: {e.equipment[0] + ' ' + e.equipment[1] if e.equipment else 'None'}"
            ]
            
            sy = 70
            for s in stats:
                render_s = self.font.render(s, True, C_TEXT)
                self.screen.blit(render_s, (WINDOW_W - 300, sy))
                sy += 25

if __name__ == "__main__":
    app = Engine()
    app.run()