from direct.showbase.ShowBase import ShowBase
from panda3d.core import WindowProperties, Vec3
from panda3d.core import CollisionTraverser, CollisionNode, CollisionRay, CollisionHandlerQueue
from panda3d.core import CollisionHandlerPusher, CollisionSphere
from panda3d.core import BitMask32, Texture, TextureStage
import math


MASK_LEVEL = BitMask32.bit(1)


class Game(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)

        # --- Window ---
        self.win_w = 1280
        self.win_h = 720
        self.center_x = self.win_w // 2
        self.center_y = self.win_h // 2

        props = WindowProperties()
        props.setTitle("Panda3D - FPS Corridor Prototype By Egowarka")
        props.setSize(self.win_w, self.win_h)
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_absolute)
        self.win.requestProperties(props)

        self.disableMouse()

        # --- Textures ---
        # Пол: ground.png рядом с main.py (если нет — просто будет без текстуры)
        self.floor_tex = self.loader.loadTexture("ground.png")
        if self.floor_tex:
            self.floor_tex.setWrapU(Texture.WM_repeat)
            self.floor_tex.setWrapV(Texture.WM_repeat)

        # --- Build level ---
        self.build_lobby_level()

        # --- Player state ---
        self.speed = 10.0
        self.player_height = 1.7
        self.player_radius = 0.4

        self.gravity = 24.0
        self.jump_speed = 8.5
        self.vel_z = 0.0
        self.on_ground = False

        self.mouse_sens = 0.05
        self.heading = 0.0
        self.pitch = 0.0
        self.capture_mouse = True
        self.win.movePointer(0, self.center_x, self.center_y)

        self.player_pos = Vec3(0, 0, 0.0)
        self.player_np = self.render.attachNewNode("player")
        self.player_np.setPos(self.player_pos)
        self.camera.reparentTo(self.player_np)
        self.camera.setPos(0, 0, self.player_height)
        self.camera.setHpr(self.heading, self.pitch, 0)

        # --- Input ---
        self.keys = {"w": False, "s": False, "a": False, "d": False, "shift": False}
        self.accept("w", self.set_key, ["w", True])
        self.accept("w-up", self.set_key, ["w", False])
        self.accept("s", self.set_key, ["s", True])
        self.accept("s-up", self.set_key, ["s", False])
        self.accept("a", self.set_key, ["a", True])
        self.accept("a-up", self.set_key, ["a", False])
        self.accept("d", self.set_key, ["d", True])
        self.accept("d-up", self.set_key, ["d", False])
        self.accept("shift", self.set_key, ["shift", True])
        self.accept("shift-up", self.set_key, ["shift", False])

        self.jump_requested = False
        self.accept("space", self.request_jump)

        self.accept("escape", self.toggle_mouse)

        # --- Collisions ---
        self.cTrav = CollisionTraverser()

        self.pusher = CollisionHandlerPusher()
        player_col = CollisionNode("playerCol")
        player_col.addSolid(CollisionSphere(0, 0, self.player_height * 0.5, self.player_radius))
        player_col.setFromCollideMask(MASK_LEVEL)
        player_col.setIntoCollideMask(BitMask32.allOff())
        self.player_col_np = self.player_np.attachNewNode(player_col)
        self.pusher.addCollider(self.player_col_np, self.player_np)
        self.cTrav.addCollider(self.player_col_np, self.pusher)

        # Ground ray (держим на полу)
        self.ground_handler = CollisionHandlerQueue()

        ray_node = CollisionNode("groundRay")
        ray_node.addSolid(CollisionRay(0, 0, 100, 0, 0, -1))
        ray_node.setFromCollideMask(MASK_LEVEL)
        ray_node.setIntoCollideMask(BitMask32.allOff())
        self.ground_ray_np = self.player_np.attachNewNode(ray_node)
        self.cTrav.addCollider(self.ground_ray_np, self.ground_handler)

        self.taskMgr.add(self.update, "update")

    # ===== Level construction =====

    def make_box(self, pos, scale, color=(0.35, 0.35, 0.35, 1.0), textured=False, tex_tile=(1, 1)):
        """
        pos: (x, y, z)
        scale: (sx, sy, sz)
        """
        n = self.loader.loadModel("models/box")
        n.reparentTo(self.render)
        n.setPos(pos[0], pos[1], pos[2])
        n.setScale(scale[0], scale[1], scale[2])
        n.setCollideMask(MASK_LEVEL)

        # Убираем дефолтную "радужность"
        n.clearTexture()
        n.clearColor()
        n.setColor(color[0], color[1], color[2], color[3])

        if textured and self.floor_tex:
            n.setTexture(self.floor_tex, 1)
            n.setTexScale(TextureStage.getDefault(), tex_tile[0], tex_tile[1])

        return n

    def build_corridor_segment(self, y_center, length, half_width, height, wall_thick=0.25, floor_thick=0.2):
        """
        Строит кусок коридора длиной length (по Y),
        ширина 2*half_width, высота height.
        Центр сегмента по Y = y_center.
        """
        y0 = y_center
        # Пол (верх примерно z=0): ставим его так, чтобы верх был на 0
        floor_z = -floor_thick
        ceil_z = height + floor_thick

        # Пол
        self.make_box(
            pos=(0, y0, floor_z),
            scale=(half_width, length / 2.0, floor_thick),
            color=(0.6, 0.6, 0.6, 1.0),
            textured=True,
            tex_tile=(max(1, int(half_width)), max(1, int(length / 2)))
        )

        # Потолок
        self.make_box(
            pos=(0, y0, ceil_z),
            scale=(half_width, length / 2.0, floor_thick),
            color=(0.25, 0.25, 0.25, 1.0),
            textured=True,
            tex_tile=(max(1, int(half_width)), max(1, int(length / 2)))
        )

        # Левая стена
        self.make_box(
            pos=(-half_width - wall_thick, y0, height / 2.0),
            scale=(wall_thick, length / 2.0, height / 2.0),
            color=(0.32, 0.32, 0.35, 1.0),
            textured=True,
            tex_tile=(max(1, int(length / 2)), max(1, int(height / 2)))
        )

        # Правая стена
        self.make_box(
            pos=(half_width + wall_thick, y0, height / 2.0),
            scale=(wall_thick, length / 2.0, height / 2.0),
            color=(0.32, 0.32, 0.35, 1.0),
            textured=True,
            tex_tile=(max(1, int(length / 2)), max(1, int(height / 2)))
        )

    def build_lobby_level(self):
        """
        Квадратное лобби вокруг (0, 0, 0).
        Игрок спавнится в центре и стоит на полу.
        """
        half_size = 6.0
        height = 3.0
        wall_thick = 0.25
        floor_thick = 0.2

        floor_z = -floor_thick
        ceil_z = height + floor_thick

        # Пол
        self.make_box(
            pos=(0, 0, floor_z),
            scale=(half_size, half_size, floor_thick),
            color=(0.6, 0.6, 0.6, 1.0),
            textured=True,
            tex_tile=(max(1, int(half_size)), max(1, int(half_size)))
        )

        # Потолок
        self.make_box(
            pos=(0, 0, ceil_z),
            scale=(half_size, half_size, floor_thick),
            color=(0.25, 0.25, 0.25, 1.0),
            textured=True,
            tex_tile=(max(1, int(half_size)), max(1, int(half_size)))
        )

        # Стены по Y (север/юг)
        self.make_box(
            pos=(0, half_size + wall_thick, height / 2.0),
            scale=(half_size, wall_thick, height / 2.0),
            color=(0.32, 0.32, 0.35, 1.0),
            textured=True,
            tex_tile=(max(1, int(half_size)), max(1, int(height / 2)))
        )
        self.make_box(
            pos=(0, -half_size - wall_thick, height / 2.0),
            scale=(half_size, wall_thick, height / 2.0),
            color=(0.32, 0.32, 0.35, 1.0),
            textured=True,
            tex_tile=(max(1, int(half_size)), max(1, int(height / 2)))
        )

        # Стены по X (восток/запад)
        self.make_box(
            pos=(half_size + wall_thick, 0, height / 2.0),
            scale=(wall_thick, half_size, height / 2.0),
            color=(0.32, 0.32, 0.35, 1.0),
            textured=True,
            tex_tile=(max(1, int(half_size)), max(1, int(height / 2)))
        )
        self.make_box(
            pos=(-half_size - wall_thick, 0, height / 2.0),
            scale=(wall_thick, half_size, height / 2.0),
            color=(0.32, 0.32, 0.35, 1.0),
            textured=True,
            tex_tile=(max(1, int(half_size)), max(1, int(height / 2)))
        )

    # ===== Player controls =====

    def set_key(self, key, value):
        self.keys[key] = value

    def request_jump(self):
        self.jump_requested = True

    def toggle_mouse(self):
        props = WindowProperties()
        if self.capture_mouse:
            self.capture_mouse = False
            props.setCursorHidden(False)
        else:
            self.capture_mouse = True
            props.setCursorHidden(True)
            self.win.movePointer(0, self.center_x, self.center_y)
        self.win.requestProperties(props)

    def update(self, task):
        dt = globalClock.getDt()
        if dt > 0.05:
            dt = 0.05

        # Mouse look
        if self.capture_mouse and self.win.getProperties().getCursorHidden():
            md = self.win.getPointer(0)
            dx = md.getX() - self.center_x
            dy = md.getY() - self.center_y
            self.win.movePointer(0, self.center_x, self.center_y)

            self.heading -= dx * self.mouse_sens
            self.pitch -= dy * self.mouse_sens
            self.pitch = max(-89.0, min(89.0, self.pitch))

        self.camera.setHpr(self.heading, self.pitch, 0)

        # WASD movement
        move = Vec3(0, 0, 0)
        if self.keys["w"]:
            move.y += 1
        if self.keys["s"]:
            move.y -= 1
        if self.keys["a"]:
            move.x -= 1
        if self.keys["d"]:
            move.x += 1

        if move.lengthSquared() > 0:
            move.normalize()

        current_speed = self.speed * (1.7 if self.keys["shift"] else 1.0)

        heading_rad = math.radians(self.camera.getH())
        cos_h = math.cos(heading_rad)
        sin_h = math.sin(heading_rad)

        world_move = Vec3(
            move.x * cos_h - move.y * sin_h,
            move.x * sin_h + move.y * cos_h,
            0
        )

        self.player_pos += world_move * (current_speed * dt)

        # Gravity / Jump
        self.vel_z -= self.gravity * dt
        self.player_pos.z += self.vel_z * dt

        # Apply position before collisions
        self.player_np.setPos(self.player_pos)
        self.cTrav.traverse(self.render)

        # Sync back in case pusher moved us
        self.player_pos = self.player_np.getPos()

        self.on_ground = False
        if self.ground_handler.getNumEntries() > 0:
            self.ground_handler.sortEntries()
            entry = self.ground_handler.getEntry(0)
            hit_z = entry.getSurfacePoint(self.render).z

            floor_z = hit_z
            if self.player_pos.z <= floor_z:
                self.player_pos.z = floor_z
                self.vel_z = 0.0
                self.on_ground = True

        if self.jump_requested and self.on_ground:
            self.vel_z = self.jump_speed
            self.on_ground = False
        self.jump_requested = False

        self.player_np.setPos(self.player_pos)
        return task.cont


if __name__ == "__main__":
    Game().run()
