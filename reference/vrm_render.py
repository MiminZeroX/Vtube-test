import bpy, sys, math, shutil, os
from mathutils import Vector
src, out = sys.argv[-2], sys.argv[-1]
glb = out + '.glb'; shutil.copy(src, glb)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb); os.remove(glb)
sc = bpy.context.scene
meshes = [o for o in sc.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)]
for o in [o for o in sc.objects if o.type == 'MESH' and o not in meshes]: o.hide_render = True
arm = next((o for o in sc.objects if o.type == 'ARMATURE'), None)
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
print('BBOX', [round(v, 2) for v in lo], [round(v, 2) for v in hi], 'bones', len(arm.data.bones) if arm else 0)
head = arm.pose.bones.get('Head') or next((b for b in arm.pose.bones if 'head' in b.name.lower()), None) if arm else None
hz = (arm.matrix_world @ head.head).z if head else hi.z - 0.3
print('HEADBONE', head.name if head else None, round(hz, 2), 'KEYS', [k.name for o in meshes if o.data.shape_keys for k in o.data.shape_keys.key_blocks])
sc.render.engine = 'CYCLES'; sc.cycles.samples = 24; sc.cycles.use_denoising = True
sc.render.resolution_x = 600; sc.render.resolution_y = 800
sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.9, 0.93, 0.96, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 1.1
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'
def shot(name, centre, scale, yaw=0.0):
    cam.data.ortho_scale = scale
    d = Vector((math.sin(yaw) * 10, -math.cos(yaw) * 10, 0))
    # VRM 0.x faces +Y in Blender after import (glTF -Z flip), so look from +Y if needed
    cam.location = centre + d * FRONT; cam.rotation_euler = (math.pi / 2, 0, yaw + (math.pi if FRONT < 0 else 0))
    sc.render.filepath = f'{out}_{name}.png'; bpy.ops.render.render(write_still=True)
FRONT = -1
c = (lo + hi) / 2; H = hi.z - lo.z
shot('full', c, H * 1.1, 0.5)
# wireframe overlay
line = bpy.data.materials.new('wire'); line.use_nodes = True
nt = line.node_tree; nt.nodes.clear(); o = nt.nodes.new('ShaderNodeOutputMaterial'); e = nt.nodes.new('ShaderNodeEmission'); e.inputs[0].default_value = (0.02, 0.02, 0.05, 1); nt.links.new(e.outputs[0], o.inputs[0])
for m in meshes:
    m.data.materials.append(line); md = m.modifiers.new('wire', 'WIREFRAME'); md.thickness = H * 0.0018; md.use_replace = False; md.material_offset = len(m.data.materials) - 1
hc = Vector((c.x, c.y, hz + H * 0.08))
shot('wire', hc, H * 0.45, 0.0)
for m in meshes: m.modifiers.remove(m.modifiers['wire'])
for m in meshes:
    if m.data.shape_keys:
        for k in m.data.shape_keys.key_blocks:
            n = k.name.lower().split('.')[-1]
            if n in ('blink_l', 'blink_left', 'a', 'a1', 'phoneme_a'): k.value = 1.0
shot('expr', hc, H * 0.45, 0.0)
