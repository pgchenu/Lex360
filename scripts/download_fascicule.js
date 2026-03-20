/**
 * Script pour télécharger un fascicule depuis Lexis 360 Intelligence.
 *
 * USAGE — à coller dans la console du navigateur (DevTools, F12)
 * sur une page lexis360intelligence.fr où vous êtes connecté :
 *
 *   1. Ouvrir la console (F12 > Console)
 *   2. Copier-coller ce script
 *   3. Appeler : downloadFascicule("EN_KEJC-238100_0KR8")
 *
 * Le script utilise le access_token du localStorage + les cookies de session
 * du navigateur (indispensables, l'API refuse les appels sans cookies).
 */

async function downloadFascicule(docId, filename) {
  const token = localStorage.getItem("access_token");
  if (!token) {
    console.error("Pas de access_token dans le localStorage. Êtes-vous connecté ?");
    return;
  }

  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  // 1. Récupérer les métadonnées
  console.log(`[1/3] Récupération des métadonnées de ${docId}...`);
  const metaRes = await fetch(`/api/document/metadata/${docId}`, {
    headers,
    credentials: "include",
  });
  if (!metaRes.ok) {
    console.error(`Erreur metadata: ${metaRes.status}`);
    return;
  }
  const meta = await metaRes.json();
  console.log(`  Titre : ${meta.document?.title}`);
  console.log(`  Type  : ${meta.document?.type}`);
  if (meta.encyclo) {
    console.log(`  Encyclopédie : ${meta.encyclo.codePublicationLabel}`);
    console.log(`  Auteur(s)    : ${meta.encyclo.auteur?.join(", ")}`);
  }

  // 2. Récupérer le contenu (SSE text/event-stream → HTML)
  console.log(`[2/3] Récupération du contenu...`);
  const recRes = await fetch(`/api/document/records/${docId}`, {
    headers,
    credentials: "include",
  });
  if (!recRes.ok) {
    console.error(`Erreur records: ${recRes.status}`);
    return;
  }
  const raw = await recRes.text();

  // Parser le format SSE : extraire les lignes "data: ..."
  const html = raw
    .split("\n")
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.substring(6))
    .join("");

  console.log(`  Contenu récupéré : ${(html.length / 1024).toFixed(0)} Ko`);

  // 3. Télécharger le fichier
  const defaultName = (meta.document?.title || docId)
    .replace(/[/:*?"<>|]/g, "_")
    .replace(/\s+/g, "_");
  const fname = filename || `${defaultName}.html`;

  console.log(`[3/3] Téléchargement : ${fname}`);
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fname;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  console.log("Terminé !");
  return { meta, contentLength: html.length };
}

/**
 * Télécharger par recherche (nom d'encyclopédie + numéro de fascicule).
 *
 * USAGE :
 *   downloadBySearch("Alsace Moselle", "212")
 */
async function downloadBySearch(encyclopedieName, fasciculeNumber) {
  const token = localStorage.getItem("access_token");
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  console.log(
    `Recherche : fascicule ${fasciculeNumber} de ${encyclopedieName}...`
  );

  const searchRes = await fetch("/api/recherche//search", {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify({
      q: `JurisClasseur ${encyclopedieName} fascicule ${fasciculeNumber}`,
      project: "all",
      highlight: false,
      offset: 0,
      size: 5,
      from: "0",
      to: String(Date.now()),
      filters: [{ name: "typeDoc", values: ["DOCTRINE_FASCICULE"] }],
      sorts: [{ field: "SCORE", order: "DESC" }],
      aggregations: [],
      relevanceProfile: null,
      combining: null,
      fields: null,
    }),
  });

  const searchData = await searchRes.json();
  const hits = searchData.data?.hits || [];

  if (hits.length === 0) {
    console.error("Aucun résultat trouvé.");
    return;
  }

  console.log(`${hits.length} résultat(s) :`);
  hits.forEach((h, i) => {
    console.log(`  [${i}] ${h.source?.document?.title} (${h.id})`);
  });

  const docId = hits[0].id;
  console.log(`\nTéléchargement du premier résultat : ${docId}`);
  return downloadFascicule(docId);
}

// Exemples d'utilisation (décommenter) :
// downloadFascicule("EN_KEJC-238100_0KR8");
// downloadBySearch("Alsace Moselle", "212");

console.log("Script chargé. Utilisez :");
console.log('  downloadFascicule("EN_KEJC-238100_0KR8")');
console.log('  downloadBySearch("Alsace Moselle", "212")');
