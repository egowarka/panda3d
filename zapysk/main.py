"""
Corridor Horror (Panda3D)

Запуск:
  python main.py

Управление:
  WASD — движение
  Shift — бег
  Space — прыжок
  E — взаимодействие (дверь)
  Esc — выход/пауза
  Мышь — поворот камеры (relative mode)
"""

from __future__ import annotations

import math
import random
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from direct.gui.DirectGui import DirectFrame, DirectLabel
from direct.interval.LerpInterval import LerpHprInterval
from direct.showbase.ShowBase import ShowBase
from panda3d.bullet import (
    BulletBoxShape,
    BulletCapsuleShape,
    BulletCharacterControllerNode,
    BulletRigidBodyNode,
    BulletWorld,
)
from panda3d.core import (
    AmbientLight,
    BitMask32,
    CardMaker,
    ClockObject,
    Filename,
    Fog,
    NodePath,
    PointLight,
    PNMImage,
    Texture,
    Fog,
    NodePath,
    PointLight,
    TextNode,
    Vec3,
    Vec4,
    WindowProperties,
)

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    Image = None


# =============================
# Настройки (под пользователя)
# =============================
CORRIDOR_LENGTH = 30.0
CORRIDOR_WIDTH = 3.0
CORRIDOR_HEIGHT = 3.0
LAMP_COUNT = 6
LAMP_INTENSITY = 1.4
WALK_SPEED = 4.0
RUN_SPEED = 7.0
FOG_DENSITY = 0.04

DOOR_UNLOCKED = False


ASSET_ROOT = Path(__file__).resolve().parent / "assets"
TEXTURE_DIR = ASSET_ROOT / "textures"
SFX_DIR = ASSET_ROOT / "sfx"


@dataclass
class InputState:
    forward: bool = False
    backward: bool = False
    left: bool = False
    right: bool = False
    run: bool = False
    interact: bool = False
    jump: bool = False


class PlayerController:
    def __init__(self, base: ShowBase, world: BulletWorld):
        self.base = base
        self.world = world
        self.input_state = InputState()

        shape = BulletCapsuleShape(0.35, 1.0, 1)
        self.controller = BulletCharacterControllerNode(shape, 0.3, "Player")
        self.node = self.base.render.attach_new_node(self.controller)
        self.node.set_pos(0, -CORRIDOR_LENGTH / 2 + 2.0, 1.0)
        self.node.set_collide_mask(BitMask32.bit(1))
        self.world.attach_character(self.controller)

        self.camera_pivot = self.node.attach_new_node("camera_pivot")
        self.camera_pivot.set_z(1.3)
        self.base.camera.reparent_to(self.camera_pivot)
        self.base.camera.set_pos(0, 0, 0)
        self.base.camera.set_hpr(0, 0, 0)

        self.heading = 0.0
        self.pitch = 0.0
        self.breath_timer = 0.0

        self.register_inputs()

    def register_inputs(self) -> None:
        self.base.accept("w", self.set_input, ["forward", True])
        self.base.accept("w-up", self.set_input, ["forward", False])
        self.base.accept("s", self.set_input, ["backward", True])
        self.base.accept("s-up", self.set_input, ["backward", False])
        self.base.accept("a", self.set_input, ["left", True])
        self.base.accept("a-up", self.set_input, ["left", False])
        self.base.accept("d", self.set_input, ["right", True])
        self.base.accept("d-up", self.set_input, ["right", False])
        self.base.accept("shift", self.set_input, ["run", True])
        self.base.accept("shift-up", self.set_input, ["run", False])
        self.base.accept("space", self.set_input, ["jump", True])
        self.base.accept("space-up", self.set_input, ["jump", False])
        self.base.accept("e", self.set_input, ["interact", True])
        self.base.accept("e-up", self.set_input, ["interact", False])

    def set_input(self, name: str, value: bool) -> None:
        setattr(self.input_state, name, value)

    def update(self, dt: float) -> None:
        move_dir = Vec3(0, 0, 0)
        if self.input_state.forward:
            move_dir.y += 1
        if self.input_state.backward:
            move_dir.y -= 1
        if self.input_state.left:
            move_dir.x -= 1
        if self.input_state.right:
            move_dir.x += 1

        if move_dir.length() > 0:
            move_dir.normalize()

        speed = RUN_SPEED if self.input_state.run else WALK_SPEED
        velocity = move_dir * speed
        self.controller.set_linear_movement(velocity, True)

        if self.input_state.jump:
            if self.controller.is_on_ground():
                self.controller.do_jump()

        self.apply_breathing(dt)

    def apply_mouse_look(self, dx: float, dy: float) -> None:
        sensitivity = 0.1
        self.heading -= dx * sensitivity
        self.pitch = max(-75.0, min(75.0, self.pitch - dy * sensitivity))
        self.node.set_h(self.heading)
        self.camera_pivot.set_p(self.pitch)

    def apply_breathing(self, dt: float) -> None:
        self.breath_timer += dt
        sway = math.sin(self.breath_timer * 1.5) * 0.02
        bob = math.sin(self.breath_timer * 2.4) * 0.01
        self.camera_pivot.set_x(sway)
        self.camera_pivot.set_z(1.3 + bob)


