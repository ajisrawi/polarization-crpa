"""
Assemble and render the full 12-element CRPA array in Blender (headless).

    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \
        --python hardware/antenna/render3d/build_array_scene.py

Inputs : render3d/*.glb (exported from the KiCad boards) and array_plate/element_positions.json
Outputs: render3d/array_iso.png, array_jammer_side.png, array_top.png, element_exploded.png,
         render3d/crpa_array.blend, render3d/crpa_array.glb

Geometry (mm, plate top = z 0): standoff 8 | feed board 0.762 | air 9 | lower patch 0.8 | air 6 |
upper patch 0.8. KiCad y (down) becomes model y (up = north = jammer side).
"""
import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
bpy.ops.wm.read_factory_settings(use_empty=True)   # start empty, before any datablock is created
ANT = HERE.parent
MM = 0.001

PLATE_T = 3.0
STANDOFF_1 = 8.0
FEED_T = 0.762
AIR_1 = 9.0
PATCH_T = 0.8
AIR_2 = 6.0
Z_FEED = STANDOFF_1
Z_LOWER = Z_FEED + FEED_T + AIR_1
Z_UPPER = Z_LOWER + PATCH_T + AIR_2
HOLE = 58.0
PROBE_OFF = json.loads((ANT / "design_params.json").read_text())["patch"]["probe"]["offset_from_centre_mm"]
SMA_XY = (-54.0, -54.0)          # KiCad (-54, 54) with y flipped
TILT_DEG = 80.0                  # module plane from horizontal -> boresight elevation 10 deg


# --------------------------------------------------------------------------
# Scene helpers
# --------------------------------------------------------------------------

