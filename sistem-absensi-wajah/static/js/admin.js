/* Panel admin: peserta (CRUD + foto), rekap absensi, ekspor Excel, pengaturan. */
"use strict";

/* ---------- util ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtTanggal(iso) {
  if (!iso) return "-";
  const [y, m, d] = iso.split("-");
  const hari = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]
    [new Date(+y, +m - 1, +d).getDay()];
  return `${hari}, ${d}/${m}/${y}`;
}

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: opts.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...opts,
  });
  if (res.status === 401) { location.href = "/login"; throw new Error("unauthorized"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Terjadi kesalahan (" + res.status + ")");
  return data;
}

const toastEl = document.getElementById("toast");
let toastTimer = null;
function toast(pesan, error = false) {
  toastEl.textContent = pesan;
  toastEl.className = "toast tampil" + (error ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toastEl.className = "toast"), 3500);
}

/* ---------- tab ---------- */
document.querySelectorAll(".sidebar nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".sidebar nav button").forEach((b) => b.classList.remove("aktif"));
    document.querySelectorAll(".section").forEach((s) => s.classList.remove("aktif"));
    btn.classList.add("aktif");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("aktif");
    if (btn.dataset.tab === "dashboard") muatStats();
    if (btn.dataset.tab === "peserta") muatPeserta();
    if (btn.dataset.tab === "absensi") muatAbsensi();
    if (btn.dataset.tab === "pengaturan") muatInfo();
  });
});

/* ---------- dashboard ---------- */
async function muatStats() {
  try {
    const s = await api("/api/admin/stats");
    document.getElementById("statGrid").innerHTML = `
      <div class="stat-card biru"><div class="angka">${s.total_peserta}</div><div class="label">Total Peserta Aktif</div></div>
      <div class="stat-card hijau"><div class="angka">${s.hadir}</div><div class="label">Hadir Hari Ini</div></div>
      <div class="stat-card merah"><div class="angka">${s.terlambat}</div><div class="label">Terlambat</div></div>
      <div class="stat-card hijau"><div class="angka">${s.sudah_pulang}</div><div class="label">Sudah Pulang</div></div>
      <div class="stat-card kuning"><div class="angka">${s.belum_hadir}</div><div class="label">Belum Absen</div></div>`;
    renderTabelAbsensi(document.getElementById("tbodyHariIni"), s.hari_ini, true);
  } catch (e) { toast(e.message, true); }
}

function renderTabelAbsensi(tbody, records, ringkas = false) {
  if (!records.length) {
    tbody.innerHTML = `<tr><td colspan="${ringkas ? 8 : 9}" class="kosong">Belum ada data absensi</td></tr>`;
    return;
  }
  tbody.innerHTML = records.map((r) => `
    <tr>
      ${ringkas ? "" : `<td>${esc(fmtTanggal(r.tanggal))}</td>`}
      <td>${esc(r.waktu)}</td>
      <td>${r.waktu_pulang ? esc(r.waktu_pulang) : '<span style="color:#94a3b8">—</span>'}</td>
      <td>${esc(r.kode)}</td>
      <td><b>${esc(r.nama)}</b></td>
      <td><span class="badge ${r.status === "Hadir" ? "badge-hijau" : "badge-merah"}">${esc(r.status)}</span>
          ${r.status_pulang ? `<span class="badge ${r.status_pulang === "Pulang Cepat" ? "badge-merah" : "badge-hijau"}">${esc(r.status_pulang)}</span>` : ""}</td>
      <td>${Math.round((r.skor || 0) * 100)}%</td>
      <td>${r.snapshot ? `<a href="/snapshots/${encodeURIComponent(r.snapshot)}" target="_blank">
          <img class="thumb" src="/snapshots/${encodeURIComponent(r.snapshot)}" alt="bukti"></a>` : "-"}</td>
      <td><button class="btn btn-merah btn-kecil" data-del-att="${r.id}">Hapus</button></td>
    </tr>`).join("");
  tbody.querySelectorAll("[data-del-att]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Hapus catatan absensi ini?")) return;
      try {
        await api("/api/admin/attendance/" + b.dataset.delAtt, { method: "DELETE" });
        toast("Catatan dihapus.");
        b.closest("tr").remove();
      } catch (e) { toast(e.message, true); }
    }));
}

