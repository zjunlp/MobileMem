(() => {
  const applicationData = globalThis.MobileMemApplicationData;
  const storageKey = "mobilemem-portrait-review-v2";
  const selected = new Set(JSON.parse(localStorage.getItem(storageKey) || "[]"));
  const content = document.querySelector("#review-content");
  const selectionCount = document.querySelector("#selection-count");

  const users = applicationData.users.map((id, index) => ({
    id,
    label:
      index < 3
        ? `中文用户 ${String.fromCharCode(65 + index)}`
        : `English user ${String.fromCharCode(62 + index)}`,
  }));

  const candidatesFor = (user) => [
    ...applicationData.sourceIdentityLabels[user.id].person.slice(1).map((name, index) => ({
      id: `${user.id}-person-${String(index + 2).padStart(2, "0")}`,
      name,
      source: "人物参考",
      path: applicationData.resolveSourceAssetPath(user.id, "person", index + 2),
    })),
    ...applicationData.sourceIdentityLabels[user.id].group_chat_members.map((name, index) => ({
      id: `${user.id}-member-${String(index + 1).padStart(2, "0")}`,
      name,
      source: "群成员",
      path: applicationData.resolveSourceAssetPath(user.id, "group_chat_members", index + 1),
    })),
  ];

  const updateSelection = () => {
    localStorage.setItem(storageKey, JSON.stringify([...selected]));
    selectionCount.textContent = String(selected.size);
  };

  const candidateCard = (user, candidate) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `candidate-card${selected.has(candidate.id) ? " is-selected" : ""}`;
    card.dataset.candidateId = candidate.id;
    card.setAttribute("aria-pressed", String(selected.has(candidate.id)));
    card.setAttribute(
      "aria-label",
      `${user.label}，${candidate.name}，${candidate.source}，编号 ${candidate.id}`,
    );
    card.innerHTML = `
      <span class="candidate-image"><img src="${candidate.path}" alt="${candidate.name}" loading="lazy"></span>
      <span class="candidate-meta"><span class="candidate-source">${candidate.source}</span><span class="candidate-code">${candidate.id}</span></span>
      <strong>${candidate.name}</strong>
      <span class="candidate-check" aria-hidden="true">✓</span>
    `;
    return card;
  };

  const render = () => {
    content.replaceChildren(
      ...users.map((user) => {
        const protagonistName = applicationData.sourceIdentityLabels[user.id].person[0];
        const protagonistPath = applicationData.resolveSourceAssetPath(user.id, "person", 1);
        const candidates = candidatesFor(user);
        const section = document.createElement("section");
        section.className = "user-section";
        section.innerHTML = `
          <header class="user-heading">
            <h2>${user.label}</h2>
            <span>${user.id}</span>
          </header>
          <div class="user-review">
            <aside class="protagonist-card" aria-label="${user.label}的主角头像">
              <span class="protagonist-label">主角 · 固定对照</span>
              <img src="${protagonistPath}" alt="${protagonistName}" loading="lazy">
              <strong>${protagonistName}</strong>
              <span>${user.id}-person-01</span>
            </aside>
            <div class="candidate-panel">
              <div class="candidate-heading">
                <strong>同一 UID 候选</strong>
                <span>${candidates.length} 张</span>
              </div>
              <div class="candidate-grid"></div>
            </div>
          </div>
        `;

        const grid = section.querySelector(".candidate-grid");
        grid.append(...candidates.map((candidate) => candidateCard(user, candidate)));
        return section;
      }),
    );
  };

  content.addEventListener("click", (event) => {
    const card = event.target.closest("[data-candidate-id]");
    if (!card) return;

    const { candidateId: id } = card.dataset;
    if (selected.has(id)) selected.delete(id);
    else selected.add(id);
    card.classList.toggle("is-selected", selected.has(id));
    card.setAttribute("aria-pressed", String(selected.has(id)));
    updateSelection();
  });

  document.querySelector("#copy-selection").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const text = [...selected].sort().join("\n") || "尚未选择图片";
    await navigator.clipboard.writeText(text);
    button.textContent = "已复制";
    window.setTimeout(() => {
      button.textContent = "复制编号";
    }, 1200);
  });

  document.querySelector("#clear-selection").addEventListener("click", () => {
    selected.clear();
    updateSelection();
    render();
  });

  updateSelection();
  render();
})();
