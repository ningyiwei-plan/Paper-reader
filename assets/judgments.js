function createReaderJudgments(storageKey, announce) {
  const key = storageKey + ":judgments";
  const dialog = document.getElementById("judgments");
  const title = document.getElementById("judgment-title");
  const heading = document.getElementById("open-judgments");
  const count = heading.querySelector("span");
  const list = document.getElementById("judgment-list");
  const form = document.getElementById("judgment-form");
  const source = document.getElementById("judgment-source");
  const quote = document.getElementById("judgment-quote");
  const prompts = document.getElementById("judgment-prompts");
  const empty = document.getElementById("judgment-empty");
  const error = document.getElementById("judgment-error");
  const template = document.getElementById("judgment-item");
  const fields = ["thought", "alternative", "evidence"];
  let notes = JSON.parse(document.getElementById("saved-judgments").textContent);
  try {
    const stored = localStorage.getItem(key);
    if (stored !== null) notes = JSON.parse(stored);
  } catch {
    // Embedded notes stay available if browser storage is restricted.
  }
  notes = Array.isArray(notes) ? notes.filter((note) =>
    note && ["id", "unit", "source", "quote", ...fields].every((field) => typeof note[field] === "string")
  ) : [];
  let current;
  let returnToList = false;

  const reportCount = () => { count.textContent = notes.length ? " · " + notes.length : ""; };
  reportCount();
  const save = (message) => {
    reportCount();
    document.dispatchEvent(new Event("reader-judgments-change"));
    try {
      localStorage.setItem(key, JSON.stringify(notes));
      announce(message);
    } catch {
      announce("当前浏览器无法保存判断笔记。可导出 HTML 保留本次修改。");
    }
  };
  const showList = () => {
    title.textContent = "判断笔记";
    form.hidden = true;
    list.hidden = false;
    empty.hidden = notes.length > 0;
    const entries = list.querySelector(".judgment-entries");
    entries.replaceChildren();
    for (const note of notes) {
      const item = template.content.firstElementChild.cloneNode(true);
      item.querySelector(".judgment-citation").textContent = note.source;
      const citation = item.querySelector("blockquote");
      citation.textContent = note.quote;
      citation.hidden = !note.quote;
      for (const field of fields) {
        const row = item.querySelector('[data-field="' + field + '"]');
        row.hidden = !note[field];
        row.querySelector("dd").textContent = note[field];
      }
      const link = item.querySelector("a");
      link.hidden = !document.getElementById(note.unit);
      link.setAttribute("href", "#" + encodeURIComponent(note.unit));
      link.addEventListener("click", () => dialog.close());
      item.querySelector("button").addEventListener("click", () => openForm(note, true));
      entries.append(item);
    }
    if (!dialog.open) dialog.showModal();
    document.dispatchEvent(new Event("reader-judgments-render"));
  };
  const openForm = (note, fromList) => {
    current = note;
    returnToList = fromList;
    title.textContent = note.id ? "编辑判断" : "记下判断";
    source.textContent = note.source;
    quote.textContent = note.quote;
    quote.hidden = !note.quote;
    for (const field of fields) form.elements[field].value = note[field] || "";
    prompts.open = Boolean(note.alternative || note.evidence);
    error.textContent = "";
    form.querySelector("[data-delete-judgment]").hidden = !note.id;
    list.hidden = true;
    form.hidden = false;
    if (!dialog.open) dialog.showModal();
    form.elements.thought.focus();
  };
  const newNote = (node, excerpt = "") => {
    const unit = node.closest(".unit");
    const details = [
      unit.closest(".chapter").querySelector("h2").textContent,
      unit.querySelector(".reading h3")?.textContent,
      unit.querySelector(".source-line a").textContent,
    ];
    if (excerpt) {
      const part = node.dataset.part;
      const name = part === "orig" ? "原文" : (node.parentElement.querySelector(".eyebrow")?.textContent || "附录提要");
      details.push(name);
    }
    openForm({ unit: unit.id, source: details.filter(Boolean).join(" · "), quote: excerpt }, false);
  };
  const done = () => returnToList ? showList() : dialog.close();
  heading.addEventListener("click", showList);
  dialog.querySelector("[data-close-judgments]").addEventListener("click", () => dialog.close());
  form.querySelector("[data-cancel-judgment]").addEventListener("click", done);
  document.querySelectorAll(".new-judgment").forEach((button) =>
    button.addEventListener("click", () => newNote(button))
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = Object.fromEntries(fields.map((field) => [field, form.elements[field].value.trim()]));
    if (!Object.values(values).some(Boolean)) {
      error.textContent = "写下一个判断、疑问或待核实的证据。";
      form.elements.thought.focus();
      return;
    }
    const row = { ...current, ...values };
    if (row.id) {
      notes = notes.map((note) => note.id === row.id ? row : note);
    } else {
      row.id = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
      notes.unshift(row);
    }
    done();
    save("已保存判断笔记。");
  });
  form.querySelector("[data-delete-judgment]").addEventListener("click", () => {
    if (!current?.id || !window.confirm("删除这条判断笔记？")) return;
    notes = notes.filter((note) => note.id !== current.id);
    showList();
    save("已删除判断笔记。");
  });
  return {
    newNote,
    entries: () => notes,
    embed(copy) {
      copy.querySelector("#saved-judgments").textContent = JSON.stringify(notes).replaceAll("<", "\\u003c");
      const view = copy.querySelector("#judgments");
      view.removeAttribute("open");
      view.querySelector(".judgment-entries").replaceChildren();
      view.querySelector("#judgment-source").textContent = "";
      view.querySelector("#judgment-quote").textContent = "";
      view.querySelector("#judgment-error").textContent = "";
    },
  };
}
