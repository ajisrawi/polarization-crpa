"""
Assemble and render the rev B (compact TMM3) 12-element CRPA array in Blender (headless).

    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup \
        --python hardware/antenna_tmm/render3d/build_array_scene.py

Stack (mm, plate top = z 0): brass posts 8 | feed RO4350B 0.762 | TMM3 A1 8.89 (feed disks) |
TMM3 A2 0.762 (patch A) | TMM3 B 3.175 (patch B) | TMM3 C 7.62 (patch C). Slabs are bonded.
"""
import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
ANT = HERE.parent
bpy.ops.wm.read_factory_settings(use_empty=True)
MM = 0.001

P = json.loads((ANT / "design_params.json").read_text())
T = P["substrates"]["slab_thickness_mm"]
PLATE_T = 3.0
POST_H = 8.0
FEED_T = 0.762
Z_FEED = POST_H
Z_A1 = Z_FEED + FEED_T
Z_A2 = Z_A1 + T["A1"]
Z_B = Z_A2 + T["A2"]
Z_C = Z_B + T["B"]
Z_TOP = Z_C + T["C"]
POST = P["board"]["post_holes_mm"]
POSTS = [(sx * POST, sy * POST) for sx in (-1, 0, 1) for sy in (-1, 0, 1) if (sx, sy) != (0, 0)]
PROBE_OFF = 10.0
SMA_XY = (-36.0, -36.0)            # KiCad (-36, 36), y flipped
TILT_DEG = 80.0
FACE_H = 110.0


