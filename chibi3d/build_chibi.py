"""3D version of the chibi cat-boy PNGTuber, sculpted procedurally in Blender.

Reuses the SDF sculpting helpers from cat/build_cat.py.
Usage: python chibi3d/build_chibi.py [--out chibi3d/out] [--turntable]
"""
import argparse
import math
import os
import sys

import bpy  # must come before mathutils
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "cat"))
import build_cat as bc  # noqa: E402

from build_cat import ellipsoid, round_cone, smax, smin, smoothstep, srgb_to_linear  # noqa: E402

HAIR = (1.00, 0.955, 0.89)
HAIR_TIP = (0.97, 0.60, 0.25)
STREAK = (0.96, 0.56, 0.20)
EAR_INNER = (1.00, 0.80, 0.78)
SKIN = (1.00, 0.925, 0.86)
BLUSH = (1.00, 0.62, 0.62)
SHIRT = (1.00, 1.00, 1.00)
COLLAR = (0.96, 0.58, 0.23)
BOW = (0.18, 0.70, 0.64)
BASE_Z = -1.60


def parts(X, Y, Z):
    P = (np.abs(X), Y, Z)
    # head and neck (skin)
    skin = ellipsoid(P, (0, 0, 0), (0.80, 0.76, 0.78))
    skin = smin(skin, ellipsoid(P, (0, -0.10, -0.30), (0.64, 0.60, 0.48)), 0.25)
    skin = smin(skin, round_cone(P, (0, 0.05, -0.60), (0, 0.05, -1.05), 0.17, 0.17), 0.05)

    # hair: a cap opened at the face, plus fringe, side locks and back tufts
    cap = ellipsoid(P, (0, 0.08, 0.12), (0.95, 0.93, 0.90))
    face_open = ellipsoid(P, (0, -0.95, -0.34), (0.64, 0.78, 0.64))
    hair = smax(cap, -face_open, 0.04)
    locks = [
        ((0.00, -0.68, 0.48), (0.03, -0.815, 0.00), 0.22, 0.03),
        ((0.27, -0.62, 0.46), (0.33, -0.76, 0.13), 0.21, 0.03),
        ((0.50, -0.46, 0.40), (0.60, -0.60, -0.04), 0.21, 0.03),
        ((0.74, -0.28, 0.05), (0.71, -0.42, -0.76), 0.17, 0.03),
        ((0.78, -0.02, -0.25), (1.08, -0.08, -0.74), 0.27, 0.04),
        ((0.62, 0.32, -0.38), (1.00, 0.30, -0.98), 0.31, 0.04),
        ((0.32, 0.62, -0.48), (0.48, 0.80, -1.08), 0.33, 0.04),
        ((0.00, 0.72, -0.48), (0.00, 0.90, -1.02), 0.31, 0.04),
        # ahoge
        ((0.00, -0.12, 0.96), (0.07, -0.24, 1.30), 0.075, 0.05),
        ((0.07, -0.24, 1.30), (0.24, -0.26, 1.20), 0.05, 0.025),
    ]
    for a, b, r1, r2 in locks:
        hair = smin(hair, round_cone(P, a, b, r1, r2), 0.06)

    ear = round_cone(P, (0.46, 0.10, 0.72), (0.76, 0.06, 1.46), 0.31, 0.04, 0.55)
    carve = round_cone(P, (0.50, -0.11, 0.86), (0.74, -0.09, 1.33), 0.20, 0.02, 0.45)
    carve = smax(carve, 0.04 - cap, 0.05)

    body = ellipsoid(P, (0, 0.05, -1.42), (0.44, 0.31, 0.46))
    return {"skin": skin, "hair": hair, "ear": ear, "carve": carve, "body": body, "cap": cap}


def chibi_sdf(X, Y, Z, parts_too=False):
    p = parts(X, Y, Z)
    top = smax(smin(p["hair"], p["ear"], 0.07), -p["carve"], 0.035)
    d = smin(p["skin"], top, 0.012)
    d = smin(d, p["body"], 0.03)
    d = np.maximum(d, BASE_Z - Z)
    return (d, p) if parts_too else d


def skin_sdf(X, Y, Z):
    return parts(X, Y, Z)["skin"]