class CorridorBuilder:
    def __init__(self, base: ShowBase, world: BulletWorld):
        self.base = base
        self.world = world
        self.root = self.base.render.attach_new_node("corridor")
        self.textures = {}

    def load_tex(self, path: Path) -> Texture:
        filename = Filename.fromOsSpecific(str(path))
        print("Loading texture:", filename)
        print("Exists:", path.exists())
        if not path.exists():
            return self.make_fallback_texture()
        texture = self.base.loader.loadTexture(filename)
        if texture is None:
            return self.make_fallback_texture()
        return texture

    def make_fallback_texture(self) -> Texture:
        image = PNMImage(1, 1)
        image.fill(0.2, 0.2, 0.2)
        texture = Texture("fallback")
        texture.load(image)
        return texture

    def build(self) -> None:
        self.textures["wall"] = self.load_tex(TEXTURE_DIR / "wall.png")
        self.textures["floor"] = self.load_tex(TEXTURE_DIR / "carpet.png")
        self.textures["ceiling"] = self.load_tex(TEXTURE_DIR / "ceiling.png")
        self.textures["door"] = self.load_tex(TEXTURE_DIR / "door.png")

        self.create_floor()
        self.create_ceiling()
        self.create_walls()

    def create_floor(self) -> None:
        card = CardMaker("floor")
        card.set_frame(-CORRIDOR_WIDTH / 2, CORRIDOR_WIDTH / 2, 0, CORRIDOR_LENGTH)
        floor_np = self.root.attach_new_node(card.generate())
        floor_np.set_p(-90)
        floor_np.set_pos(0, -CORRIDOR_LENGTH / 2, 0)
        floor_np.set_texture(self.textures["floor"], 1)
        floor_np.set_tex_scale(1, 3, CORRIDOR_LENGTH / 2)

        shape = BulletBoxShape(Vec3(CORRIDOR_WIDTH / 2, CORRIDOR_LENGTH / 2, 0.1))
        body = BulletRigidBodyNode("floor")
        body.add_shape(shape)
        body_np = self.root.attach_new_node(body)
        body_np.set_pos(0, 0, -0.1)
        body_np.set_collide_mask(BitMask32.bit(1))
        self.world.attach_rigid_body(body)

    def create_ceiling(self) -> None:
        card = CardMaker("ceiling")
        card.set_frame(-CORRIDOR_WIDTH / 2, CORRIDOR_WIDTH / 2, 0, CORRIDOR_LENGTH)
        ceiling_np = self.root.attach_new_node(card.generate())
        ceiling_np.set_p(90)
        ceiling_np.set_pos(0, -CORRIDOR_LENGTH / 2, CORRIDOR_HEIGHT)
        ceiling_np.set_texture(self.textures["ceiling"], 1)
        ceiling_np.set_tex_scale(1, 2, CORRIDOR_LENGTH / 3)

        shape = BulletBoxShape(Vec3(CORRIDOR_WIDTH / 2, CORRIDOR_LENGTH / 2, 0.1))
        body = BulletRigidBodyNode("ceiling")
        body.add_shape(shape)
        body_np = self.root.attach_new_node(body)
        body_np.set_pos(0, 0, CORRIDOR_HEIGHT + 0.1)
        body_np.set_collide_mask(BitMask32.bit(1))
        self.world.attach_rigid_body(body)

    def create_walls(self) -> None:
        wall_thickness = 0.1
        wall_length = CORRIDOR_LENGTH
        wall_height = CORRIDOR_HEIGHT

        for side in (-1, 1):
            card = CardMaker(f"wall_{side}")
            card.set_frame(0, wall_length, 0, wall_height)
            wall_np = self.root.attach_new_node(card.generate())
            wall_np.set_h(90 if side == 1 else -90)
            wall_np.set_pos(side * (CORRIDOR_WIDTH / 2), -CORRIDOR_LENGTH / 2, 0)
            wall_np.set_texture(self.textures["wall"], 1)
            wall_np.set_tex_scale(1, wall_length / 2, wall_height / 2)

            shape = BulletBoxShape(Vec3(wall_thickness, wall_length / 2, wall_height / 2))
            body = BulletRigidBodyNode(f"wall_body_{side}")
            body.add_shape(shape)
            body_np = self.root.attach_new_node(body)
            body_np.set_pos(side * (CORRIDOR_WIDTH / 2 + wall_thickness), 0, wall_height / 2)
            body_np.set_collide_mask(BitMask32.bit(1))
            self.world.attach_rigid_body(body)

        back_shape = BulletBoxShape(Vec3(CORRIDOR_WIDTH / 2, wall_thickness, wall_height / 2))
        back_body = BulletRigidBodyNode("wall_back")
        back_body.add_shape(back_shape)
        back_np = self.root.attach_new_node(back_body)
        back_np.set_pos(0, -CORRIDOR_LENGTH / 2 - wall_thickness, wall_height / 2)
        back_np.set_collide_mask(BitMask32.bit(1))
        self.world.attach_rigid_body(back_body)