def material(name, color, metallic=0.0, roughness=0.5, transmission=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return m


ALU = material("aluminium", (0.78, 0.79, 0.80), metallic=1.0, roughness=0.32)
BRASS = material("brass", (0.86, 0.68, 0.33), metallic=1.0, roughness=0.25)
GOLD = material("gold", (1.0, 0.77, 0.34), metallic=1.0, roughness=0.2)
COPPER = material("copper", (0.95, 0.55, 0.38), metallic=1.0, roughness=0.3)
NYLON = material("nylon", (0.93, 0.92, 0.88), roughness=0.6)
STEEL = material("steel", (0.62, 0.63, 0.65), metallic=1.0, roughness=0.4)


def new_collection(name, parent=None, hide=False):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    if hide:
        lc = bpy.context.view_layer.layer_collection.children.get(name)
        if lc:
            lc.exclude = True
    return col


def link_only(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def cylinder(name, r, z0, z1, xy=(0, 0), mat=None, col=None, verts=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r * MM, depth=(z1 - z0) * MM,
                                        location=(xy[0] * MM, xy[1] * MM, (z0 + z1) / 2 * MM))
    ob = bpy.context.active_object
    ob.name = name
    if mat:
        ob.data.materials.append(mat)
    if col:
        link_only(ob, col)
    return ob


def box(name, size, center, mat=None, col=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(c * MM for c in center))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = tuple(s * MM for s in size)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        ob.data.materials.append(mat)
    if col:
        link_only(ob, col)
    return ob


def import_glb(name, col, z_mm=0.0, mat_override=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(HERE / f"{name}.glb"))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(f"{name}_root", None)
    col.objects.link(root)
    for ob in new:
        link_only(ob, col)
        if ob.parent is None:
            ob.parent = root
        if mat_override and ob.type == "MESH":
            ob.data.materials.clear()
            ob.data.materials.append(mat_override)
    root.location = (0, 0, z_mm * MM)
    return root


# --------------------------------------------------------------------------
# Element templates (each in its own hidden collection, instanced on the plate)
# --------------------------------------------------------------------------

def sma(col, z_top):
    """Vertical SMA under the feed board: square flange, body through the plate, hex nut."""
    box("sma_flange", (6.35, 6.35, 1.6), (SMA_XY[0], SMA_XY[1], z_top - 0.8), GOLD, col)
    cylinder("sma_body", 3.15, -PLATE_T - 6.0, z_top - 1.6, SMA_XY, GOLD, col)
    cylinder("sma_nut", 4.6, -PLATE_T - 3.2, -PLATE_T, SMA_XY, GOLD, col, verts=6)


def standoffs(col, ranges):
    for k, (z0, z1) in enumerate(ranges):
        for x, y in ((0, HOLE), (HOLE, 0), (0, -HOLE), (-HOLE, 0)):
            cylinder(f"standoff_{k}", 2.75, z0, z1, (x, y), NYLON, col, verts=6)
    for x, y in ((0, HOLE), (HOLE, 0), (0, -HOLE), (-HOLE, 0)):
        cylinder("screw_head", 2.75, Z_UPPER + PATCH_T, Z_UPPER + PATCH_T + 2.0, (x, y), NYLON, col)


def element_template(name, feed, probes):
    col = new_collection(name, hide=True)
    import_glb(feed, col, Z_FEED)
    import_glb("patch_lower", col, Z_LOWER)
    import_glb("patch_upper", col, Z_UPPER)
    for i, xy in enumerate(probes):
        cylinder(f"probe_{i}", 0.645, Z_FEED - 0.5, Z_LOWER + PATCH_T + 0.6, xy, COPPER, col, verts=16)
    standoffs(col, [(0.0, Z_FEED), (Z_FEED + FEED_T, Z_LOWER), (Z_LOWER + PATCH_T, Z_UPPER)])
    sma(col, Z_FEED)
    return col


def monopole_template():
    col = new_collection("ELEM_MONOPOLE", hide=True)
    cylinder("monopole_rod", 3.175, 0.0, 51.0, (0, 0), BRASS, col)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=3.175 * MM, location=(0, 0, 51.0 * MM))
    cap = bpy.context.active_object
    cap.data.materials.append(BRASS)
    link_only(cap, col)
    cylinder("bulkhead_nut", 5.0, 0.0, 2.5, (0, 0), GOLD, col, verts=6)
    cylinder("bulkhead_body", 3.15, -PLATE_T - 8.0, 0.0, (0, 0), GOLD, col)
    return col


def instance(col, name, matrix, parent_col):
    ob = bpy.data.objects.new(name, None)
    ob.instance_type = "COLLECTION"
    ob.instance_collection = col
    ob.matrix_world = matrix
    parent_col.objects.link(ob)
    return ob


# --------------------------------------------------------------------------
# Build the array
# --------------------------------------------------------------------------

def build():
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"

    circ = element_template("ELEM_CIRCULAR", "feed_circular",
                            [(PROBE_OFF, 0.0), (0.0, PROBE_OFF)])
    lin = {a: element_template(f"ELEM_LINEAR_{a:03d}", f"feed_linear_{a:03d}",
                               [(PROBE_OFF * math.cos(math.radians(a)), PROBE_OFF * math.sin(math.radians(a)))])
           for a in (0, 60, 120)}
    mono = monopole_template()

    array = new_collection("CRPA_ARRAY")
    plate = import_glb("array_plate", array, -PLATE_T, mat_override=ALU)
    plate.name = "array_plate"

    elems = json.loads((ANT / "array_plate" / "element_positions.json").read_text())
    rot_x = Matrix.Rotation(math.radians(-TILT_DEG), 4, "X")
    edge = rot_x @ Vector((0, 0.075, -0.003, 1))      # bottom edge of a 150 mm tall face
    tilted = [e for e in elems if e["kind"] == "L_tilted"]
    for k, e in enumerate(elems):
        x, y = e["x"] * MM, -e["y"] * MM
        if e["kind"] == "L_tilted":
            pos = Vector((x, y - 0.0075, 0.003 - edge.z))
            instance(circ, f"elem_{k}_LHCP_tilted", Matrix.Translation(pos) @ rot_x, array)
        else:
            m = Matrix.Translation((x, y, 0))
            tmpl = lin[int(e["pol_deg"])] if e["kind"] == "H" else {"R": circ, "V": mono}[e["kind"]]
            instance(tmpl, f"elem_{k}_{e['kind']}", m, array)

    # one continuous 80-degree bracket carries all three tilted modules
    ys = -tilted[0]["y"] * MM - 0.0075
    span = (max(e["x"] for e in tilted) - min(e["x"] for e in tilted)) + 140.0
    face = box("bracket_face", (span, 150.0, 3.0), (0, 0, -1.5), ALU, array)
    face.matrix_world = Matrix.Translation((0, ys, 0.003 - edge.z)) @ rot_x
    base_y = ys + edge.y
    box("bracket_flange", (span, 50.0, 3.0), (0, (base_y - 0.025) / MM, 1.5), ALU, array)

    # exploded single element, placed well away from the array
    expl = new_collection("EXPLODED")
    gap = 30.0
    for i, (glb, z) in enumerate((("feed_circular", Z_FEED), ("patch_lower", Z_LOWER + gap),
                                  ("patch_upper", Z_UPPER + 2 * gap))):
        r = import_glb(glb, expl, z)
        r.location.x += 1.0
    for i, xy in enumerate([(PROBE_OFF, 0.0), (0.0, PROBE_OFF)]):
        cylinder(f"x_probe_{i}", 0.645, Z_FEED - 0.5, Z_LOWER + gap + PATCH_T + 0.6,
                 (1000.0 + xy[0], xy[1]), COPPER, expl, verts=16)
    for x, y in ((0, HOLE), (HOLE, 0), (0, -HOLE), (-HOLE, 0)):
        cylinder("x_standoff_a", 2.75, Z_FEED + FEED_T, Z_LOWER, (1000.0 + x, y), NYLON, expl, verts=6)
        cylinder("x_standoff_b", 2.75, Z_LOWER + gap + PATCH_T, Z_UPPER + 2 * gap, (1000.0 + x, y), NYLON, expl, verts=6)
    box("x_sma_flange", (6.35, 6.35, 1.6), (1000.0 + SMA_XY[0], SMA_XY[1], Z_FEED - 0.8), GOLD, expl)
    cylinder("x_sma_body", 3.15, Z_FEED - 14.0, Z_FEED - 1.6, (1000.0 + SMA_XY[0], SMA_XY[1]), GOLD, expl)
    return scene


# --------------------------------------------------------------------------
# Lighting, cameras, rendering
# --------------------------------------------------------------------------

def setup_render(scene):
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.92, 0.93, 0.95, 1)
    bg.inputs["Strength"].default_value = 0.9
    scene.world = world
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3.5
    sun.angle = math.radians(8)
    so = bpy.data.objects.new("sun", sun)
    so.rotation_euler = (math.radians(40), math.radians(15), math.radians(35))
    scene.collection.objects.link(so)
    fill = bpy.data.lights.new("fill", "AREA")
    fill.energy = 400
    fill.size = 2.0
    fo = bpy.data.objects.new("fill", fill)
    fo.location = (-1.0, -1.2, 1.4)
    fo.rotation_euler = (math.radians(50), 0, math.radians(-40))
    scene.collection.objects.link(fo)
    # neutral floor so the array casts a soft shadow
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -0.012))
    floor = bpy.context.active_object
    floor.name = "floor"
    floor.data.materials.append(material("floor", (0.85, 0.86, 0.88), roughness=0.9))

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1150
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"


