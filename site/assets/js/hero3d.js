/* EasyChat 3D hero: glossy chat bubbles floating in a particle network.
   Uses three.js (vendored). Falls back to the CSS gradient when WebGL is unavailable. */
(function () {
  var canvas = document.getElementById("hero-3d");
  if (!canvas || typeof THREE === "undefined") return;

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  } catch (e) {
    canvas.remove();
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputEncoding = THREE.sRGBEncoding;

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
  camera.position.set(0, 0, 14);

  var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  var accent = new THREE.Color(dark ? 0x6aa2ff : 0x2f6fdf);
  var accent2 = new THREE.Color(dark ? 0x7fd0ff : 0x5fb3f9);
  var soft = new THREE.Color(dark ? 0x2a3a55 : 0xffffff);

  // Lights
  scene.add(new THREE.AmbientLight(0xffffff, dark ? 0.35 : 0.6));
  var key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(5, 6, 8);
  scene.add(key);
  var rim = new THREE.PointLight(accent2.getHex(), 1.4, 40);
  rim.position.set(-6, -3, 6);
  scene.add(rim);

  // Chat bubble shape: rounded rectangle with a tail
  function bubbleShape(w, h, r, tailLeft) {
    var s = new THREE.Shape();
    var x = -w / 2, y = -h / 2;
    s.moveTo(x + r, y);
    if (tailLeft) {
      s.lineTo(x + r * 0.2, y - r * 0.9);
      s.lineTo(x + r * 1.6, y);
    }
    s.lineTo(x + w - r, y);
    s.quadraticCurveTo(x + w, y, x + w, y + r);
    s.lineTo(x + w, y + h - r);
    s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    s.lineTo(x + r, y + h);
    s.quadraticCurveTo(x, y + h, x, y + h - r);
    s.lineTo(x, y + r);
    s.quadraticCurveTo(x, y, x + r, y);
    return s;
  }
  var extrude = { depth: 0.35, bevelEnabled: true, bevelThickness: 0.18, bevelSize: 0.16, bevelSegments: 6, curveSegments: 18 };

  var group = new THREE.Group();
  scene.add(group);

  var specs = [
    { w: 3.2, h: 1.8, x: 3.6, y: 1.6, z: 0, c: accent, tail: true },
    { w: 2.4, h: 1.4, x: 6.2, y: -1.4, z: -1.5, c: soft, tail: false },
    { w: 1.8, h: 1.1, x: 1.6, y: -2.6, z: 1, c: accent2, tail: true },
    { w: 1.4, h: 0.9, x: 7.4, y: 2.9, z: -3, c: accent2, tail: false },
    { w: 1.2, h: 0.8, x: -1.2, y: 3.2, z: -4, c: soft, tail: true }
  ];
  var bubbles = specs.map(function (sp, i) {
    var geo = new THREE.ExtrudeGeometry(bubbleShape(sp.w, sp.h, 0.45, sp.tail), extrude);
    geo.center();
    var mat = new THREE.MeshPhysicalMaterial({
      color: sp.c, roughness: 0.22, metalness: 0.05, clearcoat: 1, clearcoatRoughness: 0.15,
      transparent: true, opacity: sp.c === soft ? 0.92 : 0.96
    });
    var mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(sp.x, sp.y, sp.z);
    mesh.rotation.set(0.15 * (i % 2 ? 1 : -1), -0.35, 0.05);
    mesh.userData = { baseY: sp.y, phase: i * 1.3, speed: 0.5 + i * 0.12 };

    // Three "typing" dots on each bubble face
    var dotMat = new THREE.MeshStandardMaterial({ color: sp.c === soft ? accent : 0xffffff, roughness: 0.3 });
    for (var d = -1; d <= 1; d++) {
      var dot = new THREE.Mesh(new THREE.SphereGeometry(sp.h * 0.1, 20, 20), dotMat);
      dot.position.set(d * sp.h * 0.32, 0, 0.36);
      dot.userData.dotIndex = d + 1;
      mesh.add(dot);
    }
    group.add(mesh);
    return mesh;
  });

  // Particle network
  var COUNT = window.innerWidth < 700 ? 70 : 140;
  var positions = new Float32Array(COUNT * 3);
  var velocities = [];
  for (var i = 0; i < COUNT; i++) {
    positions[i * 3] = (Math.random() - 0.3) * 22;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 12;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 8 - 3;
    velocities.push([(Math.random() - 0.5) * 0.01, (Math.random() - 0.5) * 0.01]);
  }
  var pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  var pMat = new THREE.PointsMaterial({ color: accent, size: 0.07, transparent: true, opacity: 0.7 });
  scene.add(new THREE.Points(pGeo, pMat));

  var MAX_LINKS = COUNT * 4;
  var linePos = new Float32Array(MAX_LINKS * 6);
  var lGeo = new THREE.BufferGeometry();
  lGeo.setAttribute("position", new THREE.BufferAttribute(linePos, 3));
  var lMat = new THREE.LineBasicMaterial({ color: accent, transparent: true, opacity: dark ? 0.16 : 0.12 });
  var lines = new THREE.LineSegments(lGeo, lMat);
  scene.add(lines);

  function updateLinks() {
    var n = 0;
    for (var a = 0; a < COUNT && n < MAX_LINKS; a++) {
      for (var b = a + 1; b < COUNT && n < MAX_LINKS; b++) {
        var dx = positions[a * 3] - positions[b * 3];
        var dy = positions[a * 3 + 1] - positions[b * 3 + 1];
        var dz = positions[a * 3 + 2] - positions[b * 3 + 2];
        if (dx * dx + dy * dy + dz * dz < 5) {
          linePos.set([positions[a * 3], positions[a * 3 + 1], positions[a * 3 + 2], positions[b * 3], positions[b * 3 + 1], positions[b * 3 + 2]], n * 6);
          n++;
        }
      }
    }
    lGeo.setDrawRange(0, n * 2);
    lGeo.attributes.position.needsUpdate = true;
  }

  // Mouse parallax
  var mouse = { x: 0, y: 0 }, target = { x: 0, y: 0 };
  window.addEventListener("pointermove", function (e) {
    target.x = (e.clientX / window.innerWidth - 0.5) * 2;
    target.y = (e.clientY / window.innerHeight - 0.5) * 2;
  }, { passive: true });

  function resize() {
    var w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // On narrow screens push the bubbles to the right edge and back, behind the copy
    group.position.x = w < 900 ? 3 : 0;
    group.position.z = w < 900 ? -5 : 0;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);
  resize();

  var visible = true;
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) { visible = entries[0].isIntersecting; if (visible) loop(); }).observe(canvas);
  }

  var clock = new THREE.Clock();
  var running = false;
  function frame() {
    var t = clock.getElapsedTime();
    mouse.x += (target.x - mouse.x) * 0.04;
    mouse.y += (target.y - mouse.y) * 0.04;
    group.rotation.y = mouse.x * 0.18;
    group.rotation.x = mouse.y * 0.1;

    bubbles.forEach(function (m) {
      var u = m.userData;
      m.position.y = u.baseY + Math.sin(t * u.speed + u.phase) * 0.35;
      m.rotation.z = Math.sin(t * 0.4 + u.phase) * 0.08;
      m.children.forEach(function (dot) {
        dot.position.z = 0.36 + Math.max(0, Math.sin(t * 5 - dot.userData.dotIndex * 0.9)) * 0.12;
      });
    });

    for (var i = 0; i < COUNT; i++) {
      positions[i * 3] += velocities[i][0];
      positions[i * 3 + 1] += velocities[i][1];
      if (Math.abs(positions[i * 3] - 3) > 12) velocities[i][0] *= -1;
      if (Math.abs(positions[i * 3 + 1]) > 6) velocities[i][1] *= -1;
    }
    pGeo.attributes.position.needsUpdate = true;
    updateLinks();
    renderer.render(scene, camera);
  }
  function loop() {
    if (running) return;
    running = true;
    (function tick() {
      if (!visible || document.hidden) { running = false; return; }
      frame();
      requestAnimationFrame(tick);
    })();
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) loop(); });

  if (reduceMotion) { updateLinks(); renderer.render(scene, camera); }
  else loop();
})();