/* ---------- peserta ---------- */
let daftarPeserta = [];

async function muatPeserta() {
  try {
    const r = await api("/api/admin/users");
    daftarPeserta = r.users;
    renderPeserta();
  } catch (e) { toast(e.message, true); }
}

function renderPeserta() {
  const q = (document.getElementById("cariPeserta").value || "").toLowerCase();
  const data = daftarPeserta.filter(
    (u) => !q || u.nama.toLowerCase().includes(q) || u.kode.toLowerCase().includes(q));
  const tbody = document.getElementById("tbodyPeserta");
  if (!data.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="kosong">Tidak ada peserta</td></tr>`;
    return;
  }
  tbody.innerHTML = data.map((u) => `
    <tr>
      <td>${u.foto ? `<img class="thumb" src="/foto-referensi/${u.id}/${encodeURIComponent(u.foto)}" alt="">` : `<div class="thumb"></div>`}</td>
      <td>${esc(u.kode)}</td>
      <td><b>${esc(u.nama)}</b></td>
      <td>${u.jumlah_foto} foto</td>
      <td><span class="badge ${u.aktif ? "badge-hijau" : "badge-abu"}">${u.aktif ? "Aktif" : "Nonaktif"}</span></td>
      <td style="white-space:nowrap">
        <button class="btn btn-putih btn-kecil" data-edit="${u.id}">Edit</button>
        <button class="btn btn-putih btn-kecil" data-toggle="${u.id}">${u.aktif ? "Nonaktifkan" : "Aktifkan"}</button>
        <button class="btn btn-merah btn-kecil" data-del="${u.id}">Hapus</button>
      </td>
    </tr>`).join("");
  tbody.querySelectorAll("[data-edit]").forEach((b) =>
    b.addEventListener("click", () => bukaModalEdit(+b.dataset.edit)));
  tbody.querySelectorAll("[data-toggle]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await api(`/api/admin/users/${b.dataset.toggle}/toggle`, { method: "POST" });
        muatPeserta();
      } catch (e) { toast(e.message, true); }
    }));
  tbody.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Hapus peserta ini BESERTA seluruh riwayat absensinya?")) return;
      try {
        await api("/api/admin/users/" + b.dataset.del, { method: "DELETE" });
        toast("Peserta dihapus.");
        muatPeserta();
      } catch (e) { toast(e.message, true); }
    }));
}
document.getElementById("cariPeserta").addEventListener("input", renderPeserta);

/* ---------- modal peserta ---------- */
const modal = document.getElementById("modalUser");
let fotoBaru = [];   // File[] foto terpilih (upload / jepretan kamera)

function bukaModal() {
  fotoBaru = [];
  document.getElementById("fUserId").value = "";
  document.getElementById("fKode").value = "";
  document.getElementById("fNama").value = "";
  document.getElementById("fFoto").value = "";
  document.getElementById("previewBaru").innerHTML = "";
  document.getElementById("previewLama").innerHTML = "";
  document.getElementById("grpFotoLama").style.display = "none";
  document.getElementById("modalJudul").textContent = "Tambah Peserta";
  modal.classList.add("tampil");
}

async function bukaModalEdit(id) {
  bukaModal();
  document.getElementById("modalJudul").textContent = "Edit Peserta";
  document.getElementById("fUserId").value = id;
  const u = daftarPeserta.find((x) => x.id === id);
  if (u) {
    document.getElementById("fKode").value = u.kode;
    document.getElementById("fNama").value = u.nama;
  }
  try {
    const r = await api(`/api/admin/users/${id}/photos`);
    if (r.photos.length) {
      document.getElementById("grpFotoLama").style.display = "";
      document.getElementById("previewLama").innerHTML = r.photos.map((p) => `
        <div class="item">
          <img src="/foto-referensi/${id}/${encodeURIComponent(p.file)}" alt="foto referensi">
          <button type="button" class="hapus" data-del-photo="${p.id}" aria-label="Hapus foto">&times;</button>
        </div>`).join("");
      document.querySelectorAll("#previewLama [data-del-photo]").forEach((b) =>
        b.addEventListener("click", async () => {
          if (!confirm("Hapus foto referensi ini?")) return;
          try {
            const res = await api("/api/admin/photos/" + b.dataset.delPhoto, { method: "DELETE" });
            toast(res.warning || "Foto dihapus.");
            bukaModalEdit(id);
            muatPeserta();
          } catch (e) { toast(e.message, true); }
        }));
    }
  } catch (e) { toast(e.message, true); }
}

document.getElementById("btnTambah").addEventListener("click", bukaModal);
document.getElementById("btnBatalModal").addEventListener("click", () => modal.classList.remove("tampil"));
modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.remove("tampil"); });

function renderPreviewBaru() {
  document.getElementById("previewBaru").innerHTML = fotoBaru.map((f, i) => `
    <div class="item">
      <img src="${URL.createObjectURL(f)}" alt="pratinjau foto">
      <button type="button" class="hapus" data-i="${i}" aria-label="Hapus foto">&times;</button>
    </div>`).join("");
  document.querySelectorAll("#previewBaru .hapus").forEach((b) =>
    b.addEventListener("click", () => {
      fotoBaru.splice(+b.dataset.i, 1);
      renderPreviewBaru();
    }));
}

document.getElementById("fFoto").addEventListener("change", (e) => {
  fotoBaru.push(...Array.from(e.target.files));
  renderPreviewBaru();
});

/* kamera di dalam modal */
let modalStream = null;
const modalVideo = document.getElementById("modalVideo");
document.getElementById("btnBukaKamera").addEventListener("click", async () => {
  try {
    modalStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640 }, audio: false });
    modalVideo.srcObject = modalStream;
    document.getElementById("kameraBox").style.display = "";
    document.getElementById("btnBukaKamera").style.display = "none";
  } catch (e) { toast("Tidak dapat membuka kamera: " + e.message, true); }
});
document.getElementById("btnTutupKamera").addEventListener("click", () => {
  modalStream?.getTracks().forEach((t) => t.stop());
  modalStream = null;
  document.getElementById("kameraBox").style.display = "none";
  document.getElementById("btnBukaKamera").style.display = "";
});
document.getElementById("btnJepret").addEventListener("click", () => {
  if (!modalStream) return;
  const c = document.createElement("canvas");
  c.width = modalVideo.videoWidth || 640;
  c.height = modalVideo.videoHeight || 480;
  c.getContext("2d").drawImage(modalVideo, 0, 0);
  c.toBlob((blob) => {
    if (!blob) return;
    fotoBaru.push(new File([blob], `jepretan_${Date.now()}.jpg`, { type: "image/jpeg" }));
    renderPreviewBaru();
  }, "image/jpeg", 0.92);
});

/* simpan (tambah / edit) */
document.getElementById("formUser").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("fUserId").value;
  const fd = new FormData();
  fd.append("kode", document.getElementById("fKode").value.trim());
  fd.append("nama", document.getElementById("fNama").value.trim());
  fotoBaru.forEach((f) => fd.append("photos", f));
  try {
    if (id) {
      await api("/api/admin/users/" + id, {
        method: "PATCH", body: JSON.stringify({
          kode: document.getElementById("fKode").value.trim(),
          nama: document.getElementById("fNama").value.trim(),
        }),
      });
      if (fotoBaru.length) {
        const r = await api(`/api/admin/users/${id}/photos`, { method: "POST", body: fd });
        if (r.detail?.length) toast("Sebagian foto ditolak: " + r.detail.join("; "), true);
      }
      toast("Perubahan disimpan.");
    } else {
      if (!fotoBaru.length) { toast("Minimal satu foto wajah diperlukan.", true); return; }
      const r = await api("/api/admin/users", { method: "POST", body: fd });
      toast(`Peserta ditambahkan (${r.berhasil} foto valid).` +
        (r.detail?.length ? " Ditolak: " + r.detail.join("; ") : ""));
    }
    modalStream?.getTracks().forEach((t) => t.stop());
    modal.classList.remove("tampil");
    muatPeserta();
  } catch (e2) { toast(e2.message, true); }
});

/* ---------- rekap absensi ---------- */
const fltDari = document.getElementById("fltDari");
const fltSampai = document.getElementById("fltSampai");
{
  const now = new Date();
  fltSampai.value = now.toISOString().slice(0, 10);
  fltDari.value = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
}

async function muatAbsensi() {
  try {
    const r = await api(`/api/admin/attendance?from=${fltDari.value}&to=${fltSampai.value}`);
    renderTabelAbsensi(document.getElementById("tbodyAbsensi"), r.records, false);
  } catch (e) { toast(e.message, true); }
}
document.getElementById("btnTerapkan").addEventListener("click", muatAbsensi);
document.getElementById("btnEkspor").addEventListener("click", () => {
  window.open(`/api/admin/export?from=${fltDari.value}&to=${fltSampai.value}`, "_blank");
});

/* ---------- pengaturan ---------- */
async function muatInfo() {
  try {
    const r = await api("/api/admin/info");
    document.getElementById("infoSistem").innerHTML = `
      <div>Versi aplikasi : <b>${esc(r.versi)}</b></div>
      <div>Model wajah : <b>${esc(r.model)}</b></div>
      <div>Ambang kecocokan : <b>${r.threshold}</b> (cosine)</div>
      <div>Jam datang : <b>${esc(r.jam_datang)}</b> &middot; Jam pulang : <b>${esc(r.jam_pulang)}</b></div>`;
    // muat nilai jam ke form pengaturan
    const s = await api("/api/admin/settings");
    document.getElementById("setJamDatang").value = s.jam_datang;
    document.getElementById("setJamPulang").value = s.jam_pulang;
    document.getElementById("jamInfo").textContent =
      `Aktif saat ini: datang ${s.jam_datang} • pulang ${s.jam_pulang}`;
  } catch (e) { toast(e.message, true); }
}

document.getElementById("btnSimpanJam").addEventListener("click", async () => {
  const jam_datang = document.getElementById("setJamDatang").value;
  const jam_pulang = document.getElementById("setJamPulang").value;
  if (!jam_datang || !jam_pulang) { toast("Kedua jam wajib diisi.", true); return; }
  try {
    await api("/api/admin/settings", {
      method: "POST", body: JSON.stringify({ jam_datang, jam_pulang }),
    });
    toast("Jam datang & pulang tersimpan.");
    document.getElementById("jamInfo").textContent =
      `Aktif saat ini: datang ${jam_datang} • pulang ${jam_pulang}`;
  } catch (e) { toast(e.message, true); }
});

document.getElementById("btnPassword").addEventListener("click", async () => {
  const lama = document.getElementById("pwdLama").value;
  const baru = document.getElementById("pwdBaru").value;
  if (baru.length < 6) { toast("Password baru minimal 6 karakter.", true); return; }
  try {
    await api("/api/admin/password", {
      method: "POST", body: JSON.stringify({ lama, baru }),
    });
    toast("Password berhasil diganti.");
    document.getElementById("pwdLama").value = "";
    document.getElementById("pwdBaru").value = "";
  } catch (e) { toast(e.message, true); }
});

/* ---------- init ---------- */
muatStats();
