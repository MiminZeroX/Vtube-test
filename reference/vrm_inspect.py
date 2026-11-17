"""Print the anatomy of a VRM file (which is a glTF binary with VRM extensions)."""
import json, struct, sys
def load(path):
    b = open(path, 'rb').read()
    n, = struct.unpack_from('<I', b, 12)
    return json.loads(b[20:20 + n])
for path in sys.argv[1:]:
    g = load(path)
    ext = g.get('extensions', {})
    print('=====', path.split('/')[-1], '| extensions:', list(ext))
    tris = 0; morphs = set()
    for m in g['meshes']:
        for p in m['primitives']:
            acc = g['accessors'][p['indices']] if 'indices' in p else g['accessors'][p['attributes']['POSITION']]
            tris += acc['count'] // 3
            if p.get('targets'): morphs.update(m.get('extras', {}).get('targetNames', p.get('extras', {}).get('targetNames', [f"{len(p['targets'])} targets"])))
    skins = g.get('skins', [])
    print(f" meshes {len(g['meshes'])}, triangles {tris}, nodes {len(g['nodes'])}, skins {len(skins)} (joints {[len(s['joints']) for s in skins]}), materials {len(g.get('materials', []))}, textures {len(g.get('images', []))}")
    print(' image sizes: see textures;', 'morph targets:', sorted(morphs)[:40], len(morphs))
    v0 = ext.get('VRM'); v1 = ext.get('VRMC_vrm')
    if v0:
        meta = v0.get('meta', {})
        print(' VRM 0.x | spec', v0.get('specVersion'), '| title', meta.get('title'), '| author', meta.get('author'), '| license', meta.get('licenseName'), '| commercial', meta.get('commercialUssageName'))
        hb = v0['humanoid']['humanBones']
        print(' humanoid bones', len(hb), ':', ' '.join(f"{h['bone']}" for h in hb))
        groups = v0.get('blendShapeMaster', {}).get('blendShapeGroups', [])
        print(' expressions:', ', '.join(f"{x.get('presetName') or x.get('name')}({len(x.get('binds', []))}b/{len(x.get('materialValues', []))}m)" for x in groups))
        sa = v0.get('secondaryAnimation', {})
        print(' spring bone groups', len(sa.get('boneGroups', [])), 'bones', sum(len(x.get('bones', [])) for x in sa.get('boneGroups', [])), '| colliders', len(sa.get('colliderGroups', [])))
        print(' firstPerson lookAt:', v0.get('firstPerson', {}).get('lookAtTypeName'), '| shaders:', sorted({m.get('shader') for m in v0.get('materialProperties', [])}))
    if v1:
        print(' VRM 1.0 | meta', {k: v1['meta'].get(k) for k in ('name', 'authors', 'licenseUrl', 'commercialUsage')})
        print(' humanoid bones', len(v1['humanoid']['humanBones']), '| expressions', list(v1.get('expressions', {}).get('preset', {})))
