"""Procedurally sculpt an anime-style cat head bust in Blender.

The fur body is modelled as a signed distance field (smooth-blended ellipsoids
and cones), meshed with marching cubes, regularised with Blender's voxel
remesher and painted with vertex colours.  Eyes, nose, mouth, whiskers, collar
and bell are separate objects.

Usage:
    python cat/build_cat.py [--out cat/out] [--no-render] [--turntable]

Needs: bpy, numpy, scikit-image, pillow (see cat/requirements.txt).
"""
import argparse
import math
import os
import sys

import bpy  # must come before bmesh/mathutils
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from skimage import measure

# --------------------------------------------------------------------------
# Palette (sRGB) -- change these to recolour the cat.
# --------------------------------------------------------------------------
FUR = (0.98, 0.60, 0.26)
FUR_DARK = (0.86, 0.40, 0.13)      # tabby stripes
FUR_LIGHT = (1.00, 0.97, 0.92)     # muzzle, blaze, chest
EAR_INNER = (1.00, 0.70, 0.72)
BLUSH = (1.00, 0.55, 0.50)
NOSE = (0.98, 0.50, 0.55)
LINE = (0.24, 0.11, 0.09)          # mouth, eye liner, outline
WHISKER = (1.00, 1.00, 1.00)
IRIS_TOP = (0.02, 0.36, 0.34)
IRIS_BOTTOM = (0.50, 0.96, 0.52)
COLLAR = (0.86, 0.16, 0.22)
BELL = (1.00, 0.80, 0.20)
BACKGROUND = (0.72, 0.87, 0.93)

VOXEL = 0.0125          # marching-cubes cell size
REMESH_VOXEL = 0.016    # final quad size
BASE_Z = -1.72          # flat bottom of the bust


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin(c):
    return tuple(float(v) for v in srgb_to_linear(c))


# --------------------------------------------------------------------------
# Signed distance primitives (work on arrays of any shape)
# --------------------------------------------------------------------------
def ellipsoid(P, c, r):
    x, y, z = P[0] - c[0], P[1] - c[1], P[2] - c[2]
    k0 = np.sqrt((x / r[0]) ** 2 + (y / r[1]) ** 2 + (z / r[2]) ** 2)
    k1 = np.sqrt((x / r[0] ** 2) ** 2 + (y / r[1] ** 2) ** 2 + (z / r[2] ** 2) ** 2)
    return np.where(k1 < 1e-7, -min(r), k0 * (k0 - 1.0) / np.maximum(k1, 1e-7))


