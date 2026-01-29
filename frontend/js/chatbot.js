const API_BASE = "http://127.0.0.1:8000";
const CHAT_ENDPOINT = `${API_BASE}/llm_chat`;

const STORAGE_KEY_CHAT = "biocimentation_llm_chat_v1";
const STORAGE_KEY_FEEDBACK = "biocimentation_llm_feedback_v1";

let chatHistory = [];   // [{role, content}]
let feedbackLog = [];   // [{id, ts, rating, verdict, question, answer, correction, tags, imageName}]

let pendingFeedback = null; // {answerIndex, questionText, answerText, imageName}

function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_CHAT);
    chatHistory = raw ? JSON.parse(raw) : [];
  } catch {
    chatHistory = [];
  }
}

function saveHistory() {
  localStorage.setItem(STORAGE_KEY_CHAT, JSON.stringify(chatHistory));
}

function loadFeedback() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_FEEDBACK);
    feedbackLog = raw ? JSON.parse(raw) : [];
  } catch {
    feedbackLog = [];
  }
}

function saveFeedback() {
  localStorage.setItem(STORAGE_KEY_FEEDBACK, JSON.stringify(feedbackLog));
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function scrollChatToBottom() {
  const box = document.getElementById("chatMessages");
  if (box) box.scrollTop = box.scrollHeight;
}

/* ===== LEFT PREVIEW (remplace les exemples) ===== */
function setLeftPreview(file) {
  const wrapPreview = document.getElementById("leftPreviewWrap");
  const wrapExamples = document.getElementById("leftExamplesWrap");
  const img = document.getElementById("leftPreviewImg");
  const name = document.getElementById("leftPreviewName");

  if (!wrapPreview || !wrapExamples || !img || !name) return;

  if (!file) {
    wrapPreview.classList.add("d-none");
    wrapExamples.classList.remove("d-none");
    img.src = "";
    name.textContent = "";
    return;
  }

  wrapExamples.classList.add("d-none");
  wrapPreview.classList.remove("d-none");
  img.src = URL.createObjectURL(file);
  name.textContent = file.name;
}

/* ===== Feedback helpers ===== */
function getLastUserQuestionBeforeAnswer(answerIndex) {
  // cherche en arrière le dernier message user avant cet answerIndex
  for (let i = answerIndex - 1; i >= 0; i--) {
    if (chatHistory[i]?.role === "user") return chatHistory[i].content;
  }
  return "";
}

function getCurrentImageName() {
  const imageInput = document.getElementById("chatImageInput");
  const file = imageInput?.files?.[0];
  return file ? file.name : "";
}

function exportFeedbackJSON() {
  const blob = new Blob([JSON.stringify(feedbackLog, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "biocimentation_feedback.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ===== CHAT UI ===== */
function addMessageToUI(role, text, meta = {}) {
  const box = document.getElementById("chatMessages");
  if (!box) return;

  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role === "user" ? "chat-user" : "chat-assistant"}`;

  const who = role === "user" ? "Vous" : "IA";

  const contentHtml =
    role === "assistant" && window.marked
      ? window.marked.parse(text)
      : `<div>${escapeHtml(text)}</div>`;

  bubble.innerHTML = `
    <div class="chat-meta">${who}</div>
    <div class="chat-text">${contentHtml}</div>
  `;

  // Actions feedback uniquement pour les messages assistant
  if (role === "assistant") {
    const answerIndex = meta.answerIndex; // index dans chatHistory
    const actions = document.createElement("div");
    actions.className = "chat-actions";

    actions.innerHTML = `
      <button type="button" class="fb-like" title="Réponse correcte / utile">👍</button>
      <button type="button" class="fb-dislike" title="Réponse incorrecte / à corriger">👎</button>
      <button type="button" class="fb-correct" title="Ajouter une correction">Corriger</button>
    `;

    const btnLike = actions.querySelector(".fb-like");
    const btnDislike = actions.querySelector(".fb-dislike");
    const btnCorrect = actions.querySelector(".fb-correct");

    btnLike.addEventListener("click", () => {
      // enregistre un feedback simple
      const q = getLastUserQuestionBeforeAnswer(answerIndex);
      const record = {
        id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random(),
        ts: new Date().toISOString(),
        verdict: "like",
        rating: 5,
        question: q,
        answer: text,
        correction: "",
        tags: [],
        imageName: getCurrentImageName(),
      };
      feedbackLog.push(record);
      saveFeedback();

      btnLike.classList.add("active-like");
      btnDislike.classList.remove("active-like");
    });

    btnDislike.addEventListener("click", () => {
      const q = getLastUserQuestionBeforeAnswer(answerIndex);
      const record = {
        id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random(),
        ts: new Date().toISOString(),
        verdict: "dislike",
        rating: 1,
        question: q,
        answer: text,
        correction: "",
        tags: [],
        imageName: getCurrentImageName(),
      };
      feedbackLog.push(record);
      saveFeedback();

      btnDislike.classList.add("active-like");
      btnLike.classList.remove("active-like");
    });

    btnCorrect.addEventListener("click", () => openCorrectionModal(answerIndex, text));

    bubble.appendChild(actions);
  }

  box.appendChild(bubble);
  scrollChatToBottom();
}

function setChatLoading(isLoading) {
  const sendBtn = document.getElementById("chatSendBtn");
  const input = document.getElementById("chatInput");
  if (sendBtn) sendBtn.disabled = isLoading;
  if (input) input.disabled = isLoading;

  const typing = document.getElementById("chatTyping");
  if (typing) typing.classList.toggle("d-none", !isLoading);
}

/* ===== Modal correction ===== */
function openCorrectionModal(answerIndex, answerText) {
  const q = getLastUserQuestionBeforeAnswer(answerIndex);
  const imageName = getCurrentImageName();

  pendingFeedback = { answerIndex, questionText: q, answerText, imageName };

  document.getElementById("fbQuestion").textContent = q || "(pas de question trouvée)";
  document.getElementById("fbAnswer").textContent = answerText || "";
  document.getElementById("fbCorrection").value = "";
  document.getElementById("fbTags").value = "";
  document.getElementById("fbRating").value = "3";

  const modalEl = document.getElementById("feedbackModal");
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  modal.show();
}

function saveCorrectionFromModal() {
  if (!pendingFeedback) return;

  const correction = document.getElementById("fbCorrection").value.trim();
  const tagsRaw = document.getElementById("fbTags").value.trim();
  const rating = parseInt(document.getElementById("fbRating").value || "3", 10);

  const tags = tagsRaw
    ? tagsRaw.split(",").map(s => s.trim()).filter(Boolean)
    : [];

  const record = {
    id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random(),
    ts: new Date().toISOString(),
    verdict: "corrected",
    rating,
    question: pendingFeedback.questionText,
    answer: pendingFeedback.answerText,
    correction,
    tags,
    imageName: pendingFeedback.imageName,
  };

  feedbackLog.push(record);
  saveFeedback();

  pendingFeedback = null;

  const modalEl = document.getElementById("feedbackModal");
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  modal.hide();
}

/* ===== init ===== */
function initChatbot() {
  loadHistory();
  loadFeedback();

  // replay chat
  const box = document.getElementById("chatMessages");
  if (box) box.innerHTML = "";

  chatHistory.forEach((m, idx) => {
    addMessageToUI(m.role, m.content, m.role === "assistant" ? { answerIndex: idx } : {});
  });

  // Enter = send (Shift+Enter = newline)
  const input = document.getElementById("chatInput");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
  }

  // Preview à gauche quand on choisit une image
  const imageInput = document.getElementById("chatImageInput");
  if (imageInput) {
    imageInput.addEventListener("change", () => {
      const file = imageInput.files?.[0] || null;
      setLeftPreview(file);
    });
  }

  // Bouton "Retirer l’image"
  const clearImgBtn = document.getElementById("leftPreviewClear");
  if (clearImgBtn) {
    clearImgBtn.addEventListener("click", () => {
      const imageInput = document.getElementById("chatImageInput");
      if (imageInput) imageInput.value = "";
      setLeftPreview(null);
    });
  }

  // clear history
  const clearBtn = document.getElementById("chatClearBtn");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      chatHistory = [];
      saveHistory();
      const box = document.getElementById("chatMessages");
      if (box) box.innerHTML = "";
    });
  }

  // bouton save modal
  const fbSaveBtn = document.getElementById("fbSaveBtn");
  if (fbSaveBtn) {
    fbSaveBtn.addEventListener("click", saveCorrectionFromModal);
  }

  // (optionnel) export avec Ctrl+E
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "e") {
      e.preventDefault();
      exportFeedbackJSON();
    }
  });
}

/* ===== send message ===== */
async function sendChatMessage() {
  const input = document.getElementById("chatInput");
  const imageInput = document.getElementById("chatImageInput");

  const text = input?.value?.trim();
  if (!text) return;

  // UI + state user
  addMessageToUI("user", text);
  chatHistory.push({ role: "user", content: text });
  saveHistory();
  input.value = "";

  setChatLoading(true);

  try {
    const fd = new FormData();
    fd.append("message", text);
    fd.append("history_json", JSON.stringify(chatHistory));

    const file = imageInput?.files?.[0];
    if (file) fd.append("image", file);

    const res = await fetch(CHAT_ENDPOINT, { method: "POST", body: fd });
    if (!res.ok) throw new Error("Erreur API LLM");

    const data = await res.json();
    const reply = data.reply ?? "Réponse non disponible.";

    // assistant
    chatHistory.push({ role: "assistant", content: reply });
    saveHistory();

    // add UI with index = last
    addMessageToUI("assistant", reply, { answerIndex: chatHistory.length - 1 });

  } catch (err) {
    console.error(err);
    const msg = "Désolé, une erreur est survenue pendant l’appel IA.";
    chatHistory.push({ role: "assistant", content: msg });
    saveHistory();
    addMessageToUI("assistant", msg, { answerIndex: chatHistory.length - 1 });
  } finally {
    setChatLoading(false);
    // on garde l'image (preview gauche) tant que l'utilisateur ne la retire pas
  }
}

window.initChatbot = initChatbot;
window.sendChatMessage = sendChatMessage;
window.exportFeedbackJSON = exportFeedbackJSON;