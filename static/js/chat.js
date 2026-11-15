const log = document.getElementById("log");
const replies = document.getElementById("replies");
const form = document.getElementById("composer");
const input = document.getElementById("message");
let csrf = "";
let busy = false;

function stamp() {
  const time = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
  }).format(new Date());
  return time + " ET";
}

function addMessage(role, text, time) {
  const item = document.createElement("li");
  item.className = role === "user" ? "user" : "bot";
  const bubble = document.createElement("p");
  bubble.textContent = text;
  const meta = document.createElement("time");
  meta.dateTime = new Date().toISOString();
  meta.textContent = time || stamp();
  item.append(bubble, meta);
  log.append(item);
  log.scrollTop = log.scrollHeight;
}

function setButtons(buttons) {
  replies.replaceChildren();
  (buttons || []).forEach((button) => {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = button.label;
    element.addEventListener("click", () => send(button.label, button.id));
    replies.append(element);
  });
}

function setTyping(on) {
  const existing = document.getElementById("typing");
  if (!on) {
    if (existing) existing.remove();
    return;
  }
  if (existing) return;
  const item = document.createElement("li");
  item.id = "typing";
  item.className = "bot typing";
  item.textContent = "DocBooker is typing";
  log.append(item);
  log.scrollTop = log.scrollHeight;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function send(message, button) {
  if (busy) return;
  busy = true;
  if (message) addMessage("user", message, stamp());
  input.value = "";
  setButtons([]);
  setTyping(true);
  const started = Date.now();
  try {
    const response = await fetch("api/chat", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
      },
      body: JSON.stringify({ message: message || "", button: button || "" }),
    });
    const data = await response.json();
    const wait = 400 - (Date.now() - started);
    if (wait > 0) await sleep(wait);
    setTyping(false);
    if (data.csrf_token) csrf = data.csrf_token;
    if (!response.ok) {
      addMessage("bot", data.error || "The message was rejected.", stamp());
      return;
    }
    (data.messages || []).forEach((item) => addMessage("bot", item.text, item.time));
    setButtons(data.buttons || []);
  } catch (_error) {
    setTyping(false);
    addMessage("bot", "The demo could not reach the local server.", stamp());
  } finally {
    busy = false;
    input.focus();
  }
}

async function start() {
  const response = await fetch("api/bootstrap", { credentials: "same-origin" });
  const data = await response.json();
  csrf = data.csrf_token || "";
  (data.messages || []).forEach((item) => addMessage(item.role || "bot", item.text, item.time));
  setButtons(data.buttons || []);
  input.focus();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  send(text, "");
});

document.getElementById("help").addEventListener("click", () => send("Help", "help"));
document.getElementById("restart").addEventListener("click", () => send("Restart", "restart"));
start();
