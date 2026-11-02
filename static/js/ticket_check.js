/* Admin-only ticket lookup and entry control. */
(() => {
  const form = document.getElementById("ticket-check-form");
  if (!form) return;

  const codeInput = document.getElementById("ticket-code");
  const submitButton = document.getElementById("ticket-check-submit");
  const authorizeButton = document.getElementById("ticket-authorize");
  const resultPanel = document.getElementById("ticket-check-result");
  const resultTitle = document.getElementById("ticket-result-title");
  const resultMessage = document.getElementById("ticket-result-message");
  const resultStatus = document.getElementById("ticket-result-status");
  const resultFacts = document.getElementById("ticket-result-facts");
  const notice = document.getElementById("ticket-check-notice");
  const cameraStart = document.getElementById("ticket-camera-start");
  const cameraStop = document.getElementById("ticket-camera-stop");
  const cameraPanel = document.getElementById("ticket-camera-panel");
  const cameraVideo = document.getElementById("ticket-camera-video");
  const cameraStatus = document.getElementById("ticket-camera-status");
  let currentTicket = null;
  let scanner = null;
  let cameraStream = null;
  let scanFrame = 0;
  let scanInProgress = false;

  function setNotice(message = "", state = "info") {
    notice.textContent = message;
    notice.dataset.state = state;
    notice.hidden = !message;
  }

  function statusLabel(state) {
    return ({
      valid: "Valide",
      used: "Déjà utilisé",
      cancelled: "Annulé",
      not_found: "Billet introuvable",
      authorized: "Entrée autorisée",
      error: "Vérification impossible",
    })[state] || "Billet non valide";
  }

  function showResult(state, title, message = "", ticket = null) {
    resultPanel.hidden = false;
    resultPanel.dataset.state = state;
    resultTitle.textContent = title;
    resultMessage.textContent = message;
    resultStatus.textContent = statusLabel(state);
    resultStatus.className = `status-pill ${state === "valid" ? "status-confirmed" : ""} ${state === "used" || state === "authorized" ? "status-used" : ""} ${state === "cancelled" || state === "not_found" || state === "error" ? "status-cancelled" : ""}`.trim();
    resultFacts.replaceChildren();
    authorizeButton.hidden = !(ticket && state === "valid"
      && ticket.ticket_status === "valid" && ticket.status === "confirmed");

    if (!ticket) return;
    const start = new Date(ticket.start_time);
    const dateText = Number.isNaN(start.getTime())
      ? ticket.start_time
      : start.toLocaleString("fr-FR", {dateStyle: "long", timeStyle: "short"});
    const facts = [
      ["Film", ticket.film_title],
      ["Séance", dateText],
      ["Salle", ticket.room_name],
      ["Places", Array.isArray(ticket.seats) && ticket.seats.length ? ticket.seats.join(", ") : "Aucune place renseignée"],
      ["Réservation", ticket.status === "confirmed" ? "Confirmée" : "Annulée"],
      ["Code du billet", ticket.ticket_code],
    ];
    for (const [label, value] of facts) {
      const row = document.createElement("div");
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = label;
      description.textContent = String(value ?? "—");
      row.append(term, description);
      resultFacts.append(row);
    }
  }

  async function readResponse(response) {
    const body = await response.json().catch(() => ({}));
    return {response, body};
  }

  function showLookupError(status, detail = "") {
    const lowerDetail = String(detail).toLocaleLowerCase("fr");
    if (status === 404) {
      showResult("not_found", "Billet introuvable", "Aucun billet ne correspond à ce code.");
      return;
    }
    if (status === 401) {
      showResult("error", "Session expirée", "Reconnectez-vous avec un compte administrateur puis réessayez.");
      return;
    }
    if (status === 403) {
      showResult("error", "Accès réservé", "La vérification des billets est réservée aux administrateurs.");
      return;
    }
    if (lowerDetail.includes("utilisé")) {
      currentTicket = currentTicket ? {...currentTicket, ticket_status: "used"} : null;
      showResult("used", "Billet déjà utilisé", detail || "Ce billet a déjà été présenté à l’entrée.", currentTicket);
      return;
    }
    if (lowerDetail.includes("annulé") || lowerDetail.includes("annulée")) {
      currentTicket = currentTicket ? {...currentTicket, ticket_status: "cancelled", status: "cancelled"} : null;
      showResult("cancelled", "Billet annulé", detail || "La réservation associée est annulée.", currentTicket);
      return;
    }
    showResult("error", "Vérification impossible", detail || "Le serveur n’a pas pu vérifier ce billet.", currentTicket);
  }

  async function verifyTicket(rawCode) {
    const code = rawCode.trim().toUpperCase();
    if (!code) {
      codeInput.setCustomValidity("Saisissez un code de billet.");
      codeInput.reportValidity();
      codeInput.setCustomValidity("");
      return;
    }
    currentTicket = null;
    resultPanel.hidden = true;
    authorizeButton.hidden = true;
    setNotice("Vérification du billet…");
    submitButton.disabled = true;
    try {
      const {response, body} = await readResponse(await fetch(
        `/api/tickets/${encodeURIComponent(code)}`,
        {headers: {Accept: "application/json"}},
      ));
      if (!response.ok) {
        setNotice("");
        showLookupError(response.status, body.detail);
        return;
      }
      currentTicket = body;
      setNotice("");
      if (body.ticket_status === "cancelled" || body.status !== "confirmed") {
        showResult("cancelled", "Billet annulé", "Cette réservation ne permet pas l’accès à la salle.", body);
      } else if (body.ticket_status === "used") {
        showResult("used", "Billet déjà utilisé", "Ce billet a déjà été présenté à l’entrée.", body);
      } else if (body.ticket_status === "valid" && body.status === "confirmed") {
        showResult("valid", "Billet valide", "Vérifiez les informations avant d’autoriser l’entrée.", body);
      } else {
        showResult("error", "Billet non valide", "Le statut du billet ne permet pas l’accès à la salle.", body);
      }
    } catch {
      setNotice("");
      showResult("error", "Serveur indisponible", "Impossible de vérifier le billet. Vérifiez la connexion puis réessayez.");
    } finally {
      submitButton.disabled = false;
    }
  }

  async function authorizeEntry() {
    if (!currentTicket || currentTicket.ticket_status !== "valid" || currentTicket.status !== "confirmed") return;
    authorizeButton.disabled = true;
    const originalLabel = authorizeButton.textContent;
    authorizeButton.textContent = "Validation…";
    setNotice("Validation auprès du serveur…");
    try {
      const {response, body} = await readResponse(await fetch(
        `/api/tickets/${encodeURIComponent(currentTicket.ticket_code)}/use`,
        {method: "POST", headers: {Accept: "application/json"}},
      ));
      if (!response.ok) {
        setNotice("");
        showLookupError(response.status, body.detail);
        return;
      }
      currentTicket = {...currentTicket, ticket_status: "used"};
      setNotice("");
      showResult("authorized", "Entrée autorisée", body.detail || "Le serveur a validé ce billet.", currentTicket);
    } catch {
      setNotice("");
      showResult("error", "Validation impossible", "La réponse du serveur n’a pas pu être reçue. Vérifiez le statut du billet avant toute nouvelle tentative.", currentTicket);
    } finally {
      authorizeButton.disabled = false;
      authorizeButton.textContent = originalLabel;
      authorizeButton.hidden = currentTicket?.ticket_status !== "valid" || currentTicket?.status !== "confirmed";
    }
  }

  function stopCamera(message = "") {
    if (scanFrame) window.cancelAnimationFrame(scanFrame);
    scanFrame = 0;
    scanInProgress = false;
    cameraStream?.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    cameraVideo.srcObject = null;
    cameraPanel.hidden = true;
    if (message) setNotice(message);
  }

  async function scanNextFrame() {
    if (!cameraStream || !scanner) return;
    if (!scanInProgress && cameraVideo.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      scanInProgress = true;
      try {
        const codes = await scanner.detect(cameraVideo);
        const rawValue = codes[0]?.rawValue?.trim();
        if (rawValue) {
          const prefix = "GRAND-CINEMA:";
          if (!rawValue.toUpperCase().startsWith(prefix)) {
            cameraStatus.textContent = "Ce QR code ne correspond pas à un billet Le Grand Cinéma.";
          } else {
            const code = rawValue.slice(prefix.length).trim();
            stopCamera();
            codeInput.value = code;
            await verifyTicket(code);
            return;
          }
        }
      } catch {
        stopCamera("La lecture caméra a échoué. Vous pouvez saisir le code manuellement.");
        return;
      } finally {
        scanInProgress = false;
      }
    }
    scanFrame = window.requestAnimationFrame(scanNextFrame);
  }

  async function enableCameraScanner() {
    cameraStart.disabled = true;
    cameraStatus.textContent = "Activation de la caméra…";
    try {
      scanner = new window.BarcodeDetector({formats: ["qr_code"]});
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video: {facingMode: {ideal: "environment"}},
        audio: false,
      });
      cameraVideo.srcObject = cameraStream;
      cameraPanel.hidden = false;
      await cameraVideo.play();
      cameraStatus.textContent = "Pointez la caméra vers le QR code du billet.";
      scanFrame = window.requestAnimationFrame(scanNextFrame);
    } catch (error) {
      stopCamera();
      cameraStatus.textContent = error.name === "NotAllowedError"
        ? "Autorisez l’accès à la caméra ou saisissez le code manuellement."
        : "Caméra indisponible. Vous pouvez saisir le code manuellement.";
      cameraPanel.hidden = false;
    } finally {
      cameraStart.disabled = false;
    }
  }

  async function configureScanner() {
    const supported = window.isSecureContext
      && typeof window.BarcodeDetector === "function"
      && Boolean(navigator.mediaDevices?.getUserMedia);
    if (supported && typeof window.BarcodeDetector.getSupportedFormats === "function") {
      try {
        cameraStart.hidden = !(await window.BarcodeDetector.getSupportedFormats()).includes("qr_code");
      } catch {
        cameraStart.hidden = true;
      }
    } else {
      cameraStart.hidden = !supported;
    }
    document.getElementById("ticket-camera-unavailable").hidden = !cameraStart.hidden;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void verifyTicket(codeInput.value);
  });
  authorizeButton.addEventListener("click", () => void authorizeEntry());
  cameraStart.addEventListener("click", () => void enableCameraScanner());
  cameraStop.addEventListener("click", () => stopCamera("Scanner arrêté."));
  window.addEventListener("pagehide", () => stopCamera());
  void configureScanner();
})();
