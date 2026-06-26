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
import os

# ==========================================
# CONSTANTS & CONFIGURATION
# ==========================================
WINDOW_W, WINDOW_H = 1280, 720 
GRID_W, GRID_H = 100, 100
TILE_SIZE = 32 

TICK_RATE = 0.3  
FPS = 60         

# Colors
C_BG_DAY = (20, 24, 35)
C_BG_NIGHT = (10, 12, 18)
C_UI_BG = (15, 15, 22, 230)
C_TEXT = (230, 235, 245)

C_CORE = (235, 60, 60)     # Order of the Core (Red/Amber)
C_CACHE = (50, 210, 240)   # Cache Wardens (Cyan)
C_RENDER = (190, 60, 235)  # Render Cult (Purple)
C_GOLD = (255, 215, 0)     # Chosen One / Monument
C_GLITCH = (50, 255, 50)   # Awakened One

# Terrain Types
TR_FLOOR = 0
TR_RIVER = 1
TR_SCHOOL = 2

# Bitmasks for States
ST_WANDERING = 1 << 0
ST_STUDYING  = 1 << 1
ST_DUELING   = 1 << 2
ST_RAID      = 1 << 3

# Faction Data
FACTIONS = {
    0: {"name": "Order of the Core", "color": C_CORE, "spell": "OVERCLOCK", "school_name": "The Overclock Citadel"},
    1: {"name": "Cache Wardens", "color": C_CACHE, "spell": "READ/WRITE SHIELD", "school_name": "The Grand Archive"},
    2: {"name": "Render Cult", "color": C_RENDER, "spell": "FRAME-DROP", "school_name": "The Raster Sanctum"}
}

PREFIXES = [("Overclocked", "atk", 1.3), ("Cache-Stored", "mana", 1.2), ("Volatile", "atk", 1.5), ("Stable", "def", 1.2)]
BASES = ["Wand", "Codex", "Staff", "Amulet", "Core"]
SUFFIXES = ["of the Core", "of the Cache", "of the Render", "of the Root"]

NAME_FIRST = ["Ignis", "Faust", "Ada", "Linus", "Turing", "Grace", "Albus", "Babbage", "Gibson", "Hex"]
NAME_MIDDLE = ["von", "del", "the", "mac", "Cyber", "Null", "Arcane", "Pseudo", "Neo", "bin"]
NAME_LAST = ["Cache", "Root", "Glitch", "Bit", "Byte", "Daemon", "Node", "Core", "Script", "Loop"]

