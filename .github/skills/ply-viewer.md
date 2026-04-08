# Skill: Three.js .ply viewer

Pattern for rendering `.ply` point clouds in the Django templates.

---

## HTML template snippet

```html
{# templates/experiments/run_detail.html #}
{% if ply_artifact %}
<div id="viewer-container" style="width:100%;height:500px;"></div>
<script type="module">
  import { initPlyViewer } from "{% static 'js/viewer.js' %}";
  initPlyViewer("viewer-container", "{{ ply_artifact.file_url }}");
</script>
{% else %}
<p class="text-muted">No .ply artifact available for this run.</p>
{% endif %}
```

---

## viewer.js skeleton

```js
// static/js/viewer.js
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160/build/three.module.js";
import { PLYLoader }    from "https://cdn.jsdelivr.net/npm/three@0.160/examples/jsm/loaders/PLYLoader.js";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.160/examples/jsm/controls/OrbitControls.js";

export function initPlyViewer(containerId, plyUrl) {
  const container = document.getElementById(containerId);
  const { clientWidth: W, clientHeight: H } = container;

  // Scene
  const scene    = new THREE.Scene();
  scene.background = new THREE.Color(0x111111);

  // Camera
  const camera = new THREE.PerspectiveCamera(60, W / H, 0.01, 100);
  camera.position.set(0, 0, 3);

  // Renderer
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(W, H);
  container.appendChild(renderer.domElement);

  // Controls
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  // Load .ply
  const loader = new PLYLoader();
  loader.load(plyUrl, (geometry) => {
    geometry.computeVertexNormals();
    const material = new THREE.PointsMaterial({
      size: 0.005,
      vertexColors: geometry.hasAttribute("color"),
    });
    const points = new THREE.Points(geometry, material);

    // Centre on bounding box
    geometry.computeBoundingBox();
    const centre = new THREE.Vector3();
    geometry.boundingBox.getCenter(centre);
    points.position.sub(centre);

    scene.add(points);
  });

  // Resize
  window.addEventListener("resize", () => {
    const { clientWidth: w, clientHeight: h } = container;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  });

  // Loop
  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}
```

---

## Django view: resolving file URL

```python
# experiments/views.py
from django.conf import settings

def run_detail(request, pk):
    run = get_object_or_404(ExperimentRun, pk=pk)
    ply_artifact = run.artifact_set.filter(artifact_type="point_cloud").first()

    ply_url = None
    if ply_artifact:
        # Serve via MEDIA_URL if file is under MEDIA_ROOT
        rel = Path(ply_artifact.file_path).relative_to(settings.MEDIA_ROOT)
        ply_url = settings.MEDIA_URL + str(rel)

    return render(request, "experiments/run_detail.html", {
        "run": run,
        "ply_artifact": ply_artifact,
        "ply_url": ply_url,
    })
```

---

## Notes

- `.splat` files are **not** supported by `PLYLoader`. See `docs/architecture.md#viewer` for options.
- For large point clouds (>5M points), consider server-side downsampling before serving.
- `OrbitControls` requires a user gesture on iOS — add a tap-to-start overlay if mobile support is needed.