def camera(scene, name, loc, target, lens=50, ortho_scale=None):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.clip_start = 0.01
    cam.clip_end = 50
    if ortho_scale:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho_scale
    ob = bpy.data.objects.new(name, cam)
    scene.collection.objects.link(ob)
    ob.location = loc
    direction = Vector(target) - Vector(loc)
    ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return ob


def render(scene, cam, out, res=(1800, 1150)):
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = str(HERE / out)
    bpy.ops.render.render(write_still=True)
    print("rendered", out, flush=True)


def main():
    scene = build()
    setup_render(scene)
    centre = (0.0, 0.03, 0.02)
    views = [
        ("array_iso.png", camera(scene, "cam_iso", (0.95, -1.05, 0.85), centre, lens=45)),
        ("array_jammer_side.png", camera(scene, "cam_jammer", (0.35, 1.25, 0.32), (0.0, 0.05, 0.05), lens=45)),
        ("array_top.png", camera(scene, "cam_top", (0.0, 0.05, 2.0), (0.0, 0.05, 0.0), ortho_scale=0.72)),
        ("element_exploded.png", camera(scene, "cam_expl", (1.22, -0.21, 0.17), (1.0, 0.0, 0.045), lens=60)),
    ]
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "crpa_array.blend"))
    for out, cam in views:
        # the denoiser ran out of memory on the close-up: render it smaller, more samples
        if out == "element_exploded.png":
            scene.cycles.use_denoising = False
            scene.cycles.samples = 160
            render(scene, cam, out, (1400, 950))
        else:
            render(scene, cam, out)

    # GLB of the assembled array (instances realized) for any 3D viewer
    for ob in bpy.data.objects:
        ob.select_set(False)
    for ob in bpy.data.collections["CRPA_ARRAY"].objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.collections["CRPA_ARRAY"].objects[0]
    bpy.ops.object.duplicates_make_real()
    bpy.ops.export_scene.gltf(filepath=str(HERE / "crpa_array.glb"), use_selection=True,
                              export_format="GLB")
    print("exported crpa_array.glb", flush=True)


main()
