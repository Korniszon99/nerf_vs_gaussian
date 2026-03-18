import * as THREE from "https://unpkg.com/three@0.170.0/build/three.module.js";
import { OrbitControls } from "https://unpkg.com/three@0.170.0/examples/jsm/controls/OrbitControls.js";
import { PLYLoader } from "https://unpkg.com/three@0.170.0/examples/jsm/loaders/PLYLoader.js";

const container = document.getElementById("viewer");

if (!container) {
    throw new Error("Brak elementu #viewer");
}

const cloudUrl = container.dataset.pointCloudUrl;
if (!cloudUrl) {
    container.innerHTML = "<p style='color:#fff;padding:8px'>Brak pliku chmury punktów w artefaktach.</p>";
} else {
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0e1111);

    const camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.01, 5000);
    camera.position.set(0, 0.5, 2.0);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    const ambient = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambient);

    const grid = new THREE.GridHelper(4, 20, 0x666666, 0x333333);
    scene.add(grid);

    const ext = cloudUrl.split(".").pop()?.toLowerCase();
    if (ext !== "ply") {
        container.insertAdjacentHTML(
            "beforeend",
            "<p style='position:absolute;color:#fff;padding:8px'>Aktualny viewer obsługuje render .ply. Dodaj konwersję artefaktu do .ply po treningu.</p>",
        );
    } else {
        const loader = new PLYLoader();
        loader.load(cloudUrl, (geometry) => {
            geometry.computeVertexNormals();
            geometry.center();
            const material = new THREE.PointsMaterial({ size: 0.01, color: 0x74b9ff });
            const points = new THREE.Points(geometry, material);
            scene.add(points);
        });
    }

    const animate = () => {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    };
    animate();

    window.addEventListener("resize", () => {
        const width = container.clientWidth;
        const height = container.clientHeight;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
    });
}