def colours(co):
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    ax = np.abs(x)
    p = parts(x, y, z)
    n = len(co)
    col = np.tile(srgb_to_linear(SKIN), (n, 1))

    def paint(colour, mask):
        nonlocal col
        m = np.clip(np.asarray(mask, dtype=float), 0, 1)[:, None]
        col = col * (1 - m) + srgb_to_linear(colour)[None, :] * m

    front = smoothstep(0.0, -0.2, y)
    blush = 1 - smoothstep(0.5, 1.0, np.sqrt(((ax - 0.43) / 0.15) ** 2 + ((z + 0.34) / 0.08) ** 2))
    paint(BLUSH, 0.6 * blush * front)

    top = np.minimum(p["hair"], p["ear"])
    is_top = top < p["skin"] + 0.004
    hair_col = np.tile(srgb_to_linear(HAIR), (n, 1))
    tip = smoothstep(-0.25, -0.95, z)[:, None]
    hair_col = hair_col * (1 - tip) + srgb_to_linear(HAIR_TIP)[None, :] * tip
    streak = (1 - smoothstep(0.13, 0.15, np.abs(x - 0.27))) * smoothstep(0.35, 0.15, y) * (z > 0.05)
    streak = np.maximum(streak, (z > 1.12) * 1.0)[:, None]          # ahoge tip
    hair_col = hair_col * (1 - streak) + srgb_to_linear(STREAK)[None, :] * streak
    is_ear = (p["ear"] < p["hair"] + 0.01) & (z > 0.80)
    hair_col[is_ear] = srgb_to_linear(STREAK)
    inner = (1 - smoothstep(0.010, 0.028, p["carve"]))[:, None]
    hair_col = hair_col * (1 - inner) + srgb_to_linear(EAR_INNER)[None, :] * inner
    col[is_top] = hair_col[is_top]

    is_body = (p["body"] < np.minimum(p["skin"], top) + 0.004) & (z < -0.95)
    body_col = np.tile(srgb_to_linear(SHIRT), (n, 1))
    collar = (smoothstep(-1.20, -1.17, z))[:, None]
    body_col = body_col * (1 - collar) + srgb_to_linear(COLLAR)[None, :] * collar
    col[is_body] = body_col[is_body]
    return np.concatenate([col, np.ones((n, 1))], axis=1).astype(np.float32)


def build_eyes(root, mats, x=0.31, z=-0.13, radii=(0.20, 0.085, 0.235)):
    eye_mesh = bc.ellipsoid_mesh("Eye", radii, uv=True)
    eye_mesh.materials.append(mats["eye"])
    rim_mesh = bc.ellipsoid_mesh("EyeLiner", (radii[0] * 1.09, radii[1], radii[2] * 1.05))
    rim_mesh.materials.append(mats["line"])
    for side, name in ((1, "L"), (-1, "R")):
        p, nrm = bc.surface_point(side * x, z)
        fwd = (Vector((0, -1, 0)) * 0.5 + nrm * 0.5).normalized()
        y_axis = -fwd
        x_axis = y_axis.cross(Vector((0, 0, 1))).normalized()
        z_axis = x_axis.cross(y_axis).normalized()
        rot = Matrix((x_axis, y_axis, z_axis)).transposed().to_4x4()
        tilt = Matrix.Rotation(math.radians(-5 * side), 4, "Y")
        centre = p - fwd * (radii[1] - 0.026)
        eye = bc.new_object(f"Eye.{name}", eye_mesh, root)
        eye.matrix_local = Matrix.Translation(centre) @ rot @ tilt
        rim = bc.new_object(f"EyeLiner.{name}", rim_mesh, root)
        rim.matrix_local = Matrix.Translation(centre - fwd * 0.012 + z_axis * 0.018) @ rot @ tilt


def build_mouth(root, mat, mz=-0.46, r=0.05):
    for side in (1, -1):
        angles = np.linspace(math.pi, 2 * math.pi + 0.5, 18)
        pts = []
        for a in angles:
            p, nrm = bc.surface_point(side * (r + r * math.cos(a)), mz + r * math.sin(a))
            pts.append(p + nrm * 0.002)
        radii = [1.0] * (len(pts) - 4) + [0.8, 0.6, 0.4, 0.2]
        bc.curve_object(f"Mouth.{'L' if side > 0 else 'R'}", pts, radii, 0.009, mat, root)


