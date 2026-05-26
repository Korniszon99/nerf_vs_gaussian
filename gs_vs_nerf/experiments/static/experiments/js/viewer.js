import * as THREE from "https://unpkg.com/three@0.170.0/build/three.module.js";
import { OrbitControls } from "https://unpkg.com/three@0.170.0/examples/jsm/controls/OrbitControls.js";
import { PLYLoader } from "https://unpkg.com/three@0.170.0/examples/jsm/loaders/PLYLoader.js";

const ACTIVE_VIEWERS = new WeakMap();

function renderMessage(container, message, tone = "info") {
    const toneClass = tone === "danger" ? "alert-danger" : tone === "warning" ? "alert-warning" : "alert-info";
    container.innerHTML = `<div class="alert ${toneClass} mb-0" role="alert">${message}</div>`;
}

/**
 * Inicjalizuje viewer .ply dla wskazanego elementu lub selektora.
 * @param {HTMLElement|string} containerOrSelector
 * @param {string=} explicitCloudUrl
 */
export function initPointCloudViewer(containerOrSelector, explicitCloudUrl) {
    const container =
        typeof containerOrSelector === "string"
            ? document.querySelector(containerOrSelector)
            : containerOrSelector;

    if (!container) {
        return null;
    }

    if (ACTIVE_VIEWERS.has(container)) {
        ACTIVE_VIEWERS.get(container)();
    }

    const cloudUrl = explicitCloudUrl || container.dataset.pointCloudUrl;
    if (!cloudUrl) {
        renderMessage(container, "Brak pliku chmury punktow w artefaktach.");
        return null;
    }

    const ext = cloudUrl.split(".").pop()?.toLowerCase();
    if (ext !== "ply") {
        renderMessage(
            container,
            "Aktualny viewer obsluguje tylko render .ply. Dodaj konwersje artefaktu do .ply po treningu.",
            "warning",
        );
        return null;
    }

    container.innerHTML = "";
    container.classList.add("position-relative", "bg-dark", "rounded");

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

    const loader = new PLYLoader();
    loader.load(
        cloudUrl,
        (geometry) => {
            geometry.computeVertexNormals();
            geometry.center();
            const material = new THREE.PointsMaterial({ size: 0.01, color: 0x74b9ff });
            const points = new THREE.Points(geometry, material);
            scene.add(points);
        },
        undefined,
        () => {
            renderMessage(container, "Nie udalo sie zaladowac pliku .ply.", "danger");
        },
    );

    const animate = () => {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    };
    animate();

    const onResize = () => {
        const width = container.clientWidth;
        const height = container.clientHeight;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
    };
    window.addEventListener("resize", onResize);

    const teardown = () => {
        window.removeEventListener("resize", onResize);
        controls.dispose();
        renderer.dispose();
        container.innerHTML = "";
        ACTIVE_VIEWERS.delete(container);
    };
    ACTIVE_VIEWERS.set(container, teardown);
    return teardown;
}

// Backward compatibility: automatyczna inicjalizacja przy pierwszym renderze #viewer.
if (document.getElementById("viewer")) {
    initPointCloudViewer("#viewer");
}
