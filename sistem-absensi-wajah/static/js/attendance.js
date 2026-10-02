/* Halaman absensi: akses kamera, kirim frame ke server, render instruksi. */
"use strict";

const video = document.getElementById("video");
const videoBox = document.getElementById("videoBox");
const camBadge = document.getElementById("camBadge");
const camBadgeText = camBadge.querySelector(".teks");
const statusArea = document.getElementById("statusArea");
const jamEl = document.getElementById("jam");
const tglEl = document.getElementById("tgl");

const FRAME_MS = 160;           // jeda antar frame (server memproses ~60-100 ms)
let stream = null;
let token = null;
let running = false;

/* ---------- ikon SVG ---------- */
function svg(path, vb = "0 0 24 24") {
  return `<svg viewBox="${vb}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
}
const IKON = {
  user: svg('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>'),
  check: svg('<path d="M20 6 9 17l-5-5"/>'),
  x: svg('<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>'),
  info: svg('<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>'),
  mata: svg('<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>'),
  kiri: svg('<path d="M19 12H5M12 19l-7-7 7-7"/>'),
  kanan: svg('<path d="M5 12h14M12 5l7 7-7 7"/>'),
  bawah: svg('<path d="M12 5v14M19 12l-7 7-7-7"/>'),
  senyum: svg('<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/>'),
  datang: svg('<path d="M3 12h16M13 6l6 6-6 6"/><path d="M3 4v16"/>'),
  pulang: svg('<path d="M21 12H5M11 18l-6-6 6-6"/><path d="M21 4v16"/>'),
};
const PETA_IKON_INSTRUKSI = [
  ["Kedipkan", IKON.mata], ["ke kiri", IKON.kiri], ["ke kanan", IKON.kanan],
  ["Anggukkan", IKON.bawah], ["Tersenyum", IKON.senyum],
];

/* ---------- jam ---------- */
function tick() {
  const now = new Date();
  jamEl.textContent = now.toLocaleTimeString("id-ID", { hour12: false });
  tglEl.textContent = now.toLocaleDateString("id-ID", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
}
tick();
setInterval(tick, 1000);

/* ---------- util ---------- */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function beepSukses() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain).connect(ctx.destination);
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.1, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
    osc.start();
    osc.stop(ctx.currentTime + 0.45);
  } catch (_) { /* abaikan */ }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function setCamBadge(teks, aktif = false) {
  camBadgeText.textContent = teks;
  camBadge.classList.toggle("jalan", aktif);
}

/* ---------- kamera ---------- */
async function initCamera() {
  if (!window.isSecureContext) {
    setCamBadge("Kamera butuh localhost/HTTPS");
    return renderError(
      "Akses kamera hanya diizinkan pada halaman aman (https:// atau http://localhost). " +
      "Buka aplikasi lewat alamat localhost yang tampil saat server dijalankan.");
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return renderError("Browser ini tidak mendukung akses kamera. Gunakan Chrome/Edge/Firefox terbaru.");
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 960 }, height: { ideal: 720 },
        frameRate: { ideal: 15 }, facingMode: "user",
      },
      audio: false,
    });
    video.srcObject = stream;
    // sesuaikan rasio kotak dengan rasio stream agar gambar TIDAK terpotong
    // dan panduan oval tepat di tengah area wajah
    video.addEventListener("loadedmetadata", () => {
      if (video.videoWidth && video.videoHeight) {
        videoBox.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
      }
    }, { once: true });
    video.play().catch(() => {});
    setCamBadge("Kamera aktif", true);
  } catch (err) {
    setCamBadge("Kamera tidak tersedia");
    renderError(
      "Tidak dapat mengakses kamera (" + err.name + "). " +
      "Izinkan akses kamera pada ikon kunci di address bar lalu muat ulang halaman. " +
      "Pastikan kamera tidak sedang dipakai aplikasi lain (Zoom/Meet).");
  }
}

function captureFrame() {
  // Jangan kirim frame hitam saat video belum siap
  if (!video.videoWidth || !video.videoHeight || video.readyState < 2) return null;
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  return canvas.toDataURL("image/jpeg", 0.85);
}

/* ---------- render UI ---------- */
function renderIdle() {
  statusArea.innerHTML = `
    <div class="instruksi">
      <div class="bundar bundar-biru">${IKON.user}</div>
      <h2>Verifikasi Wajah</h2>
      <div class="sub">Sistem memverifikasi wajah asli (anti-foto), lalu mencocokkannya<br>
        dengan data peserta yang didaftarkan administrator.</div>
      <div class="aksi">
        <button class="btn btn-utama btn-besar" id="btnDatang">${IKON.datang} Absen Datang</button>
        <button class="btn btn-putih btn-besar" id="btnPulang">${IKON.pulang} Absen Pulang</button>
      </div>
    </div>`;
  document.getElementById("btnDatang").addEventListener("click", () => mulaiAbsen("datang"));
  document.getElementById("btnPulang").addEventListener("click", () => mulaiAbsen("pulang"));
}

function ikonInstruksi(teks) {
  for (const [kata, ikon] of PETA_IKON_INSTRUKSI) {
    if (teks && teks.includes(kata)) return ikon;
  }
  return IKON.user;
}

function renderProses(resp) {
  const total = resp.challenge_total || 2;
  const idx = resp.challenge_index || 0;
  const fase = resp.status === "challenge";
  const persen = fase ? Math.min(100, Math.round(((idx + (resp.performed ? 0.5 : 0)) / total) * 100)) : 6;
  const ikon = resp.performed ? IKON.check : ikonInstruksi(resp.instruction);
  const bundarCls = resp.performed ? "bundar-hijau" : "bundar-biru";
  const teks = resp.performed
    ? "Bagus — kembali menghadap kamera"
    : (resp.instruction || "Posisikan wajah di dalam bingkai");
  statusArea.innerHTML = `
    <div class="instruksi">
      <div class="bundar ${bundarCls}">${ikon}</div>
      <h2>${esc(teks)}</h2>
      ${resp.detail ? `<div class="sub">${esc(resp.detail)}</div>` : ""}
      <div class="progres">
        <div class="bar"><div class="isi" style="width:${persen}%"></div></div>
        <div class="ket"><span>Verifikasi keaslian wajah</span><span>${fase ? `Tantangan ${idx + 1} dari ${total}` : "Menyiapkan"}</span></div>
      </div>
    </div>`;
}

function renderSukses(r) {
  beepSukses();
  setCamBadge("Tercatat", true);
  const pulang = r.mode === "pulang";
  const tepat = pulang ? r.status_kehadiran !== "Pulang Cepat" : r.status_kehadiran === "Hadir";
  statusArea.innerHTML = `
    <div class="hasil sukses">
      <div class="bundar bundar-hijau">${IKON.check}</div>
      <h2>${pulang ? "Absen Pulang Tercatat" : "Absen Datang Tercatat"}</h2>
      <div class="nama">${esc(r.nama)}</div>
      <div class="meta">${esc(r.kode)} &middot; ${esc(r.waktu)} WIB &middot; ${esc(r.tanggal || "")}</div>
      <div class="chip">
        <span class="badge ${tepat ? "badge-hijau" : "badge-merah"}">${esc(r.status_kehadiran)}</span>
        ${r.skor != null ? `<span class="badge badge-abu">Kecocokan ${Math.round(r.skor * 100)}%</span>` : ""}
      </div>
      <div class="aksi">
        <button class="btn btn-putih" onclick="location.reload()">Selesai</button>
      </div>
    </div>`;
}

function renderSudah(r) {
  setCamBadge("Sudah absen");
  statusArea.innerHTML = `
    <div class="hasil">
      <div class="bundar bundar-abu">${IKON.info}</div>
      <h2>${r.mode === "pulang" ? "Sudah Absen Pulang" : "Sudah Absen Datang"}</h2>
      <div class="nama">${esc(r.nama)}</div>
      <div class="meta">Tercatat pukul ${esc(r.waktu)} &middot; Status: ${esc(r.status_kehadiran)}</div>
      ${r.pesan ? `<div class="sub" style="color:var(--teks-2);margin-top:6px">${esc(r.pesan)}</div>` : ""}
      <div class="aksi">
        <button class="btn btn-putih" onclick="location.reload()">Tutup</button>
      </div>
    </div>`;
}

function renderGagal(r) {
  setCamBadge("Gagal");
  statusArea.innerHTML = `
    <div class="hasil gagal">
      <div class="bundar bundar-merah">${IKON.x}</div>
      <h2>Absensi Gagal</h2>
      <div class="sub" style="color:var(--teks-2); margin-top:6px">${esc(r.reason || "Terjadi kesalahan.")}</div>
      <div class="aksi">
        <button class="btn btn-utama" onclick="location.reload()">Coba Lagi</button>
      </div>
    </div>`;
}

function renderError(pesan) {
  statusArea.innerHTML = `
    <div class="hasil gagal">
      <div class="bundar bundar-merah">${IKON.x}</div>
      <h2>Kamera Tidak Dapat Digunakan</h2>
      <div class="sub" style="color:var(--teks-2); margin-top:6px">${esc(pesan)}</div>
    </div>`;
}

/* ---------- alur absensi ---------- */
async function api(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

async function mulaiAbsen(mode) {
  if (!stream) { renderError("Kamera belum aktif."); return; }
  const r = await api("/api/attendance/start", { mode });
  if (!r.ok) { renderGagal({ reason: r.error || "Tidak dapat memulai sesi." }); return; }
  token = r.token;
  running = true;
  setCamBadge(mode === "pulang" ? "Memproses absen pulang…" : "Memverifikasi wajah…", true);
  renderProses({ status: "align", instruction: "Posisikan wajah di dalam bingkai" });
  loop();
}

async function loop() {
  while (running && token) {
    if (document.hidden) { await sleep(300); continue; }
    const image = captureFrame();
    if (!image) { await sleep(200); continue; }
    let resp;
    try {
      resp = await api("/api/attendance/frame", { token, image });
    } catch (_) {
      running = false;
      renderGagal({ reason: "Koneksi ke server terputus. Muat ulang halaman." });
      return;
    }
    if (resp.error && !resp.status) {
      running = false;
      renderGagal({ reason: resp.error });
      return;
    }
    if (resp.final) {
      running = false;
      token = null;
      if (resp.status === "success") renderSukses(resp);
      else if (resp.status === "already") renderSudah(resp);
      else renderGagal(resp);
      return;
    }
    renderProses(resp);
    await sleep(FRAME_MS);
  }
}

window.addEventListener("beforeunload", () => {
  if (token && navigator.sendBeacon) {
    navigator.sendBeacon(
      "/api/attendance/cancel",
      new Blob([JSON.stringify({ token })], { type: "application/json" }));
  }
});

renderIdle();
initCamera();