SPRITES = {}
HAS_CUSTOM_SPRITES = False

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
        self.name = f"{random.choice(NAME_FIRST)} {random.choice(NAME_MIDDLE)} {random.choice(NAME_LAST)}"
        self.state = ST_WANDERING
        self.target_x, self.target_y = None, None
        
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
            if world.awakened_entity:
                self.move_towards(world.awakened_entity.grid_x, world.awakened_entity.grid_y, world)
            return

        # Civilization behaviors: Gathering at their home school
        school_pos = world.school_positions.get(self.faction)
        if school_pos and random.random() < 0.15:
            # Anchor pull toward their base
            self.move_towards(school_pos[0] + 1, school_pos[1] + 1, world)
            self.state = ST_STUDYING
            self.knowledge += 3
        else:
            self.state = ST_WANDERING
            self.knowledge += 2 if self.is_chosen else 1

        if self.knowledge > 500: self.rank = "Adept"
        if self.knowledge > 1500: self.rank = "Professor"

        if self.rank == "Professor" and random.randint(1, 100000) == 1 and not world.raid_active:
            world.trigger_root_awakening(self)
            return

        if self.state != ST_STUDYING:
            self.old_x, self.old_y = self.grid_x, self.grid_y
            moves = [(0,1), (0,-1), (1,0), (-1,0)]
            random.shuffle(moves)
            
            for dx, dy in moves:
                nx, ny = self.grid_x + dx, self.grid_y + dy
                if 0 <= nx < GRID_W and 0 <= ny < GRID_H:
                    # Let's prevent them from standing right inside structural walls of schools
                    if world.terrain[nx][ny] == TR_SCHOOL and (nx, ny) in world.school_positions.values():
                        continue
                        
                    occupant = world.grid[nx][ny]
                    if occupant and occupant.faction != self.faction and occupant.state == ST_WANDERING:
                        if world.is_night or random.random() < 0.2:
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
            if world.terrain[nx][ny] != TR_SCHOOL:
                world.grid[self.grid_x][self.grid_y] = None
                self.grid_x, self.grid_y = nx, ny
                world.grid[nx][ny] = self

    def initiate_duel(self, target, world):
        self.state = ST_DUELING
        target.state = ST_DUELING
        self.duel_target = target
        target.duel_target = self
        world.log_event(f"⚔️ {self.name} engaged {target.name}!")

    def process_combat(self, world):
        if not self.duel_target or self.duel_target.hp <= 0:
            self.resolve_combat_win(world)
            return
            
        spell = FACTIONS[self.faction]["spell"]
        dmg = max(1, int((self.iv_atk * 1.5) - (self.duel_target.iv_def * 0.5) + random.randint(0, 5)))
        self.duel_target.hp -= dmg
        
        world.particles.append({"x": self.grid_x, "y": self.grid_y, "tx": self.duel_target.grid_x, "ty": self.duel_target.grid_y, "life": 1.0, "color": self.get_color()})
        world.popups.append({"txt": f"{spell}! (-{dmg})", "x": self.grid_x, "y": self.grid_y, "life": 1.5})

    def resolve_combat_win(self, world):
        self.state = ST_WANDERING
        world.log_event(f"💀 {self.name} deleted {self.duel_target.name}!")
        
        if random.random() < 0.3:
            pfx = random.choice(PREFIXES)
            base = random.choice(BASES)
            sfx = random.choice(SUFFIXES)
            self.equipment = (pfx[0], base, sfx)
            world.log_event(f"✨ {self.name} looted [{pfx[0]} {base} {sfx}]")
            
        world.grid[self.duel_target.grid_x][self.duel_target.grid_y] = None
        world.entities.remove(self.duel_target)
        self.duel_target = None
        self.hp = self.max_hp

    def draw(self, surface, cam_x, cam_y, lerp_alpha):
        screen_x = (self.old_x + (self.grid_x - self.old_x) * lerp_alpha) * TILE_SIZE - cam_x
        screen_y = (self.old_y + (self.grid_y - self.old_y) * lerp_alpha) * TILE_SIZE - cam_y

        if screen_x < -TILE_SIZE or screen_x > WINDOW_W or screen_y < -TILE_SIZE or screen_y > WINDOW_H:
            return 

        rect = pygame.Rect(int(screen_x), int(screen_y), TILE_SIZE-2, TILE_SIZE-2)
        color = self.get_color()

        if HAS_CUSTOM_SPRITES and self.faction in SPRITES:
            surface.blit(SPRITES[self.faction], (rect.x, rect.y))
        else:
            x, y, w, h = rect.x, rect.y, rect.width, rect.height
            # Hat
            pygame.draw.rect(surface, color, (x, y + h//2, w, h//4))         
            pygame.draw.rect(surface, color, (x + w//4, y + h//8, w//2, h//2.5)) 
            # Robe
            pygame.draw.rect(surface, color, (x + w//6, y + h//1.5, w - w//3, h - h//1.5))
            # Face
            pygame.draw.rect(surface, (255, 200, 150), (x + w//4, y + h//2.5, w//2, h//4))
            # Eyes
            eye_color = (255, 50, 50) if self.state == ST_DUELING else (0,0,0)
            pygame.draw.rect(surface, eye_color, (x + w//3, y + h//2.2, 2, 2))
            pygame.draw.rect(surface, eye_color, (x + w - w//3 - 2, y + h//2.2, 2, 2))

        if self.is_chosen:
            pygame.draw.circle(surface, C_GOLD, rect.center, int(TILE_SIZE//1.5), 2)
        if self.state == ST_DUELING and self.duel_target:
            pygame.draw.circle(surface, color, rect.center, int(TILE_SIZE * 1.2), 1)

class World:
    def __init__(self):
        # 0 = Floor, 1 = River, 2 = School Structure
        self.terrain = [[TR_FLOOR for _ in range(GRID_H)] for _ in range(GRID_W)]
        # Metadata map to store aesthetic details (circuit board paths, background variations)
        self.terrain_meta = [[random.randint(0, 5) for _ in range(GRID_H)] for _ in range(GRID_W)]
        
        self.grid = [[None for _ in range(GRID_H)] for _ in range(GRID_W)]
        self.entities = []
        self.particles = []
        self.popups = []
        self.event_log = []
        
        self.tick_count = 0
        self.is_night = False
        self.raid_active = False
        self.awakened_entity = None
        
        self.school_positions = {} # Faction ID -> (x, y) coordinates
        
        # Build Map Geometry
        self.generate_rivers()
        self.generate_schools()
        
        # Populate World Entities
        for i in range(150):
            while True:
                x, y = random.randint(2, GRID_W-3), random.randint(2, GRID_H-3)
                # Keep spawn points clear of major obstructions initially
                if not self.grid[x][y] and self.terrain[x][y] == TR_FLOOR:
                    ent = Entity(x, y, i)
                    self.grid[x][y] = ent
                    self.entities.append(ent)
                    break
                
    def generate_rivers(self):
        # Generate two winding vertical "Data Streams" across the map
        for stream_count in range(2):
            curr_x = random.randint(15 + stream_count*35, 30 + stream_count*35)
            for y in range(GRID_H):
                # Wander subtly left/right
                if random.random() < 0.3:
                    curr_x += random.choice([-1, 1])
                    curr_x = max(0, min(GRID_W - 1, curr_x))
                
                # Make rivers 2-tiles wide for mass
                self.terrain[curr_x][y] = TR_RIVER
                if curr_x + 1 < GRID_W:
                    self.terrain[curr_x+1][y] = TR_RIVER

    def generate_schools(self):
        # Place grand campuses for the three factions away from edges
        positions = [(15, 20), (50, 70), (80, 25)]
        for faction_id, pos in enumerate(positions):
            sx, sy = pos
            self.school_positions[faction_id] = (sx, sy)
            
            # Form a 4x4 structural sector for each academy campus
            for x in range(sx, sx + 4):
                for y in range(sy, sy + 4):
                    if 0 <= x < GRID_W and 0 <= y < GRID_H:
                        self.terrain[x][y] = TR_SCHOOL

    def log_event(self, text):
        self.event_log.append(text)
        if len(self.event_log) > 6:
            self.event_log.pop(0)

    def trigger_root_awakening(self, entity):
        self.raid_active = True
        self.awakened_entity = entity
        entity.state = ST_RAID
        entity.uid = 9999
        entity.max_hp = 9999
        entity.hp = 9999
        entity.name = f"AWAKENED_{entity.name}"
        self.log_event(f"⚠️ EXCEPTION: {entity.name} gained ROOT PRIVILEGES!")
        
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

        self.particles = [p for p in self.particles if p["life"] > 0]
        self.popups = [p for p in self.popups if p["life"] > 0]

class Engine:
    def __init__(self):
        pygame.init()
        
        global WINDOW_W, WINDOW_H
        info = pygame.display.Info()
        WINDOW_W, WINDOW_H = info.current_w, info.current_h
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), pygame.FULLSCREEN)
        
        pygame.display.set_caption("Arcane CPU Civilization")
        pygame.mouse.set_visible(False) 
        
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Consolas', 16, bold=True)
        self.title_font = pygame.font.SysFont('Consolas', 22, bold=True)
        
        self.world = World()
        self.last_tick_time = time.time()
        
        self.cam_x, self.cam_y = 0.0, 0.0
        self.target_ent = random.choice(self.world.entities) if self.world.entities else None
        self.cam_timer = 0

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE: 
                        running = False
                    if event.key == pygame.K_SPACE: 
                        if self.world.entities:
                            self.target_ent = random.choice(self.world.entities)
                            self.cam_timer = 0

            now = time.time()
            if now - self.last_tick_time >= TICK_RATE:
                self.world.tick()
                self.last_tick_time = now
                
                self.cam_timer += TICK_RATE
                if self.cam_timer > 15 or self.target_ent not in self.world.entities:
                    if self.world.entities:
                        self.target_ent = random.choice(self.world.entities)
                    self.cam_timer = 0
                    
            lerp_alpha = min(1.0, (now - self.last_tick_time) / TICK_RATE)
            self.render(lerp_alpha, dt)
            
        pygame.quit()
        sys.exit()

    def render(self, lerp_alpha, dt):
        bg_color = C_BG_NIGHT if self.world.is_night else C_BG_DAY
        if self.world.raid_active: bg_color = (35, 12, 12) 
        self.screen.fill(bg_color)
        
        # Smooth tracking camera camera variables
        if self.target_ent:
            ent_screen_x = (self.target_ent.old_x + (self.target_ent.grid_x - self.target_ent.old_x) * lerp_alpha) * TILE_SIZE
            ent_screen_y = (self.target_ent.old_y + (self.target_ent.grid_y - self.target_ent.old_y) * lerp_alpha) * TILE_SIZE
            target_cx = ent_screen_x - WINDOW_W / 2
            target_cy = ent_screen_y - WINDOW_H / 2
            self.cam_x += (target_cx - self.cam_x) * 0.05
            self.cam_y += (target_cy - self.cam_y) * 0.05

        # Precise Culling bounds calculations
        start_grid_x = max(0, int(self.cam_x // TILE_SIZE))
        end_grid_x = min(GRID_W, int((self.cam_x + WINDOW_W) // TILE_SIZE) + 2)
        start_grid_y = max(0, int(self.cam_y // TILE_SIZE))
        end_grid_y = min(GRID_H, int((self.cam_y + WINDOW_H) // TILE_SIZE) + 2)

        # Dynamic sine wave timing values for animations
        pulse_val = (math.sin(time.time() * 4) + 1) / 2
        flow_offset = int(time.time() * 40) % TILE_SIZE

        # ==========================================
        # RENDER LAYER 1: BACKGROUND LANDSCAPE & TEXTURES
        # ==========================================
        for gx in range(start_grid_x, end_grid_x):
            for gy in range(start_grid_y, end_grid_y):
                tx = gx * TILE_SIZE - int(self.cam_x)
                ty = gy * TILE_SIZE - int(self.cam_y)
                terrain_type = self.world.terrain[gx][gy]
                meta = self.world.terrain_meta[gx][gy]

                if terrain_type == TR_FLOOR:
                    # Render Circuit-Board style micro texture details
                    base_shade = 22 if self.world.is_night else 32
                    if meta == 1: # Line variant
                        pygame.draw.rect(self.screen, (base_shade+8, base_shade+12, base_shade+20), (tx+4, ty+4, TILE_SIZE-8, 2))
                    elif meta == 2: # Node dot variant
                        pygame.draw.circle(self.screen, (base_shade+15, base_shade+15, base_shade+25), (tx+TILE_SIZE//2, ty+TILE_SIZE//2), 2)
                    elif meta == 3: # Right-angled corner microcircuit trace
                        pygame.draw.lines(self.screen, (base_shade+6, base_shade+10, base_shade+18), False, [(tx, ty+16), (tx+16, ty+16), (tx+16, ty+32)], 1)

                elif terrain_type == TR_RIVER:
                    # Neon Animated Cyber Data River
                    r_col = (10, 45 + int(pulse_val * 15), 110 + int(pulse_val * 30)) if self.world.is_night else (15, 75, 180)
                    pygame.draw.rect(self.screen, r_col, (tx, ty, TILE_SIZE, TILE_SIZE))
                    
                    # Flowing bits / wave current particles inside rivers
                    bit_y = (ty + flow_offset + (gx * 7) % TILE_SIZE) % TILE_SIZE
                    pygame.draw.rect(self.screen, (60, 180, 255), (tx + TILE_SIZE//2 - 1, ty + bit_y, 3, 6))

        # ==========================================
        # RENDER LAYER 2: PROCEDURAL CIVILIZATION SCHOOLS
        # ==========================================
        for f_id, pos in self.world.school_positions.items():
            sx, sy = pos
            tx = sx * TILE_SIZE - int(self.cam_x)
            ty = sy * TILE_SIZE - int(self.cam_y)
            
            # Check if building is inside visible frame
            if -150 < tx < WINDOW_W + 150 and -150 < ty < WINDOW_H + 150:
                f_color = FACTIONS[f_id]["color"]
                
                # Base Foundations
                pygame.draw.rect(self.screen, (25, 25, 35), (tx, ty, TILE_SIZE*4, TILE_SIZE*4), border_radius=12)
                pygame.draw.rect(self.screen, f_color, (tx, ty, TILE_SIZE*4, TILE_SIZE*4), 3, border_radius=12)
                
                # Inner Cyber Pillars
                for step in range(4):
                    pygame.draw.rect(self.screen, (40, 40, 55), (tx + 12 + step*28, ty + 12, 16, TILE_SIZE*3), border_radius=4)
                
                # Main Core Reactor Building (Center Piece)
                center_rect = pygame.Rect(tx + TILE_SIZE + 4, ty + TILE_SIZE + 4, TILE_SIZE*2 - 8, TILE_SIZE*2 - 8)
                pygame.draw.rect(self.screen, (15, 15, 22), center_rect, border_radius=8)
                
                # Pulsing energy array
                g_radius = int(12 + pulse_val * 14)
                glow_surf = pygame.Surface((g_radius*2, g_radius*2), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (f_color[0], f_color[1], f_color[2], 65), (g_radius, g_radius), g_radius)
                self.screen.blit(glow_surf, (center_rect.centerx - g_radius, center_rect.centery - g_radius))
                
                pygame.draw.circle(self.screen, f_color, center_rect.center, 8)
                pygame.draw.circle(self.screen, (255, 255, 255), center_rect.center, 4)

                # Floating Text Title for the Campus
                t_surf = self.font.render(FACTIONS[f_id]["school_name"], True, f_color)
                self.screen.blit(t_surf, (tx + (TILE_SIZE*2) - t_surf.get_width()//2, ty - 24))

        # Ambient structural grid lines
        grid_color = (26, 30, 42) if not self.world.is_night else (14, 16, 24)
        for x in range(0, GRID_W * TILE_SIZE, TILE_SIZE):
            if -TILE_SIZE < x - self.cam_x < WINDOW_W:
                pygame.draw.line(self.screen, grid_color, (x - self.cam_x, 0), (x - self.cam_x, WINDOW_H))
        for y in range(0, GRID_H * TILE_SIZE, TILE_SIZE):
            if -TILE_SIZE < y - self.cam_y < WINDOW_H:
                pygame.draw.line(self.screen, grid_color, (0, y - self.cam_y), (WINDOW_W, y - self.cam_y))

        # ==========================================
        # RENDER LAYER 3: SIMULATION ENTITIES & VFX
        # ==========================================
        for e in self.world.entities:
            e.draw(self.screen, self.cam_x, self.cam_y, lerp_alpha)
            
        for p in self.world.particles:
            p["life"] -= dt
            sx = p["x"] * TILE_SIZE - self.cam_x + TILE_SIZE/2
            sy = p["y"] * TILE_SIZE - self.cam_y + TILE_SIZE/2
            tx = p["tx"] * TILE_SIZE - self.cam_x + TILE_SIZE/2
            ty = p["ty"] * TILE_SIZE - self.cam_y + TILE_SIZE/2
            
            thickness = max(1, int(p["life"] * 6))
            pygame.draw.line(self.screen, p["color"], (sx, sy), (tx, ty), thickness)
            
            lerp_proj_x = sx + (tx - sx) * (1.0 - p["life"])
            lerp_proj_y = sy + (ty - sy) * (1.0 - p["life"])
            pygame.draw.circle(self.screen, (255, 255, 255), (int(lerp_proj_x), int(lerp_proj_y)), thickness + 2)
            
        for p in self.world.popups:
            p["life"] -= dt * 1.5
            sx = p["x"] * TILE_SIZE - self.cam_x
            sy = p["y"] * TILE_SIZE - self.cam_y - (30 - p["life"] * 15)
            
            txt = self.font.render(p["txt"], True, C_TEXT)
            self.screen.blit(txt, (sx, sy))

        self.draw_ui()
        pygame.display.flip()

    def draw_ui(self):
        y_offset = WINDOW_H - 160
        for log in self.world.event_log:
            txt = self.font.render(log, True, C_TEXT)
            self.screen.blit(txt, (30, y_offset))
            y_offset += 22
            
        if self.target_ent:
            hud_rect = pygame.Surface((350, 250), pygame.SRCALPHA)
            pygame.draw.rect(hud_rect, C_UI_BG, (0, 0, 350, 250), border_radius=10)
            pygame.draw.rect(hud_rect, C_TEXT, (0, 0, 350, 250), 2, border_radius=10)
            self.screen.blit(hud_rect, (WINDOW_W - 380, 30))
            
            e = self.target_ent
            title = self.title_font.render(f"SYS_TRACE: {e.name}", True, C_GOLD if e.is_chosen else C_TEXT)
            self.screen.blit(title, (WINDOW_W - 360, 45))
            
            stats = [
                f"Faction: {FACTIONS[e.faction]['name']}",
                f"Rank: {e.rank} (XP: {e.knowledge})",
                f"State: {['WANDERING', 'STUDYING', 'DUELING', 'RAID'][int(math.log2(e.state))]}",
                f"HP: {e.hp}/{e.max_hp}",
                f"ATK: {e.iv_atk} | DEF: {e.iv_def} | MP: {e.iv_mana}",
                f"Equip: {e.equipment[0] + ' ' + e.equipment[1] if e.equipment else 'None'}"
            ]
            
            sy = 85
            for s in stats:
                render_s = self.font.render(s, True, C_TEXT)
                self.screen.blit(render_s, (WINDOW_W - 360, sy))
                sy += 25
                
        esc_text = self.font.render("Press ESC to exit | Spacebar to swap camera", True, (100, 100, 120))
        self.screen.blit(esc_text, (30, 30))

if __name__ == "__main__":
    app = Engine()
    app.run()