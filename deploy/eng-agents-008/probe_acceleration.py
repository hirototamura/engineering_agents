"""Fail-closed CUDA/MJX/EGL or RTX/OptiX smoke test. Run with the reserved GPU visible."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path


def mjx_probe(output):
    import jax
    import mujoco
    from mujoco import mjx
    from OpenGL import GL
    from PIL import Image
    devices = jax.devices()
    assert len(devices) == 1 and devices[0].platform == "gpu", devices
    model = mujoco.MjModel.from_xml_string('''<mujoco><option timestep="0.002"/>
      <visual><global offwidth="320" offheight="240"/></visual>
      <worldbody><light pos="0 0 3"/><geom type="plane" size="2 2 .1"/>
        <body pos="0 0 0.4"><freejoint/>
          <geom type="box" size=".076 .076 .076" mass="1" rgba=".15 .5 .8 1"/>
        </body></worldbody></mujoco>''')
    gpu_model = mjx.put_model(model)
    data = mjx.make_data(gpu_model)
    step = jax.jit(mjx.step)
    for _ in range(10):
        data = step(gpu_model, data)
    data.qpos.block_until_ready()
    assert float(data.qpos[2]) < 0.4
    cpu_data = mjx.get_data(model, data)  # Transfer state for rendering, not another solver.
    with mujoco.Renderer(model, height=240, width=320) as renderer:
        renderer.update_scene(cpu_data)
        pixels = renderer.render()
        vendor = GL.glGetString(GL.GL_VENDOR).decode()
        gpu = GL.glGetString(GL.GL_RENDERER).decode()
        assert "NVIDIA" in vendor and "A5000" in gpu, (vendor, gpu)
        Image.fromarray(pixels).save(output / "mjx-egl.png")
    return {"engine": "mjx_cuda_and_egl", "jax_devices": [str(d) for d in devices],
            "opengl_vendor": vendor, "opengl_renderer": gpu,
            "steps": 10, "final_z_m": float(data.qpos[2]), "passed": True}


def optix_probe(output):
    import bpy
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    selected = []
    for device in prefs.devices:
        device.use = device.type == "OPTIX"
        if device.use:
            selected.append({"name": device.name, "id": device.id})
    assert len(selected) == 1 and "A5000" in selected[0]["name"], selected
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 8
    scene.render.resolution_x = 320
    scene.render.resolution_y = 240
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(output / "optix.png")
    bpy.ops.render.render(write_still=True)
    return {"engine": "blender_cycles_optix", "devices": selected,
            "blender_version": bpy.app.version_string, "passed": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=["mjx", "optix"])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not os.environ.get("CUDA_VISIBLE_DEVICES", "").startswith("GPU-"):
        raise RuntimeError("Set CUDA_VISIBLE_DEVICES to the reserved GPU UUID")
    args.output.mkdir(parents=True, exist_ok=True)
    result = (mjx_probe if args.engine == "mjx" else optix_probe)(args.output)
    result["gpu_uuid"] = os.environ["CUDA_VISIBLE_DEVICES"]
    (args.output / (args.engine + ".json")).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
