// ====== PREVIEW INPUT IMAGE ======
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("imageInput");
  const preview = document.getElementById("inputPreview");

  if (input && preview) {
    input.addEventListener("change", (e) => {
      const file = e.target.files?.[0];
      if (!file) {
        preview.classList.add("d-none");
        preview.src = "";
        return;
      }
      preview.src = URL.createObjectURL(file);
      preview.classList.remove("d-none");
    });
  }
});

// ====== RENDER TABLE ======
function renderMetricsTable(metrics) {
  const body = document.getElementById("resultsBody");
  if (!body) return;

  body.innerHTML = "";

  const rows = [
    ["Nom image", metrics.image ?? "—"],
    ["Grossissement (mag)", metrics.mag ?? "N/A"],
    ["Image valide", String(metrics.good_image)],
    ["Pontage réussi", metrics.bridging_success ?? "—"],

    ["Total cristaux", metrics.n_cristaux_total ?? "—"],
    ["Cristaux pontants", metrics.n_cristaux_pontage ?? "—"],
    ["% pontants", metrics.pct_cristaux_pontage != null ? (metrics.pct_cristaux_pontage * 100).toFixed(2) + "%" : "—"],
    ["Nombre grains", metrics.n_grains ?? "—"],

    ["Sharpness (Laplacian)", metrics.sharpness_laplacian_var != null ? Number(metrics.sharpness_laplacian_var).toFixed(2) : "—"],
    ["Contraste", metrics.contrast_range != null ? Number(metrics.contrast_range).toFixed(2) : "—"],

    ["Coverage total", metrics.coverage_all != null ? Number(metrics.coverage_all).toFixed(4) : "—"],
    ["Coverage pontage", metrics.coverage_bridging != null ? Number(metrics.coverage_bridging).toFixed(4) : "—"],
    ["Score pontage", metrics.bridging_strength_score != null ? Number(metrics.bridging_strength_score).toFixed(4) : "—"],

    ["Raisons (si invalide)", metrics.reasons ? metrics.reasons : "—"],
  ];

  rows.forEach(([k, v]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><strong>${k}</strong></td><td>${v}</td>`;
    body.appendChild(tr);
  });
}

// ====== MAIN ANALYZE ======
async function analyze() {
  const input = document.getElementById("imageInput");
  const loading = document.getElementById("loading");

  // Output elements
  const overlayImg = document.getElementById("overlay");
  const overlayWrap = document.getElementById("overlayWrap"); // optionnel si tu utilises collapse
  const resultsBody = document.getElementById("resultsBody");

  if (!input?.files || input.files.length === 0) {
    alert("Veuillez choisir une image !");
    return;
  }

  const file = input.files[0];
  const formData = new FormData();
  formData.append("image", file);

  // Reset affichage
  if (loading) loading.classList.remove("d-none");

  if (resultsBody) {
    resultsBody.innerHTML = `
      <tr>
        <td class="text-muted">Analyse en cours…</td>
        <td class="text-muted">—</td>
      </tr>
    `;
  }

  if (overlayImg) {
    overlayImg.src = "";
    overlayImg.classList.add("d-none");
  }

  // si overlayWrap existe (collapse), on le ferme
  if (overlayWrap) {
    overlayWrap.classList.remove("show");
  }

  try {
    const response = await fetch("http://127.0.0.1:8000/analyze", {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      throw new Error("Erreur lors de l'analyse de l'image");
    }

    const data = await response.json();
    const metrics = data.metrics || {};
    const overlayBase64 = data.overlay_base64;

    // 1) Tableau metrics
    renderMetricsTable(metrics);

    // 2) Overlay
    if (overlayImg) {
      if (overlayBase64 && overlayBase64.length > 0) {
        overlayImg.src = `data:image/png;base64,${overlayBase64}`;
        overlayImg.classList.remove("d-none");
        overlayImg.alt = "Overlay résultat";
      } else {
        overlayImg.alt = "Overlay non disponible";
        overlayImg.classList.add("d-none");
      }
    }

  } catch (error) {
    console.error(error);

    if (resultsBody) {
      resultsBody.innerHTML = `
        <tr>
          <td colspan="2">
            <div class="alert alert-danger mb-0">Erreur : ${error.message}</div>
          </td>
        </tr>
      `;
    }
  } finally {
    if (loading) loading.classList.add("d-none");
  }
}