def build_bow(root, mats):
    centre = Vector((0, -0.285, -1.08))
    out = []
    for side in (1, -1):
        m = bc.ellipsoid_mesh("BowWing", (0.20, 0.065, 0.135))
        for v in m.vertices:                      # pinch towards the knot
            t = min(max((v.co.x + 0.20) / 0.40, 0.0), 1.0)
            v.co.z *= 0.35 + 0.65 * t
            v.co.y *= 0.55 + 0.45 * t
        m.materials.append(mats["bow"])
        o = bc.new_object(f"Bow.{'L' if side > 0 else 'R'}", m, root)
        o.matrix_local = Matrix.Translation(centre) @ Matrix.Scale(side, 4, (1, 0, 0)) @ Matrix.Translation((0.19, 0, 0)) @ Matrix.Rotation(math.radians(-10), 4, "Y")
        out.append(o)
    k = bc.ellipsoid_mesh("BowKnot", (0.07, 0.07, 0.08))
    k.materials.append(mats["bow"])
    ko = bc.new_object("BowKnot", k, root)
    ko.location = centre + Vector((0, -0.02, 0))
    b = bc.ellipsoid_mesh("Bell", (0.085, 0.085, 0.085))
    b.materials.append(mats["bell"])
    bo = bc.new_object("Bell", b, root)
    bo.location = centre + Vector((0, -0.05, -0.15))
    s = bc.ellipsoid_mesh("BellSlit", (0.012, 0.05, 0.06))
    s.materials.append(mats["line"])
    so = bc.new_object("BellSlit", s, root)
    so.location = bo.location + Vector((0, -0.05, -0.035))
    so.rotation_euler = (math.radians(-55), 0, 0)
    return out + [ko, bo]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--turntable", action="store_true")
    ap.add_argument("--size", type=int, default=1200)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--views", default="front,three_quarter,side,back")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    bc.BASE_Z = BASE_Z
    bc.fur_colours = colours
    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = bpy.data.objects.new("Chibi", None)
    bpy.context.scene.collection.objects.link(root)

    iris = bc.eye_texture()
    iris.filepath_raw = os.path.join(args.out, "eye_iris.png")
    iris.file_format = "PNG"
    iris.save()
    iris.pack()
    mats = {
        "eye": bc.make_material("Eye", colour=bc.IRIS_BOTTOM, image=iris, roughness=0.25),
        "line": bc.make_material("Line", colour=bc.LINE, roughness=0.9),
        "bow": bc.make_material("Bow", colour=BOW, roughness=0.6),
        "bell": bc.make_material("Bell", colour=bc.BELL, metallic=1.0, roughness=0.3),
    }

    bc.cat_sdf = chibi_sdf
    body = bc.build_fur(root)
    body.name = "Body"
    bc.cat_sdf = skin_sdf           # place face features on the skin, under the fringe
    build_eyes(root, mats)
    build_mouth(root, mats["line"])
    bc.cat_sdf = chibi_sdf
    bow = build_bow(root, mats)

    glb = os.path.join(args.out, "chibi_cat.glb")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", export_apply=False,
                              export_vertex_color="ACTIVE", export_all_vertex_colors=False, export_yup=True)
    print("exported", glb, f"{os.path.getsize(glb) / 1e6:.1f} MB", flush=True)

    outline = bc.outline_material()
    bc.add_outline(body, outline, 0.011)
    for o in bow:
        bc.add_outline(o, outline, 0.008)
    bc.add_toon_output(body.data.materials[0])
    bc.add_toon_output(mats["eye"], unlit=True)
    bc.add_toon_output(mats["line"], unlit=True)
    bc.add_toon_output(mats["bow"])
    mats["bell"].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.0
    bc.add_toon_output(mats["bell"], gloss=True)

    rig = bc.setup_render(root, args.size, args.samples)
    rig.location = (0, 0, -0.15)
    blend = os.path.join(args.out, "chibi_cat.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    print("saved", blend, flush=True)

    views = {"front": (0, 0), "three_quarter": (35, -8), "side": (90, 0), "back": (155, -8)}
    for name in [v for v in args.views.split(",") if v]:
        bc.render_view(rig, *views[name], os.path.join(args.out, f"render_{name}.png"))
    if args.turntable:
        sc = bpy.context.scene
        sc.render.resolution_x = sc.render.resolution_y = 600
        sc.cycles.samples = 32
        for i in range(48):
            bc.render_view(rig, 360.0 * i / 48, -6, os.path.join(args.out, "turntable", f"{i:03d}.png"))


if __name__ == "__main__":
    main()
