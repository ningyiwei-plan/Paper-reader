function createReaderSearch(chapters, links, judgments, updateToc) {
  const form = document.querySelector(".reader-search");
  const { query, chapter, kind } = form.elements;
  const count = form.querySelector(".search-count");
  chapter.replaceChildren(new Option("全部章节", ""));
  const normalize = (text) => text.normalize("NFKC").toLowerCase().replace(/\s+/g, " ").trim();
  const sections = chapters.map((section) => {
    const heading = section.querySelector(".chapter-heading");
    chapter.add(new Option(heading.querySelector("h2").textContent, section.id));
    const units = Array.from(section.querySelectorAll(".unit"), (node) => ({
      node,
      note: node.querySelector("textarea"),
      text: normalize([heading.textContent, ...Array.from(
        node.querySelectorAll(".reading h3, .source-line a, .markable, .figure-trigger img"),
        (element) => element.alt || element.textContent
      )].join(" ")),
    }));
    return { section, units };
  });
  const total = sections.reduce((sum, entry) => sum + entry.units.length, 0);
  let active = false;
  const update = () => {
    const words = normalize(query.value).split(" ").filter(Boolean);
    active = Boolean(words.length || chapter.value || kind.value);
    const judgmentText = new Map();
    if (words.length || kind.value === "notes") {
      for (const note of judgments.entries()) {
        judgmentText.set(note.unit, [judgmentText.get(note.unit) || "", note.quote,
          note.thought, note.alternative, note.evidence].join(" "));
      }
    }
    let visible = 0;
    sections.forEach(({ section, units }, index) => {
      let found = 0;
      for (const { node, note, text } of units) {
        const annotations = normalize(note.value + " " + (judgmentText.get(node.id) || ""));
        const matchesKind = !kind.value || node.dataset.kind === kind.value
          || (kind.value === "appendix" && section.hasAttribute("data-appendix"))
          || (kind.value === "notes" && Boolean(annotations));
        const matches = (!chapter.value || chapter.value === section.id) && matchesKind
          && words.every((word) => text.includes(word) || annotations.includes(word));
        node.hidden = !matches;
        if (matches) found++;
      }
      section.hidden = links[index].hidden = found === 0;
      visible += found;
    });
    count.textContent = !visible ? "没有匹配内容，请更换关键词或清除筛选。"
      : active ? `${visible} 条匹配 · 共 ${total} 个内容块` : `共 ${total} 个内容块`;
    updateToc();
  };
  const clear = () => {
    query.value = chapter.value = kind.value = "";
    update();
  };
  form.addEventListener("input", (event) => { if (!event.isComposing) update(); });
  query.addEventListener("compositionend", update);
  form.addEventListener("submit", (event) => event.preventDefault());
  form.addEventListener("reset", (event) => { event.preventDefault(); clear(); });
  document.addEventListener("input", (event) => {
    // Defer until the edit completes, so deleting the last letter keeps focus.
    if (active && event.target.matches(".note textarea")) {
      event.target.addEventListener("blur", update, { once: true });
    }
  });
  document.addEventListener("reader-judgments-change", () => { if (active) update(); });
  document.addEventListener("click", (event) => {
    const link = event.target.closest('a[href^="#"]');
    const target = link && document.getElementById(link.hash.slice(1));
    if (target?.closest(".chapter[hidden], .unit[hidden]")) clear();
  });
  form.hidden = false;
  clear();
}