def round_cone(P, a, b, r1, r2, flat=1.0):
    """Cone with spherical caps from a (radius r1) to b (radius r2).

    flat < 1 squashes it front-to-back (along Y) around the a-b line.
    """
    px, py, pz = P[0] - a[0], (P[1] - a[1]) / flat, P[2] - a[2]
    bx, by, bz = b[0] - a[0], (b[1] - a[1]) / flat, b[2] - a[2]
    l2 = bx * bx + by * by + bz * bz
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    y = px * bx + py * by + pz * bz
    z = y - l2
    qx, qy, qz = px * l2 - bx * y, py * l2 - by * y, pz * l2 - bz * y
    x2 = qx * qx + qy * qy + qz * qz
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d = np.where(
        np.sign(z) * a2 * z2 > k,
        np.sqrt(x2 + z2) * il2 - r2,
        np.where(
            np.sign(y) * a2 * y2 < k,
            np.sqrt(x2 + y2) * il2 - r1,
            (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - r1,
        ),
    )
    return d * flat


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# --------------------------------------------------------------------------
# The cat
# --------------------------------------------------------------------------
def cat_sdf(X, Y, Z, parts=False):
    """Distance field of the fur body.  Symmetric in X."""
    P = (np.abs(X), Y, Z)

    # skull, cheeks, chin, muzzle
    core = ellipsoid(P, (0, 0, 0), (1.10, 0.96, 0.94))
    core = smin(core, ellipsoid(P, (0.62, -0.20, -0.34), (0.60, 0.58, 0.47)), 0.25)
    core = smin(core, ellipsoid(P, (0, -0.74, -0.58), (0.22, 0.17, 0.14)), 0.12)
    core = smin(core, ellipsoid(P, (0, -0.79, -0.37), (0.34, 0.19, 0.22)), 0.14)
    core = smin(core, ellipsoid(P, (0.13, -0.87, -0.38), (0.17, 0.12, 0.14)), 0.07)

    # cheek fluff
    tuft = round_cone(P, (0.84, -0.15, -0.18), (1.32, -0.04, -0.09), 0.30, 0.045, 0.6)
    tuft = smin(tuft, round_cone(P, (0.84, -0.15, -0.38), (1.34, -0.04, -0.43), 0.32, 0.045, 0.6), 0.08)
    tuft = smin(tuft, round_cone(P, (0.74, -0.15, -0.50), (1.15, -0.06, -0.77), 0.30, 0.045, 0.6), 0.08)
    # forehead tuft
    tuft = smin(tuft, round_cone(P, (0.0, -0.30, 0.80), (0.0, -0.54, 1.12), 0.20, 0.03), 0.05)
    tuft = smin(tuft, round_cone(P, (0.16, -0.28, 0.80), (0.31, -0.46, 1.01), 0.16, 0.03), 0.06)
    head = smin(core, tuft, 0.09)

    # ears, hollowed from the front
    ear = round_cone(P, (0.52, 0.08, 0.64), (0.84, 0.02, 1.50), 0.35, 0.045, 0.6)
    carve = round_cone(P, (0.57, -0.17, 0.80), (0.82, -0.15, 1.36), 0.23, 0.02, 0.45)
    carve = smax(carve, 0.04 - core, 0.05)          # never dig into the skull
    head = smin(head, ear, 0.08)
    head = smax(head, -carve, 0.04)

    # neck and shoulders, cut flat at the bottom
    body = round_cone(P, (0, 0.05, -0.60), (0, 0.05, -1.25), 0.34, 0.38)
    body = smin(body, ellipsoid(P, (0, 0.05, -1.66), (0.84, 0.50, 0.46)), 0.16)
    d = smin(head, body, 0.06)
    d = np.maximum(d, BASE_Z - Z)

    if parts:
        return d, {"core": core, "carve": carve, "ear": ear, "body": body, "head": head}
    return d


def sdf_grad(p, eps=2e-3):
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    g = np.stack(
        [
            cat_sdf(x + eps, y, z) - cat_sdf(x - eps, y, z),
            cat_sdf(x, y + eps, z) - cat_sdf(x, y - eps, z),
            cat_sdf(x, y, z + eps) - cat_sdf(x, y, z - eps),
        ],
        axis=1,
    )
    n = np.linalg.norm(g, axis=1, keepdims=True)
    return g / np.maximum(n, 1e-9)


def surface_point(x, z):
    """Front-most point of the fur surface at (x, z), and its normal."""
    ys = np.linspace(-1.6, 0.4, 4001)
    d = cat_sdf(np.full_like(ys, x), ys, np.full_like(ys, z))
    i = int(np.argmax(d < 0))
    y = ys[i - 1] + (ys[i] - ys[i - 1]) * d[i - 1] / (d[i - 1] - d[i])
    p = np.array([[x, y, z]])
    return Vector(p[0]), Vector(sdf_grad(p)[0])


def fur_colours(co):
    """Per-vertex linear RGBA for the fur body."""
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    ax = np.abs(x)
    _, parts = cat_sdf(x, y, z, parts=True)
    front = smoothstep(0.05, -0.15, y)

    col = np.tile(srgb_to_linear(FUR), (len(co), 1))

    def paint(colour, mask):
        nonlocal col
        m = np.clip(mask, 0, 1)[:, None]
        col = col * (1 - m) + srgb_to_linear(colour)[None, :] * m

    # tabby stripes: three over the crown, bands down the back, two per cheek
    crown = np.zeros(len(co))
    for c, w, zmin in ((0.0, 0.050, 0.50), (0.21, 0.042, 0.58)):
        taper = smoothstep(zmin, zmin + 0.22, z)
        crown = np.maximum(crown, (1 - smoothstep(w * taper, w * taper + 0.02, np.abs(ax - c))) * (taper > 0.02))
    crown *= smoothstep(0.75, 0.55, y) * (parts["ear"] > 0.05)
    back = (1 - smoothstep(0.035, 0.055, np.abs(((z + 0.03 * np.cos(5 * x) + 2.0) % 0.36) - 0.18)))
    back *= smoothstep(0.35, 0.60, y) * smoothstep(-0.55, -0.35, z) * smoothstep(0.75, 0.55, z)
    back *= smoothstep(0.95, 0.60, ax)
    cheek = np.zeros(len(co))
    for c in (-0.10, -0.33):
        zc = c - 0.25 * (ax - 0.80)
        width = 0.038 * smoothstep(0.74, 0.92, ax)
        cheek = np.maximum(cheek, (1 - smoothstep(width, width + 0.02, np.abs(z - zc))) * (ax > 0.76))
    cheek *= smoothstep(1.28, 1.10, ax)
    paint(FUR_DARK, np.maximum(np.maximum(crown, back), cheek))

    # white muzzle, blaze between the eyes, chest bib
    muzzle = 1 - smoothstep(0.92, 1.06, np.sqrt((ax / 0.50) ** 2 + ((z + 0.52) / 0.36) ** 2))
    blaze_w = 0.085 * smoothstep(0.42, -0.15, z)
    blaze = (1 - smoothstep(blaze_w, blaze_w + 0.03, ax)) * (z > -0.3) * (z < 0.45)
    bib = (1 - smoothstep(0.40, 0.52, np.sqrt((ax / 1.0) ** 2 + ((z + 1.55) / 1.25) ** 2))) * (z < -0.72)
    bib = np.maximum(bib, (1 - smoothstep(0.26, 0.34, ax)) * (z < -0.60) * (z > -1.0))
    paint(FUR_LIGHT, np.maximum(np.maximum(muzzle, blaze), bib) * front)

    # blush and pink inner ears
    blush = 1 - smoothstep(0.55, 1.0, np.sqrt(((ax - 0.66) / 0.17) ** 2 + ((z + 0.36) / 0.085) ** 2))
    paint(BLUSH, 0.7 * blush * front)
    paint(EAR_INNER, 1 - smoothstep(0.012, 0.032, parts["carve"]))

    return np.concatenate([col, np.ones((len(co), 1))], axis=1).astype(np.float32)


# --------------------------------------------------------------------------
# Blender helpers
# --------------------------------------------------------------------------
def new_object(name, mesh, parent=None):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj


def shade_smooth(mesh):
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    mesh.update()


def make_material(name, colour=None, attribute=None, image=None, metallic=0.0, roughness=0.8):
    """glTF-friendly Principled material; colour from a constant, attribute or image."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if attribute:
        src = nt.nodes.new("ShaderNodeVertexColor")
        src.layer_name = attribute
        nt.links.new(src.outputs["Color"], bsdf.inputs["Base Color"])
    elif image:
        src = nt.nodes.new("ShaderNodeTexImage")
        src.image = image
        nt.links.new(src.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        src = nt.nodes.new("ShaderNodeRGB")
        src.outputs[0].default_value = (*lin(colour), 1.0)
        nt.links.new(src.outputs[0], bsdf.inputs["Base Color"])
    src.name = "ColourSource"
    mat.diffuse_color = (*lin(colour), 1.0) if colour else (*lin(FUR), 1.0)
    return mat


def add_toon_output(mat, unlit=False, gloss=False):
    """Add a Cycles-only cel-shaded output next to the Principled one."""
    nt = mat.node_tree
    src = nt.nodes["ColourSource"]
    colour = src.outputs[0]
    for n in nt.nodes:
        if n.type == "OUTPUT_MATERIAL":
            n.target = "EEVEE"
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.target = "CYCLES"
    emit = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(colour, emit.inputs["Color"])
    if unlit:
        emit.inputs["Strength"].default_value = 1.0
        nt.links.new(emit.outputs[0], out.inputs["Surface"])
        return
    emit.inputs["Strength"].default_value = 0.52
    toon = nt.nodes.new("ShaderNodeBsdfToon")
    toon.component = "DIFFUSE"
    toon.inputs["Size"].default_value = 0.74
    toon.inputs["Smooth"].default_value = 0.04
    nt.links.new(colour, toon.inputs["Color"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(toon.outputs[0], add.inputs[0])
    nt.links.new(emit.outputs[0], add.inputs[1])
    last = add
    if gloss:
        spec = nt.nodes.new("ShaderNodeBsdfToon")
        spec.component = "GLOSSY"
        spec.inputs["Size"].default_value = 0.25
        spec.inputs["Smooth"].default_value = 0.02
        spec.inputs["Color"].default_value = (1, 1, 1, 1)
        add2 = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(add.outputs[0], add2.inputs[0])
        nt.links.new(spec.outputs[0], add2.inputs[1])
        last = add2
    nt.links.new(last.outputs[0], out.inputs["Surface"])


def outline_material():
    mat = bpy.data.materials.new("Outline")
    mat.use_nodes = True
    mat.use_backface_culling = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    path = nt.nodes.new("ShaderNodeLightPath")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*lin(LINE), 1.0)
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    show = nt.nodes.new("ShaderNodeMath")       # camera ray AND front face
    show.operation = "MULTIPLY"
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(geo.outputs["Backfacing"], inv.inputs[1])
    nt.links.new(inv.outputs[0], show.inputs[0])
    nt.links.new(path.outputs["Is Camera Ray"], show.inputs[1])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(show.outputs[0], mix.inputs["Fac"])
    nt.links.new(transp.outputs[0], mix.inputs[1])
    nt.links.new(emit.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    mat.diffuse_color = (*lin(LINE), 1.0)
    return mat


def add_outline(obj, mat, thickness=0.014):
    obj.data.materials.append(mat)
    mod = obj.modifiers.new("Outline", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = 1.0
    mod.use_flip_normals = True
    mod.use_rim = False
    mod.material_offset = len(obj.data.materials) - 1
    mod.show_in_editmode = False


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------
def build_fur(root):
    lo = np.array([-1.60, -1.20, BASE_Z - 0.06], dtype=np.float32)
    hi = np.array([1.60, 1.15, 1.72], dtype=np.float32)
    n = np.ceil((hi - lo) / VOXEL).astype(int) + 1
    axes = [lo[i] + VOXEL * np.arange(n[i], dtype=np.float32) for i in range(3)]
    print(f"sdf grid {tuple(n)} = {n.prod() / 1e6:.1f}M samples", flush=True)
    X, Y, Z = np.meshgrid(*axes, indexing="ij", sparse=True)
    vol = cat_sdf(X + 0 * Y + 0 * Z, Y + 0 * X + 0 * Z, Z + 0 * X + 0 * Y).astype(np.float32)
    verts, faces, _, _ = measure.marching_cubes(vol, 0.0, spacing=(VOXEL,) * 3)
    del vol
    verts = verts + lo
    # make sure faces point outwards
    v0, v1, v2 = (verts[faces[:, i]] for i in range(3))
    if np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() < 0:
        faces = faces[:, ::-1]
    print(f"marching cubes: {len(verts)} verts, {len(faces)} tris", flush=True)

    mesh = bpy.data.meshes.new("CatFur")
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(faces.size)
    mesh.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    mesh.polygons.add(len(faces))
    mesh.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    mesh.polygons.foreach_set("loop_total", np.full(len(faces), 3, dtype=np.int32))
    mesh.update(calc_edges=True)
    mesh.validate()
    obj = new_object("Fur", mesh, root)

    # regular quads, then pull every vertex back onto the exact surface
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    mesh.remesh_voxel_size = REMESH_VOXEL
    mesh.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.voxel_remesh()
    mesh = obj.data
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    for _ in range(3):
        flat = co[:, 2] < BASE_Z + 1e-3
        d = cat_sdf(co[:, 0], co[:, 1], co[:, 2])
        step = sdf_grad(co) * d[:, None]
        step[flat] = 0
        co -= step
    co[:, 2] = np.maximum(co[:, 2], BASE_Z)
    mesh.vertices.foreach_set("co", co.astype(np.float32).ravel())
    shade_smooth(mesh)
    print(f"remeshed: {len(mesh.vertices)} verts, {len(mesh.polygons)} faces", flush=True)

    attr = mesh.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", fur_colours(co).ravel())
    mesh.color_attributes.active_color = attr
    mesh.color_attributes.render_color_index = 0
    mesh.materials.append(make_material("Fur", attribute="Col", roughness=0.85))
    obj.select_set(False)
    return obj


def eye_texture(size=1024):
    v, u = np.meshgrid(np.linspace(1, -1, size), np.linspace(-1, 1, size), indexing="ij")
    r = np.sqrt(u * u + v * v)
    img = np.zeros((size, size, 3))
    top, bottom = np.array(IRIS_TOP), np.array(IRIS_BOTTOM)
    t = smoothstep(0.75, -0.75, v)[..., None]
    img[:] = top * (1 - t) + bottom * t
    # bright crescent at the bottom of the iris
    glow = smoothstep(0.55, 0.0, np.sqrt((u / 0.75) ** 2 + ((v + 0.55) / 0.42) ** 2))[..., None]
    img = img + (1 - img) * 0.35 * glow
    # dark outer ring and eyelid shadow
    ring = smoothstep(0.70, 1.0, r)[..., None]
    img = img * (1 - 0.75 * ring)
    lid = smoothstep(0.25, 0.85, v)[..., None]
    img = img * (1 - 0.55 * lid)
    # pupil
    pupil = 1 - smoothstep(0.94, 1.0, np.sqrt((u / 0.27) ** 2 + ((v - 0.02) / 0.60) ** 2))
    img = img * (1 - pupil[..., None]) + np.array([0.03, 0.04, 0.07]) * pupil[..., None]
    # highlights
    for cu, cv, rad in ((-0.30, 0.40, 0.23), (0.34, -0.42, 0.11), (-0.52, 0.10, 0.06)):
        h = 1 - smoothstep(rad - 0.015, rad, np.sqrt((u - cu) ** 2 + (v - cv) ** 2))
        img = img * (1 - h[..., None]) + h[..., None]
    rgba = np.concatenate([np.clip(img, 0, 1), np.ones((size, size, 1))], axis=2)
    image = bpy.data.images.new("EyeIris", size, size, alpha=False)
    image.pixels.foreach_set(rgba[::-1].astype(np.float32).ravel())   # rows are bottom-up
    return image


def ellipsoid_mesh(name, radii, uv=False):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=1.0)
    layer = bm.loops.layers.uv.new("UVMap") if uv else None
    for v in bm.verts:
        v.co = Vector((v.co.x * radii[0], v.co.y * radii[1], v.co.z * radii[2]))
    if uv:
        for f in bm.faces:
            for loop in f.loops:
                c = loop.vert.co
                loop[layer].uv = (0.5 + 0.5 * c.x / radii[0], 0.5 + 0.5 * c.z / radii[2])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    shade_smooth(mesh)
    return mesh


def build_eyes(root, mats):
    radii = (0.27, 0.11, 0.315)
    eye_mesh = ellipsoid_mesh("Eye", radii, uv=True)
    eye_mesh.materials.append(mats["eye"])
    rim_mesh = ellipsoid_mesh("EyeLiner", (radii[0] * 1.08, radii[1], radii[2] * 1.05))
    rim_mesh.materials.append(mats["line"])
    objs = []
    for side, name in ((1, "L"), (-1, "R")):
        p, nrm = surface_point(side * 0.43, -0.06)
        fwd = (Vector((0, -1, 0)) * 0.45 + nrm * 0.55).normalized()
        y_axis = -fwd
        x_axis = y_axis.cross(Vector((0, 0, 1))).normalized()
        z_axis = x_axis.cross(y_axis).normalized()
        rot = Matrix((x_axis, y_axis, z_axis)).transposed().to_4x4()
        tilt = Matrix.Rotation(math.radians(-9 * side), 4, "Y")   # outer corners up
        centre = p - fwd * (radii[1] - 0.038)
        eye = new_object(f"Eye.{name}", eye_mesh, root)
        eye.matrix_local = Matrix.Translation(centre) @ rot @ tilt
        rim = new_object(f"EyeLiner.{name}", rim_mesh, root)
        rim.matrix_local = Matrix.Translation(centre - fwd * 0.016 + z_axis * 0.024) @ rot @ tilt
        objs += [eye, rim]
    return objs


def build_nose(root, mat):
    radii = (0.095, 0.05, 0.064)
    mesh = ellipsoid_mesh("Nose", radii)
    for v in mesh.vertices:      # pinch the bottom into a rounded triangle
        t = min(max(-v.co.z / radii[2], 0.0), 1.0)
        v.co.x *= 1.0 - 0.62 * t * t
    mesh.materials.append(mat)
    p, nrm = surface_point(0.0, -0.275)
    obj = new_object("Nose", mesh, root)
    obj.location = p - nrm * 0.018
    return obj


def curve_object(name, points, radii, depth, mat, root):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = depth
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for pt, co, rad in zip(sp.points, points, radii):
        pt.co = (*co, 1.0)
        pt.radius = rad
    tmp = bpy.data.objects.new(name + "_curve", cu)
    bpy.context.scene.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    mesh.name = name
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    shade_smooth(mesh)
    mesh.materials.append(mat)
    return new_object(name, mesh, root)


def build_mouth(root, mat):
    mz, r = -0.405, 0.088
    objs = []

    def on_surface(xz):
        pts = []
        for x, z in xz:
            p, nrm = surface_point(x, z)
            pts.append(p + nrm * 0.002)
        return pts

    for side in (1, -1):
        xz = [(0.0, z) for z in np.linspace(-0.32, mz, 5)]
        angles = np.linspace(math.pi, 2 * math.pi + 0.55, 22)
        xz += [(side * (r + r * math.cos(a)), mz + r * math.sin(a)) for a in angles[1:]]
        pts = on_surface(xz)
        radii = [1.0] * (len(pts) - 5) + [0.9, 0.75, 0.55, 0.35, 0.15]
        objs.append(curve_object(f"Mouth.{'L' if side > 0 else 'R'}", pts, radii, 0.0125, mat, root))
    return objs


def build_whiskers(root, mat):
    objs = []
    for side in (1, -1):
        for i, (z0, rise, length) in enumerate(((-0.33, 0.20, 0.74), (-0.38, 0.02, 0.80), (-0.43, -0.16, 0.72))):
            p, nrm = surface_point(side * 0.25, z0)
            start = p - nrm * 0.01
            pts, radii = [], []
            for t in np.linspace(0, 1, 16):
                pts.append(
                    start
                    + Vector((side * length * t, -0.10 * t - 0.05 * math.sin(math.pi * t), rise * t - 0.10 * t * t))
                )
                radii.append(1.0 - 0.9 * t)
            objs.append(curve_object(f"Whisker.{'L' if side > 0 else 'R'}.{i}", pts, radii, 0.011, mat, root))
    return objs


def build_collar(root, mats):
    cz, cy = -1.02, 0.05
    bm = bmesh.new()
    major, minor, seg, ring = 0.405, 0.062, 96, 16
    rows = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        row = []
        for j in range(ring):
            b = 2 * math.pi * j / ring
            rad = major + minor * 0.75 * math.cos(b)
            row.append(bm.verts.new((rad * math.cos(a), cy + rad * math.sin(a), cz + minor * 1.25 * math.sin(b))))
        rows.append(row)
    for i in range(seg):
        for j in range(ring):
            bm.faces.new(
                (rows[i][j], rows[(i + 1) % seg][j], rows[(i + 1) % seg][(j + 1) % ring], rows[i][(j + 1) % ring])
            )
    mesh = bpy.data.meshes.new("Collar")
    bm.to_mesh(mesh)
    bm.free()
    shade_smooth(mesh)
    mesh.materials.append(mats["collar"])
    collar = new_object("Collar", mesh, root)

    bell_r = 0.125
    bell_mesh = ellipsoid_mesh("Bell", (bell_r, bell_r, bell_r))
    bell_mesh.materials.append(mats["bell"])
    bell = new_object("Bell", bell_mesh, root)
    bell.location = (0, cy - major - 0.075, cz - 0.115)
    slit_mesh = ellipsoid_mesh("BellSlit", (0.016, 0.07, 0.085))
    slit_mesh.materials.append(mats["line"])
    slit = new_object("BellSlit", slit_mesh, root)
    slit.location = bell.location + Vector((0, -bell_r * 0.62, -bell_r * 0.42))
    slit.rotation_euler = (math.radians(-55), 0, 0)
    hole_mesh = ellipsoid_mesh("BellHole", (0.032, 0.03, 0.032))
    hole_mesh.materials.append(mats["line"])
    hole = new_object("BellHole", hole_mesh, root)
    hole.location = bell.location + Vector((0, -bell_r * 0.93, -bell_r * 0.05))
    return [collar, bell, slit, hole]


# --------------------------------------------------------------------------
# Scene, export, render
# --------------------------------------------------------------------------
def setup_render(root, size, samples):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.transparent_max_bounces = 32
    sc.cycles.max_bounces = 3
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"

    world = bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    amb = nt.nodes.new("ShaderNodeBackground")
    amb.inputs["Color"].default_value = (1.0, 0.92, 0.95, 1)
    amb.inputs["Strength"].default_value = 0.25
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (*lin(BACKGROUND), 1)
    path = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(amb.outputs[0], mix.inputs[1])
    nt.links.new(bg.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])

    rig = bpy.data.objects.new("CameraRig", None)
    sc.collection.objects.link(rig)
    rig.location = (0, 0, 0.0)
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 85
    cam = bpy.data.objects.new("Camera", cam_data)
    sc.collection.objects.link(cam)
    cam.parent = rig
    cam.location = (0, -9.6, 0.25)
    cam.rotation_euler = (math.radians(88.5), 0, 0)
    sc.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.2
    sun_data.angle = math.radians(1.0)
    sun = bpy.data.objects.new("Sun", sun_data)
    sc.collection.objects.link(sun)
    sun.parent = rig          # light follows the camera, like a studio turntable
    sun.rotation_euler = (math.radians(52), 0, math.radians(-32))
    return rig


def render_view(rig, yaw_deg, pitch_deg, path):
    rig.rotation_euler = (math.radians(pitch_deg), 0, math.radians(yaw_deg))
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--turntable", action="store_true", help="also render turntable frames")
    ap.add_argument("--size", type=int, default=1200)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--views", default="front,three_quarter,side,back")
    args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
    os.makedirs(args.out, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = bpy.data.objects.new("Cat", None)
    bpy.context.scene.collection.objects.link(root)

    iris = eye_texture()
    iris.filepath_raw = os.path.join(args.out, "eye_iris.png")
    iris.file_format = "PNG"
    iris.save()
    iris.pack()
    mats = {
        "eye": make_material("Eye", colour=IRIS_BOTTOM, image=iris, roughness=0.25),
        "line": make_material("Line", colour=LINE, roughness=0.9),
        "nose": make_material("Nose", colour=NOSE, roughness=0.5),
        "whisker": make_material("Whisker", colour=WHISKER, roughness=0.6),
        "collar": make_material("Collar", colour=COLLAR, roughness=0.6),
        "bell": make_material("Bell", colour=BELL, metallic=1.0, roughness=0.3),
    }

    fur = build_fur(root)
    build_eyes(root, mats)
    nose = build_nose(root, mats["nose"])
    build_mouth(root, mats["line"])
    build_whiskers(root, mats["whisker"])
    collar_parts = build_collar(root, mats)

    # ---- export (before render-only shading is added) ----
    glb = os.path.join(args.out, "cat_head.glb")
    bpy.ops.export_scene.gltf(
        filepath=glb,
        export_format="GLB",
        export_apply=False,
        export_vertex_color="ACTIVE",
        export_all_vertex_colors=False,
        export_yup=True,
    )
    print("exported", glb, f"{os.path.getsize(glb) / 1e6:.1f} MB", flush=True)

    # ---- render-only look: cel shading + inverted-hull outline ----
    outline = outline_material()
    for obj, thick in ((fur, 0.014), (nose, 0.008), (collar_parts[0], 0.010), (collar_parts[1], 0.010)):
        add_outline(obj, outline, thick)
    add_toon_output(fur.data.materials[0])
    add_toon_output(mats["eye"], unlit=True)
    add_toon_output(mats["line"], unlit=True)
    add_toon_output(mats["whisker"], unlit=True)
    add_toon_output(mats["nose"], gloss=True)
    add_toon_output(mats["collar"])
    mats["bell"].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.0
    add_toon_output(mats["bell"], gloss=True)

    rig = setup_render(root, args.size, args.samples)
    blend = os.path.join(args.out, "cat_head.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    print("saved", blend, f"{os.path.getsize(blend) / 1e6:.1f} MB", flush=True)

    if not args.no_render:
        views = {"front": (0, 0), "three_quarter": (35, -8), "side": (90, 0), "back": (155, -8)}
        for name in args.views.split(","):
            yaw, pitch = views[name]
            render_view(rig, yaw, pitch, os.path.join(args.out, f"render_{name}.png"))
    if args.turntable:
        frames = 48
        bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = 600
        bpy.context.scene.cycles.samples = 32
        for i in range(frames):
            render_view(rig, 360.0 * i / frames, -6, os.path.join(args.out, "turntable", f"{i:03d}.png"))


if __name__ == "__main__":
    main()