class Door:
    def __init__(self, base: ShowBase, world: BulletWorld, textures: dict[str, object]):
        self.base = base
        self.world = world
        self.textures = textures
        self.root = self.base.render.attach_new_node("door_root")
        self.hinge = self.root.attach_new_node("door_hinge")

        self.is_open = False
        self.is_unlocked = DOOR_UNLOCKED
        self.anim: Optional[LerpHprInterval] = None

        self.body_np = self.build_geometry()
        self.lock_sound = self.base.loader.load_sfx(str(SFX_DIR / "locked.wav"))

    def build_geometry(self) -> NodePath:
        door_width = 1.2
        door_height = 2.4
        door_thickness = 0.08

        card = CardMaker("door")
        card.set_frame(0, door_width, 0, door_height)
        door_np = self.hinge.attach_new_node(card.generate())
        door_np.set_p(0)
        door_np.set_pos(0, -door_thickness / 2, 0)
        door_np.set_texture(self.textures["door"], 1)
        door_np.set_tex_scale(1, 1, 1)
        door_np.set_two_sided(True)

        self.root.set_pos(0, CORRIDOR_LENGTH / 2 - 0.2, 0)
        self.hinge.set_pos(-door_width / 2, 0, 0)
        self.hinge.set_h(180)

        shape = BulletBoxShape(Vec3(door_width / 2, door_thickness / 2, door_height / 2))
        body = BulletRigidBodyNode("door_body")
        body.add_shape(shape)
        body.set_kinematic(True)
        body_np = self.root.attach_new_node(body)
        body_np.set_pos(0, 0, door_height / 2)
        body_np.set_collide_mask(BitMask32.bit(1))
        self.world.attach_rigid_body(body)

        return body_np

    def update_collision_transform(self) -> None:
        transform = self.hinge.get_net_transform().get_mat()
        self.body_np.set_mat(transform)

    def try_interact(self) -> str:
        if not self.is_unlocked:
            if self.lock_sound:
                self.lock_sound.play()
            return "Locked"
        if self.is_open:
            return ""
        self.open_door()
        return ""

    def open_door(self) -> None:
        if self.anim:
            self.anim.finish()
        self.is_open = True
        self.anim = LerpHprInterval(self.hinge, 1.2, Vec3(90, 0, 0))
        self.anim.start()

    def update(self) -> None:
        self.update_collision_transform()


