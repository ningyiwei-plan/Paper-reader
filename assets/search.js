const foldReaderSearch = (text) => text.normalize("NFKC").toLowerCase().replaceAll("ς", "σ");
const readerGraphemes = typeof Intl.Segmenter === "function" ? new Intl.Segmenter() : null;

function readerMatchOffsets(text, words) {
  const folded = foldReaderSearch(text);
  if (!words.some((word) => folded.includes(word))) return [];
  const starts = [], ends = [];
  const segments = readerGraphemes ? readerGraphemes.segment(text)
    : Array.from(text.matchAll(/[\s\S]\p{M}*/gu), (match) => ({ segment: match[0], index: match.index }));
  for (const { segment, index } of segments) {
    const size = foldReaderSearch(segment).length;
    for (let i = 0; i < size; i++) {
      starts.push(index);
      ends.push(index + segment.length);
    }
  }
  const matches = [];
  for (const word of words) {
    for (let i = folded.indexOf(word); i !== -1; i = folded.indexOf(word, i + word.length)) {
      matches.push([starts[i], ends[i + word.length - 1]]);
    }
  }
  return matches.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
}

function addReaderSearchRanges(highlight, element, words) {
  const offsets = readerMatchOffsets(element.textContent, words);
  if (!offsets.length) return;
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let start = 0;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.length) continue;
    nodes.push({ node, start, end: start + node.length });
    start += node.length;
  }
  // A hit can cross text nodes when the reader marked part of the same word.
  for (const [from, to] of offsets) {
    const first = nodes.find(({ end }) => from < end);
    const last = nodes.find(({ end }) => to <= end);
    if (!first || !last) continue;
    const range = document.createRange();
    range.setStart(first.node, from - first.start);
    range.setEnd(last.node, to - last.start);
    highlight.add(range);
  }
}

function createReaderSearch(chapters, links, judgments, updateToc) {
  const form = document.querySelector(".reader-search");
  const { query, chapter, kind } = form.elements;
  const count = form.querySelector(".search-count");
  chapter.replaceChildren(new Option("全部章节", ""));
  const sections = chapters.map((section) => {
    const heading = section.querySelector(".chapter-heading");
    chapter.add(new Option(heading.querySelector("h2").textContent, section.id));
    const units = Array.from(section.querySelectorAll(".unit"), (node) => {
      const fields = Array.from(node.querySelectorAll(".reading h3, .source-line a, .markable"));
      const alt = node.querySelector(".figure-trigger img")?.alt || "";
      return {
        node, fields, note: node.querySelector("textarea"),
        text: foldReaderSearch([heading.textContent, alt, ...fields.map((field) => field.textContent)].join(" ")),
      };
    });
    return { section, heading, units };
  });
  const total = sections.reduce((sum, entry) => sum + entry.units.length, 0);
  let active = false;
  const update = () => {
    const words = [...new Set(foldReaderSearch(query.value).split(/\s+/).filter(Boolean))];
    active = Boolean(words.length || chapter.value || kind.value);
    const highlight = words.length && globalThis.CSS?.highlights ? new Highlight() : null;
    globalThis.CSS?.highlights?.delete("paper-reader-search");
    document.querySelectorAll(".search-note-hits").forEach((node) => node.remove());
    const judgmentFields = new Map();
    if (words.length || kind.value === "notes") {
      for (const note of judgments.entries()) {
        const fields = judgmentFields.get(note.unit) || [];
        fields.push(note.quote, note.thought, note.alternative, note.evidence);
        judgmentFields.set(note.unit, fields);
      }
    }
    let visible = 0;
    sections.forEach(({ section, heading, units }, index) => {
      let found = 0;
      for (const { node, note, fields, text } of units) {
        const judgments = judgmentFields.get(node.id) || [];
        const annotations = foldReaderSearch([note.value, ...judgments].join(" ")).trim();
        const matchesKind = !kind.value || node.dataset.kind === kind.value
          || (kind.value === "appendix" && section.hasAttribute("data-appendix"))
          || (kind.value === "notes" && Boolean(annotations));
        const matches = (!chapter.value || chapter.value === section.id) && matchesKind
          && words.every((word) => text.includes(word) || annotations.includes(word));
        node.hidden = !matches;
        if (!matches) continue;
        found++;
        if (highlight) {
          fields.forEach((field) => addReaderSearchRanges(highlight, field, words));
          const excerpts = document.createElement("div");
          excerpts.className = "search-note-hits";
          for (const [label, value] of [["我的笔记", note.value], ...judgments.map((item) => ["判断笔记", item])]) {
            const [hit] = readerMatchOffsets(value, words);
            if (!hit) continue;
            const [from, to] = hit;
            const start = Math.max(from - 30, 0);
            const end = Math.min(to + 80, value.length);
            const excerpt = document.createElement("p");
            const name = document.createElement("strong");
            name.textContent = label;
            const body = document.createElement("span");
            body.textContent = (start ? "…" : "") + value.slice(start, end) + (end < value.length ? "…" : "");
            excerpt.append(name, body);
            excerpts.append(excerpt);
            addReaderSearchRanges(highlight, body, words);
          }
          if (excerpts.childElementCount) node.querySelector(".annotation").append(excerpts);
        }
      }
      section.hidden = links[index].hidden = found === 0;
      visible += found;
      if (found && highlight) {
        heading.querySelectorAll("h2, span").forEach((field) => addReaderSearchRanges(highlight, field, words));
        addReaderSearchRanges(highlight, links[index], words);
      }
    });
    if (highlight) {
      document.querySelectorAll(".judgment-entry :is(blockquote, dd)").forEach((field) => {
        addReaderSearchRanges(highlight, field, words);
      });
      CSS.highlights.set("paper-reader-search", highlight);
    }
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
  document.addEventListener("reader-judgments-render", () => { if (query.value.trim()) update(); });
  document.addEventListener("reader-marks-change", () => { if (query.value.trim()) update(); });
  document.addEventListener("click", (event) => {
    const link = event.target.closest('a[href^="#"]');
    const target = link && document.getElementById(link.hash.slice(1));
    if (target?.closest(".chapter[hidden], .unit[hidden]")) clear();
  });
  form.hidden = false;
  clear();
}