def material(name, color, metallic=0.0, roughness=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return m


ALU = material("aluminium", (0.78, 0.79, 0.80), 1.0, 0.32)
BRASS = material("brass", (0.86, 0.68, 0.33), 1.0, 0.25)
GOLD = material("gold", (1.0, 0.77, 0.34), 1.0, 0.2)
COPPER = material("copper", (0.95, 0.55, 0.38), 1.0, 0.3)
CERAMIC = material("TMM3 ceramic", (0.90, 0.87, 0.80), 0.0, 0.55)


def new_collection(name, hide=False):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    if hide:
        bpy.context.view_layer.layer_collection.children[name].exclude = True
    return col


def link_only(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def cylinder(name, r, z0, z1, xy, mat, col, verts=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r * MM, depth=(z1 - z0) * MM,
                                        location=(xy[0] * MM, xy[1] * MM, (z0 + z1) / 2 * MM))
    ob = bpy.context.active_object
    ob.name = name
    ob.data.materials.append(mat)
    link_only(ob, col)
    return ob


def box(name, size, center, mat, col):
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(c * MM for c in center))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = tuple(s * MM for s in size)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(mat)
    link_only(ob, col)
    return ob


def import_glb(name, col, z_mm, body_mat=None, body_thickness=None, all_mat=None):
    """Import a KiCad GLB; optionally recolour the laminate body (the full-thickness mesh)."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(HERE / f"{name}.glb"))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(f"{name}_root", None)
    col.objects.link(root)
    for ob in new:
        link_only(ob, col)
        if ob.parent is None:
            ob.parent = root
        if ob.type != "MESH":
            continue
        if all_mat:
            ob.data.materials.clear()
            ob.data.materials.append(all_mat)
        elif body_mat and body_thickness:
            # the laminate body is the only mesh spanning the full slab outline and thickness
            # (plated feed-disk barrels are full-thickness too, but tiny in x/y)
            pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
            span = lambda i: max(p[i] for p in pts) - min(p[i] for p in pts)
            if abs(span(2) - body_thickness * MM) < 0.35 * MM and span(0) > 0.07:
                ob.data.materials.clear()
                ob.data.materials.append(body_mat)
    root.location = (0, 0, z_mm * MM)
    return root


def element_template(name, feed, a1, probes):
    col = new_collection(name, hide=True)
    import_glb(feed, col, Z_FEED)
    import_glb(a1, col, Z_A1, CERAMIC, T["A1"])
    import_glb("slab_A2", col, Z_A2, CERAMIC, T["A2"])
    import_glb("slab_B", col, Z_B, CERAMIC, T["B"])
    import_glb("slab_C", col, Z_C, CERAMIC, T["C"])
    for i, xy in enumerate(probes):
        cylinder(f"probe_{i}", 0.645, Z_FEED - 0.5, Z_A2 + 0.02, xy, COPPER, col, 16)
    for xy in POSTS:
        cylinder("brass_post", 2.75, 0.0, Z_FEED, xy, BRASS, col, 6)
        cylinder("screw_head", 2.75, Z_FEED + FEED_T, Z_FEED + FEED_T + 2.0, xy, STEEL, col, 24)
    box("sma_flange", (6.35, 6.35, 1.6), (SMA_XY[0], SMA_XY[1], Z_FEED - 0.8), GOLD, col)
    cylinder("sma_body", 3.15, -PLATE_T - 6.0, Z_FEED - 1.6, SMA_XY, GOLD, col)
    return col


STEEL = material("steel", (0.62, 0.63, 0.65), 1.0, 0.4)


def monopole_template():
    col = new_collection("ELEM_MONOPOLE", hide=True)
    cylinder("monopole_rod", 3.175, 0.0, 51.0, (0, 0), BRASS, col)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=3.175 * MM, location=(0, 0, 51.0 * MM))
    cap = bpy.context.active_object
    cap.data.materials.append(BRASS)
    link_only(cap, col)
    cylinder("bulkhead_nut", 5.0, 0.0, 2.5, (0, 0), GOLD, col, 6)
    cylinder("bulkhead_body", 3.15, -PLATE_T - 8.0, 0.0, (0, 0), GOLD, col)
    return col


def instance(col, name, matrix, parent):
    ob = bpy.data.objects.new(name, None)
    ob.instance_type = "COLLECTION"
    ob.instance_collection = col
    ob.matrix_world = matrix
    parent.objects.link(ob)
    return ob


def probe_xy(angle):
    a = math.radians(angle)
    return (PROBE_OFF * math.cos(a), PROBE_OFF * math.sin(a))


def build():
    circ = element_template("ELEM_CIRC", "feed_circular", "slab_A1_circ", [probe_xy(0), probe_xy(90)])
    lin = {a: element_template(f"ELEM_LIN_{a:03d}", f"feed_linear_{a:03d}", f"slab_A1_lin{a:03d}",
                               [probe_xy(a)]) for a in (0, 60, 120)}
    mono = monopole_template()
    array = new_collection("CRPA_ARRAY")
    import_glb("array_plate", array, -PLATE_T, all_mat=ALU)

    elems = json.loads((ANT / "array_plate" / "element_positions.json").read_text())
    rot_x = Matrix.Rotation(math.radians(-TILT_DEG), 4, "X")
    edge = rot_x @ Vector((0, FACE_H / 2 * MM, -0.003, 1))
    tilted = [e for e in elems if e["kind"] == "L_tilted"]
    for k, e in enumerate(elems):
        x, y = e["x"] * MM, -e["y"] * MM
        if e["kind"] == "L_tilted":
            pos = Vector((x, y - 0.0075, 0.003 - edge.z))
            instance(circ, f"elem_{k}_tilted", Matrix.Translation(pos) @ rot_x, array)
        else:
            tmpl = lin[int(e["pol_deg"])] if e["kind"] == "H" else {"R": circ, "V": mono}[e["kind"]]
            instance(tmpl, f"elem_{k}_{e['kind']}", Matrix.Translation((x, y, 0)), array)
    ys = -tilted[0]["y"] * MM - 0.0075
    span = (max(e["x"] for e in tilted) - min(e["x"] for e in tilted)) + 110.0
    face = box("bracket_face", (span, FACE_H, 3.0), (0, 0, -1.5), ALU, array)
    face.matrix_world = Matrix.Translation((0, ys, 0.003 - edge.z)) @ rot_x
    box("bracket_flange", (span, 40.0, 3.0), (0, (ys + edge.y - 0.02) / MM, 1.5), ALU, array)

    # exploded single element, 1 m to the side
    expl = new_collection("EXPLODED")
    gap = 18.0
    layers = [("feed_circular", Z_FEED, None, None), ("slab_A1_circ", Z_A1 + gap, CERAMIC, T["A1"]),
              ("slab_A2", Z_A2 + 2 * gap, CERAMIC, T["A2"]), ("slab_B", Z_B + 3 * gap, CERAMIC, T["B"]),
              ("slab_C", Z_C + 4 * gap, CERAMIC, T["C"])]
    for glb, z, mat, th in layers:
        r = import_glb(glb, expl, z, mat, th)
        r.location.x += 1.0
    for xy in (probe_xy(0), probe_xy(90)):
        cylinder("x_probe", 0.645, Z_FEED - 0.5, Z_A2 + gap, (1000.0 + xy[0], xy[1]), COPPER, expl, 16)
    for xy in POSTS:
        cylinder("x_post", 2.75, -6.0, Z_FEED, (1000.0 + xy[0], xy[1]), BRASS, expl, 6)
    box("x_sma", (6.35, 6.35, 1.6), (1000.0 + SMA_XY[0], SMA_XY[1], Z_FEED - 0.8), GOLD, expl)
    cylinder("x_sma_body", 3.15, Z_FEED - 14.0, Z_FEED - 1.6, (1000.0 + SMA_XY[0], SMA_XY[1]), GOLD, expl)


def setup(scene):
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.93, 0.95, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scene.world = world
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3.5
    sun.angle = math.radians(8)
    so = bpy.data.objects.new("sun", sun)
    so.rotation_euler = (math.radians(40), math.radians(15), math.radians(35))
    scene.collection.objects.link(so)
    fill = bpy.data.lights.new("fill", "AREA")
    fill.energy = 300
    fill.size = 2.0
    fo = bpy.data.objects.new("fill", fill)
    fo.location = (-0.9, -1.0, 1.2)
    fo.rotation_euler = (math.radians(50), 0, math.radians(-40))
    scene.collection.objects.link(fo)
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -0.012))
    bpy.context.active_object.data.materials.append(material("floor", (0.85, 0.86, 0.88), 0, 0.9))
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = "AgX"


def camera(scene, name, loc, target, lens=50, ortho=None):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.clip_start = 0.01
    if ortho:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho
    ob = bpy.data.objects.new(name, cam)
    scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def render(scene, cam, out, res=(1800, 1150), denoise=True, samples=48):
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.cycles.use_denoising = denoise
    scene.cycles.samples = samples
    scene.render.filepath = str(HERE / out)
    bpy.ops.render.render(write_still=True)
    print("rendered", out, flush=True)


def main():
    scene = bpy.context.scene
    build()
    setup(scene)
    c = (0.0, 0.03, 0.02)
    views = [("array_iso.png", camera(scene, "iso", (0.78, -0.86, 0.70), c, 45), {}),
             ("array_jammer_side.png", camera(scene, "jam", (0.30, 1.02, 0.26), (0, 0.05, 0.04), 45), {}),
             ("array_top.png", camera(scene, "top", (0, 0.04, 2.0), (0, 0.04, 0), ortho=0.56), {}),
             ("element_exploded.png", camera(scene, "expl", (1.26, -0.26, 0.21), (1.0, 0.0, 0.05), 50),
              {"res": (1400, 1050), "denoise": False, "samples": 160})]
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "crpa_array_revB.blend"))
    import sys
    only = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for out, cam, kw in views:
        if not only or out in only:
            render(scene, cam, out, **kw)
    if only:
        return
    for ob in bpy.data.objects:
        ob.select_set(False)
    objs = list(bpy.data.collections["CRPA_ARRAY"].objects)
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.duplicates_make_real()
    bpy.ops.export_scene.gltf(filepath=str(HERE / "crpa_array_revB.glb"), use_selection=True, export_format="GLB")
    print("exported crpa_array_revB.glb", flush=True)


main()
