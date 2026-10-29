"""Convert the Meshy Pink Starbot FBX and textures to the diagnostics viewer GLB.

Run with Blender, followed by -- SOURCE_DIRECTORY OUTPUT_GLB.
"""
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def convert(source, output):
    files = list(source.glob('*.fbx'))
    if len(files) != 1:
        raise ValueError('Expected exactly one FBX in the source directory')
    fbx = files[0]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(fbx))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    points = [o.matrix_world @ Vector(p) for o in meshes for p in o.bound_box]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    # Blender Z-up / front -Y becomes glTF Y-up / front +Z on export.
    transform = Matrix.Scale(1.9 / (hi.z - lo.z), 4) @ Matrix.Translation(
        Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
    for obj in meshes:
        obj.matrix_world = transform @ obj.matrix_world
    bpy.context.view_layer.update()

    material = bpy.data.materials.new('Pink Starbot')
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    for suffix, socket in [('', 'Base Color'), ('_roughness', 'Roughness'), ('_metallic', 'Metallic')]:
        texture = nodes.new('ShaderNodeTexImage')
        texture.image = bpy.data.images.load(str(source / (fbx.stem + suffix + '.png')))
        if suffix:
            texture.image.colorspace_settings.name = 'Non-Color'
        links.new(texture.outputs['Color'], bsdf.inputs[socket])
    texture = nodes.new('ShaderNodeTexImage')
    texture.image = bpy.data.images.load(str(source / (fbx.stem + '_normal.png')))
    texture.image.colorspace_settings.name = 'Non-Color'
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(texture.outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(material)

    # The supplied mesh is static. These are telemetry anchors, not animation bones.
    # Place each anchor just above the actual front surface for reliable hovering.
    vertices, faces = [], []
    for obj in meshes:
        offset = len(vertices)
        vertices.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
        faces.extend(tuple(offset + i for i in p.vertices) for p in obj.data.polygons)
    surface = BVHTree.FromPolygons(vertices, faces)
    side = {
        'shoulder_pitch': (0.20, 0.875), 'shoulder_roll': (0.24, 0.86),
        'shoulder_yaw': (0.265, 0.84), 'elbow': (0.425, 0.85),
        'wrist_pitch': (0.66, 0.88), 'wrist_roll': (0.69, 0.825),
        'hip_pitch': (0.105, 0.56), 'hip_roll': (0.155, 0.53),
        'hip_yaw': (0.125, 0.475), 'knee': (0.13, 0.315),
        'ankle_pitch': (0.13, 0.15), 'ankle_roll': (0.165, 0.095),
    }
    positions = {}
    for joint, (x, height) in side.items():
        positions['left_' + joint] = (x, height)
        positions['right_' + joint] = (-x, height)
    positions.update(neck_pitch=(0, 0.915), neck_yaw=(0, 0.975),
                     torso_pitch=(0, 0.645), torso_yaw=(0, 0.72))
    missing = []
    for name, (x, height) in positions.items():
        point, _, _, _ = surface.ray_cast(Vector((x, -5, height)), Vector((0, 1, 0)))
        if point is None:
            missing.append(name)
            continue
        anchor = bpy.data.objects.new(name, None)
        anchor.empty_display_type = 'SPHERE'
        anchor.empty_display_size = 0.025
        anchor.location = point + Vector((0, -0.018, 0))
        bpy.context.collection.objects.link(anchor)
    if missing:
        raise ValueError(f'No model surface at joint anchors: {missing}')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in list(meshes) + [bpy.data.objects[name] for name in positions]:
        obj.select_set(True)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB',
                              use_selection=True, export_yup=True, export_animations=False)
    print(f'Exported {output} with {len(positions)} diagnostic anchors')


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:]
    if len(args) != 2:
        raise SystemExit('Usage: blender --background --python import_starbot.py -- SOURCE_DIRECTORY OUTPUT_GLB')
    convert(Path(args[0]).expanduser().resolve(), Path(args[1]).expanduser().resolve())