class LightingController:
    def __init__(self, base: ShowBase):
        self.base = base
        self.lamps: list[PointLight] = []
        self.lamp_nodes: list[NodePath] = []
        self.flicker_index = 0
        self.flicker_timer = 0.0
        self.setup_lighting()

    def setup_lighting(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.set_color(Vec4(0.08, 0.06, 0.05, 1))
        ambient_np = self.base.render.attach_new_node(ambient)
        self.base.render.set_light(ambient_np)

        spacing = CORRIDOR_LENGTH / (LAMP_COUNT + 1)
        for i in range(LAMP_COUNT):
            light = PointLight(f"lamp_{i}")
            light.set_color(Vec4(1.0, 0.85, 0.65, 1) * LAMP_INTENSITY)
            light_np = self.base.render.attach_new_node(light)
            light_np.set_pos(0, -CORRIDOR_LENGTH / 2 + spacing * (i + 1), CORRIDOR_HEIGHT - 0.2)
            self.base.render.set_light(light_np)
            self.lamps.append(light)
            self.lamp_nodes.append(light_np)

            glow = self.base.loader.load_model("models/misc/sphere")
            glow.reparent_to(light_np)
            glow.set_scale(0.08)
            glow.set_color(1, 0.9, 0.7, 1)
            glow.set_light_off()

        self.flicker_index = random.randint(0, max(0, LAMP_COUNT - 1))

    def update(self, dt: float) -> None:
        self.flicker_timer -= dt
        if self.flicker_timer <= 0:
            self.flicker_timer = random.uniform(0.3, 1.2)
            flicker_light = self.lamps[self.flicker_index]
            base_color = Vec4(1.0, 0.85, 0.65, 1) * LAMP_INTENSITY
            variance = random.uniform(0.5, 1.0)
            flicker_light.set_color(base_color * variance)


class UI:
    def __init__(self, base: ShowBase):
        self.base = base
        self.crosshair = DirectFrame(
            frameColor=(1, 1, 1, 0.9),
            frameSize=(-0.003, 0.003, -0.003, 0.003),
            pos=(0, 0, 0),
        )
        self.prompt = DirectLabel(
            text="",
            scale=0.05,
            pos=(0, 0, -0.2),
            text_fg=(0.95, 0.9, 0.8, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
        )
        self.locked_label = DirectLabel(
            text="",
            scale=0.06,
            pos=(0, 0, 0.4),
            text_fg=(1, 0.5, 0.4, 1),
            text_align=TextNode.ACenter,
            frameColor=(0, 0, 0, 0),
        )
        self.lock_timer = 0.0

    def show_prompt(self, text: str) -> None:
        self.prompt["text"] = text

    def show_locked(self) -> None:
        self.locked_label["text"] = "Locked"
        self.lock_timer = 1.2

    def update(self, dt: float) -> None:
        if self.lock_timer > 0:
            self.lock_timer -= dt
            if self.lock_timer <= 0:
                self.locked_label["text"] = ""


class CorridorHorrorApp(ShowBase):
    def __init__(self) -> None:
        super().__init__()
        self.disable_mouse()
        self.props = self.win.get_properties()
        props = WindowProperties()
        props.set_mouse_mode(WindowProperties.M_relative)
        props.set_cursor_hidden(True)
        self.win.request_properties(props)
        self.base_mouse_x = self.props.get_x_size() / 2
        self.base_mouse_y = self.props.get_y_size() / 2

        self.clock = ClockObject.get_global_clock()

        self.world = BulletWorld()
        self.world.set_gravity(Vec3(0, 0, -9.81))

        self.generate_assets()

        self.corridor = CorridorBuilder(self, self.world)
        self.corridor.build()

        self.player = PlayerController(self, self.world)
        self.door = Door(self, self.world, self.corridor.textures)
        self.lighting = LightingController(self)
        self.ui = UI(self)

        self.setup_fog()
        self.setup_audio()

        self.accept("escape", self.toggle_pause)
        self.paused = False

        self.task_mgr.add(self.update, "update")

    def setup_fog(self) -> None:
        fog = Fog("corridor_fog")
        fog.set_color(0.05, 0.04, 0.03)
        fog.set_exp_density(FOG_DENSITY)
        self.render.set_fog(fog)

    def setup_audio(self) -> None:
        hum = self.loader.load_sfx(str(SFX_DIR / "hum.wav"))
        if hum:
            hum.set_loop(True)
            hum.set_volume(0.2)
            hum.play()

        rumble = self.loader.load_sfx(str(SFX_DIR / "rumble.wav"))
        if rumble:
            rumble.set_loop(True)
            rumble.set_volume(0.25)
            rumble.play()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.paused:
            self.ui.show_prompt("Paused - Esc to resume")
        else:
            self.ui.show_prompt("")

    def update(self, task) -> int:
        dt = globalClock.get_dt()
        if self.paused:
            return task.cont

        self.handle_mouse_look()
        self.player.update(dt)
        self.world.do_physics(dt, 4, 1 / 120)
        self.door.update()
        self.lighting.update(dt)
        self.ui.update(dt)

        self.check_door_interaction()

        return task.cont

    def handle_mouse_look(self) -> None:
        if not self.win.has_pointer(0):
            return
        pointer = self.win.get_pointer(0)
        dx = pointer.get_x() - self.base_mouse_x
        dy = pointer.get_y() - self.base_mouse_y
        if dx != 0 or dy != 0:
            self.player.apply_mouse_look(dx, dy)
            self.win.move_pointer(0, int(self.base_mouse_x), int(self.base_mouse_y))

    def check_door_interaction(self) -> None:
        door_pos = self.door.root.get_pos(self.render)
        player_pos = self.player.node.get_pos(self.render)
        distance = (door_pos - player_pos).length()
        if distance < 2.3:
            self.ui.show_prompt("E — interact")
            if self.player.input_state.interact:
                result = self.door.try_interact()
                if result == "Locked":
                    self.ui.show_locked()
        else:
            self.ui.show_prompt("")

    def generate_assets(self) -> None:
        TEXTURE_DIR.mkdir(parents=True, exist_ok=True)
        SFX_DIR.mkdir(parents=True, exist_ok=True)

        if Image is None:
            print("Pillow is not available. Procedural textures will not be generated.")
            return

        self.generate_texture_wall()
        self.generate_texture_carpet()
        self.generate_texture_ceiling()
        self.generate_texture_door()
        self.generate_sfx()

    def generate_texture_wall(self) -> None:
        path = TEXTURE_DIR / "wall.png"
        if path.exists():
            return
        img = Image.new("RGB", (512, 512), (55, 24, 20))
        draw = ImageDraw.Draw(img)
        for _ in range(2000):
            x = random.randint(0, 511)
            y = random.randint(0, 511)
            color = (random.randint(50, 70), random.randint(20, 30), random.randint(18, 25))
            draw.point((x, y), fill=color)
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        img.save(path)

    def generate_texture_carpet(self) -> None:
        path = TEXTURE_DIR / "carpet.png"
        if path.exists():
            return
        img = Image.new("RGB", (512, 512), (180, 170, 140))
        draw = ImageDraw.Draw(img)
        for y in range(0, 512, 32):
            for x in range(0, 512, 32):
                if (x // 32 + y // 32) % 2 == 0:
                    draw.rectangle([x, y, x + 31, y + 31], fill=(170, 160, 130))
        for i in range(0, 512, 64):
            draw.rectangle([i, 0, i + 2, 511], fill=(150, 140, 120))
            draw.rectangle([0, i, 511, i + 2], fill=(150, 140, 120))
        img = img.filter(ImageFilter.GaussianBlur(0.4))
        img.save(path)

    def generate_texture_ceiling(self) -> None:
        path = TEXTURE_DIR / "ceiling.png"
        if path.exists():
            return
        img = Image.new("RGB", (256, 256), (70, 65, 60))
        draw = ImageDraw.Draw(img)
        for _ in range(800):
            x = random.randint(0, 255)
            y = random.randint(0, 255)
            color = (random.randint(60, 80), random.randint(55, 70), random.randint(50, 65))
            draw.point((x, y), fill=color)
        img = img.filter(ImageFilter.GaussianBlur(0.8))
        img.save(path)

    def generate_texture_door(self) -> None:
        path = TEXTURE_DIR / "door.png"
        if path.exists():
            return
        img = Image.new("RGB", (256, 512), (85, 45, 30))
        draw = ImageDraw.Draw(img)
        for y in range(0, 512, 64):
            draw.rectangle([10, y + 10, 246, y + 54], outline=(110, 70, 50), width=2)
        img = img.filter(ImageFilter.GaussianBlur(0.4))
        img.save(path)

    def generate_sfx(self) -> None:
        self.generate_tone(SFX_DIR / "hum.wav", 110.0, 3.0, 0.2)
        self.generate_tone(SFX_DIR / "rumble.wav", 60.0, 3.0, 0.2)
        self.generate_tone(SFX_DIR / "locked.wav", 220.0, 0.5, 0.4)

    def generate_tone(self, path: Path, freq: float, duration: float, volume: float) -> None:
        if path.exists():
            return
        sample_rate = 22050
        frames = int(sample_rate * duration)
        with wave.open(str(path), "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            for i in range(frames):
                sample = volume * math.sin(2 * math.pi * freq * (i / sample_rate))
                value = int(sample * 32767)
                wav_file.writeframesraw(value.to_bytes(2, byteorder="little", signed=True))


if __name__ == "__main__":
    app = CorridorHorrorApp()
    app.run()
