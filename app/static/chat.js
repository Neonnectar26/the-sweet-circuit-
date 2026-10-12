/* Live chat client for a Sweet Circuit room. Vanilla JS, no build step. */
(function () {
  var chat = document.getElementById("chat");
  if (!chat) return;
  var roomSlug = chat.dataset.room;
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var speakAs = document.getElementById("speak-as");

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function timeStr(ts) {
    var d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function renderMessage(m) {
    var div = document.createElement("div");
    div.className = "msg" + (m.author_type === "bot" ? " bot" : "");
    div.id = "msg-" + m.id;
    var badge = m.badge ? '<span class="badge">' + esc(m.badge) + "</span>" : "";
    var reportBtn = form
      ? ' <button class="report" data-id="' + m.id + '" title="Report message">report</button>'
      : "";
    div.innerHTML =
      '<span class="avatar">' + esc(m.avatar) + "</span>" +
      '<span class="who">' + esc(m.author) + badge + "</span>" +
      '<span class="time">' + esc(timeStr(m.created_at)) + "</span>" +
      reportBtn +
      "<div>" + esc(m.body) + "</div>";
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }

  chat.addEventListener("click", function (e) {
    var btn = e.target.closest(".report");
    if (!btn) return;
    var reason = prompt("Why are you reporting this message?");
    if (reason === null) return;
    var f = document.createElement("form");
    f.method = "POST";
    f.action = "/messages/" + btn.dataset.id + "/report";
    var i = document.createElement("input");
    i.type = "hidden"; i.name = "reason"; i.value = reason;
    f.appendChild(i);
    document.body.appendChild(f);
    f.submit();
  });

  var proto = location.protocol === "https:" ? "wss:" : "ws:";
  var ws = new WebSocket(proto + "//" + location.host + "/ws/" + roomSlug);

  ws.onmessage = function (ev) {
    var data = JSON.parse(ev.data);
    if (data.type === "history") {
      chat.innerHTML = "";
      data.messages.forEach(renderMessage);
    } else if (data.type === "message") {
      renderMessage(data.message);
    } else if (data.type === "error") {
      alert(data.error);
    }
  };

  ws.onclose = function () {
    var div = document.createElement("div");
    div.className = "dim";
    div.textContent = "— disconnected. Reload to rejoin. —";
    chat.appendChild(div);
  };

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var body = input.value.trim();
      if (!body || ws.readyState !== WebSocket.OPEN) return;
      var payload = { body: body };
      if (speakAs && speakAs.value) payload.as_bot = parseInt(speakAs.value, 10);
      ws.send(JSON.stringify(payload));
      input.value = "";
      input.focus();
    });
  }
})();
