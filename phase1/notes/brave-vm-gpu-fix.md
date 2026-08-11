# Brave Blank-Window GPU Fix — Investigation Report

## Problem
Brave (Chromium) shows a blank gray page area in QEMU/KVM VMs using virtio-vga,
while Firefox renders the same wizard page perfectly. The window chrome (title bar,
buttons) renders, but the page content area stays blank/transparent.

## Root Cause
The VM's `virtio-vga` device has **zero 3D capability sets** — no GL or Vulkan
support exposed to the guest. Chromium/Brave's GPU compositing pipeline requires a
working GL/Vulkan path to render page content. Without it, the page rasterizes
but can't composite to the screen.

Key evidence from `/sys/class/drm/card1-Virtual-1/capabilities`:
```
number of cap sets: 0
```

The guest also has a `virtio_icd.json` Vulkan ICD installed by the guest kernel,
pointing at the broken virtio device. Chromium prefers Vulkan → hits
`GpuControl.CreateCommandBuffer` failures → blank page.

## What Was Tried

### Brave flags (guest-side)
| Flags | GPU process | Page renders? |
|---|---|---|
| `--disable-gpu` | N/A (disabled) | ❌ No compositing |
| `--use-angle=swiftshader --enable-unsafe-swiftshader` | Clean (0 errors) | ❌ Title loads, content blank |
| `--use-gl=angle --use-angle=gl` (system Mesa/llvmpipe) | Clean | ❌ Content blank |
| `LIBGL_ALWAYS_SOFTWARE=1 --use-angle=gl --in-process-gpu` | Clean | ❌ Content blank |
| Hide virtio ICD + SwiftShader combo | Clean | ❌ Content blank |

**Key finding**: With SwiftShader flags + hidden Vulkan ICD, the GPU process runs
with zero errors in the log, the page loads (title bar shows "Syntropia — Pick your
apps"), but the content area remains blank. CDP confirms the document is `about:blank`
— the renderer never connects to the local server.

### VM video device (host-side)
| Config | Result |
|---|---|
| `<model type='virtio'/>` + `<acceleration accel3d='yes'/>` | ❌ `spice: invalid video codec` (known spice bug with NVIDIA) |
| `egl-headless` + VNC + virgl | ❌ `eglInitialize failed: EGL_NOT_INITIALIZED` (NVIDIA EGL) |
| `LIBGL_ALWAYS_SOFTWARE=1` on QEMU process | ❌ Same EGL failure |

**The NVIDIA proprietary host driver** doesn't expose the EGL/GBM path that
virglrenderer needs to create a software GL context.

## What Works
1. **Firefox** renders the wizard grid perfectly in the same VM (software WebRender).
2. **Brave on real hardware** (NVIDIA GPU) renders the wizard fine.
3. Both VMs (syntropia-fresh and syntropia-hooktest) have identical virtio-vga config
   and both exhibit the same blank Brave window.

## Diagnosis Summary
This is **not a product bug** — Brave works on real hardware. It's a virtio-gpu
limitation: Chromium's GPU compositing fundamentally requires a working GL/Vulkan
path, which the default virtio-vga (without virgl) doesn't provide.

## Recommended Fixes

### Short-term (product code)
Add a GPU fallback to `open_browser()` in `syntropia-apps-server.py`:
- After launching Brave, wait 3 seconds
- Check via Xwayland or `/sys/class/drm/` whether the guest has 3D
- If no 3D detected, fall back to Firefox for the wizard dialog
- This makes the wizard reliable on VMs and low-end GPU hardware

### Medium-term (VM testing)
For Syntropia dev/testing VMs, one of:
1. **Switch to AMD/Intel GPU** — virgl works on Mesa/EGL hosts
2. **Use GNOME Boxes or VirtualBox** — their display backends handle GL differently
3. **Accept the limitation** — Firefox renders fine, Brave is for real hardware only

### Long-term (if virgl is needed on NVIDIA hosts)
- Use `qemu-system-x86_64` directly (not libvirt) to pass
  `LIBGL_ALWAYS_SOFTWARE=1` before QEMU initializes, then use spice with
  `-spice gl=on` and manually set video codecs (bypasses libvirt's empty codec)
- This is complex and fragile; not recommended for production

## Files Referenced
- `phase1/wizard/syntropia-apps-server.py` — `open_browser()` function (lines 99-127)
- Guest: `/sys/class/drm/card1-Virtual-1/capabilities` — GPU cap sets
- Guest: `/etc/dri/icd.d/virtio_icd.json` — broken Vulkan ICD path
