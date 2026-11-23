function createReaderMarks(storageKey, announce, onJudgment) {
  const toolbar = document.getElementById("mark-tools");
  const seed = document.getElementById("saved-marks");
  const storageName = storageKey + ":marks";
  const kinds = ["highlight", "bold"];
  const blocks = new Map();
  for (const node of document.querySelectorAll("[data-part]")) {
    const key = node.closest(".unit").id + ":" + node.dataset.part;
    blocks.set(key, { node, text: node.textContent });
  }
  let marks = JSON.parse(seed.textContent);
  try {
    const existing = localStorage.getItem(storageName);
    if (existing !== null) marks = JSON.parse(existing);
  } catch {
    // The embedded copy can still be used and exported.
  }
  const valid = (ranges, length) => Array.isArray(ranges) ? ranges.filter((pair) =>
    Array.isArray(pair) && pair.length === 2 && pair.every(Number.isSafeInteger)
    && pair[0] >= 0 && pair[1] <= length && pair[0] < pair[1]
  ) : [];
  const union = (ranges) => {
    const merged = [];
    for (const [start, end] of ranges.slice().sort((a, b) => a[0] - b[0])) {
      const previous = merged.at(-1);
      if (previous && start <= previous[1]) previous[1] = Math.max(end, previous[1]);
      else merged.push([start, end]);
    }
    return merged;
  };
  const clean = {};
  for (const [key, { text }] of blocks) {
    const source = marks?.[key];
    const entry = Object.fromEntries(kinds.map((kind) => [kind, union(valid(source?.[kind], text.length))]));
    if (kinds.some((kind) => entry[kind].length)) clean[key] = entry;
  }
  marks = clean;

  const subtract = (ranges, start, end) => ranges.flatMap(([a, b]) => {
    if (b <= start || a >= end) return [[a, b]];
    const remainders = [];
    if (a < start) remainders.push([a, start]);
    if (b > end) remainders.push([end, b]);
    return remainders;
  });
  const paint = (key) => {
    const { text, node } = blocks.get(key);
    const ranges = marks[key];
    if (!ranges) {
      node.textContent = text;
      return;
    }
    const boundaries = new Set([0, text.length]);
    for (const kind of kinds) for (const pair of ranges[kind]) pair.forEach((n) => boundaries.add(n));
    const steps = Array.from(boundaries).sort((a, b) => a - b);
    const fragment = document.createDocumentFragment();
    for (let i = 1; i < steps.length; i++) {
      const [start, end] = [steps[i - 1], steps[i]];
      const value = text.slice(start, end);
      const styles = kinds.filter((kind) => ranges[kind].some(([a, b]) => a <= start && end <= b));
      if (styles.length) {
        const span = document.createElement("span");
        span.className = styles.map((kind) => "reader-" + kind).join(" ");
        span.textContent = value;
        fragment.append(span);
      } else {
        fragment.append(value);
      }
    }
    node.replaceChildren(fragment);
  };
  for (const key of Object.keys(marks)) paint(key);

  let selected = null;
  const hide = () => {
    selected = null;
    toolbar.hidden = true;
  };
  const markable = (container) => {
    const element = container.nodeType === Node.ELEMENT_NODE ? container : container.parentElement;
    return element?.closest("[data-part]");
  };
  let pending = false;
  document.addEventListener("selectionchange", () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.rangeCount || !selection.toString().trim()) return hide();
      const range = selection.getRangeAt(0);
      const node = markable(range.startContainer);
      if (!node || node !== markable(range.endContainer)) return hide();
      const key = node.closest(".unit").id + ":" + node.dataset.part;
      const prefix = document.createRange();
      prefix.selectNodeContents(node);
      prefix.setEnd(range.startContainer, range.startOffset);
      const start = prefix.toString().length;
      prefix.setEnd(range.endContainer, range.endOffset);
      const end = prefix.toString().length;
      if (end <= start) return hide();
      selected = { key, start, end };
      const box = range.getBoundingClientRect();
      toolbar.hidden = false;
      const left = Math.min(Math.max(6, box.left), window.innerWidth - toolbar.offsetWidth - 6);
      const top = box.top > toolbar.offsetHeight + 8 ? box.top - toolbar.offsetHeight - 6 : box.bottom + 6;
      toolbar.style.left = Math.max(left, 0) + "px";
      toolbar.style.top = Math.max(4, Math.min(top, window.innerHeight - toolbar.offsetHeight - 6)) + "px";
    });
  });
  window.addEventListener("scroll", hide, { passive: true });
  window.addEventListener("resize", hide);
  toolbar.addEventListener("mousedown", (event) => event.preventDefault());
  toolbar.addEventListener("click", (event) => {
    const action = event.target.closest("[data-mark]")?.dataset.mark;
    if (!action || !selected) return;
    const { key, start, end } = selected;
    if (action === "judge") {
      const { node, text } = blocks.get(key);
      window.getSelection().removeAllRanges();
      hide();
      onJudgment(node, text.slice(start, end).trim());
      return;
    }
    const entry = marks[key] || { highlight: [], bold: [] };
    if (action === "clear") {
      for (const kind of kinds) entry[kind] = subtract(entry[kind], start, end);
    } else if (kinds.includes(action)) {
      const covered = entry[action].some(([a, b]) => a <= start && end <= b);
      entry[action] = covered ? subtract(entry[action], start, end) : union([...entry[action], [start, end]]);
    }
    if (kinds.some((kind) => entry[kind].length)) marks[key] = entry;
    else delete marks[key];
    window.getSelection().removeAllRanges();
    hide();
    paint(key);
    try {
      localStorage.setItem(storageName, JSON.stringify(marks));
    } catch {
      announce("浏览器无法保存标记。请导出 HTML 保留本次标记。");
    }
  });
  return (copy) => {
    copy.querySelector("#saved-marks").textContent = JSON.stringify(marks).replaceAll("<", "\\u003c");
    copy.querySelector("#mark-tools").hidden = true;
    for (const node of copy.querySelectorAll("[data-part]")) node.textContent = node.textContent;
  };
}
