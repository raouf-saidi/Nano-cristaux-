async function analyze() {
  const input = document.getElementById("imageInput");
  const resultsPre = document.getElementById("results");
  const overlayImg = document.getElementById("overlay");
  const loading = document.getElementById("loading");

  if (!input.files || input.files.length === 0) {
    alert("Veuillez choisir une image !");
    return;
  }

  const file = input.files[0];
  const formData = new FormData();
  formData.append("image", file);

  // Reset affichage
  loading.classList.remove("d-none");
  resultsPre.textContent = "";
  overlayImg.src = "";

  try {
    const response = await fetch("http://127.0.0.1:8000/analyze", {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      throw new Error("Erreur lors de l'analyse de l'image");
    }

    const data = await response.json();
    const metrics = data.metrics;
    const overlayBase64 = data.overlay_base64;

    // 1) Afficher l’image overlay
    if (overlayBase64 && overlayBase64.length > 0) {
      overlayImg.src = `data:image/png;base64,${overlayBase64}`;
    } else {
      overlayImg.alt = "Overlay non disponible";
    }

    // 2) Générer un tableau HTML avec les métriques
    const rows = [
      ["Nom image", metrics.image],
      ["Grossissement (mag)", metrics.mag ?? "N/A"],
      ["Image valide", metrics.good_image],
      ["Pontage réussi", metrics.bridging_success],
      ["Total cristaux", metrics.n_cristaux_total],
      ["Cristaux pontants", metrics.n_cristaux_pontage],
      ["% pontants", metrics.pct_cristaux_pontage != null ? (metrics.pct_cristaux_pontage * 100).toFixed(2) + "%" : "N/A"],
      ["Nombre grains", metrics.n_grains],
      ["Sharpness (Laplacian)", metrics.sharpness_laplacian_var != null ? metrics.sharpness_laplacian_var.toFixed(2) : "N/A"],
      ["Contraste", metrics.contrast_range != null ? metrics.contrast_range.toFixed(2) : "N/A"],
      ["Coverage total", metrics.coverage_all != null ? metrics.coverage_all.toFixed(4) : "N/A"],
      ["Coverage pontage", metrics.coverage_bridging != null ? metrics.coverage_bridging.toFixed(4) : "N/A"],
      ["Score pontage", metrics.bridging_strength_score != null ? metrics.bridging_strength_score.toFixed(4) : "N/A"],
      ["Raisons (si image invalide)", metrics.reasons || ""],
    ];

    // Tableau Bootstrap
    let tableHtml = `
      <div class="table-responsive">
        <table class="table table-sm table-bordered align-middle mt-3">
          <thead class="table-dark">
            <tr>
              <th>Indicateur</th>
              <th>Valeur</th>
            </tr>
          </thead>
          <tbody>
    `;

    for (const [k, v] of rows) {
      tableHtml += `
        <tr>
          <td><strong>${k}</strong></td>
          <td>${v}</td>
        </tr>
      `;
    }

    tableHtml += `
          </tbody>
        </table>
      </div>
    `;

    // Injecter le tableau dans le <pre> (mieux : remplacer <pre> par <div>)
    resultsPre.innerHTML = tableHtml;

  } catch (error) {
    console.error(error);
    resultsPre.innerHTML = `<div class="alert alert-danger mt-3">Erreur: ${error.message}</div>`;
  } finally {
    loading.classList.add("d-none");
  }
}
