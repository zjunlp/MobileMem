/** MobileMem-Omni paper-result leaderboard. */

(() => {
  const metricOrder = [
    "singleHop",
    "multiHop",
    "knowledgeUpdate",
    "temporalReasoning",
    "abstention",
    "implicitPreference",
    "visualReasoning",
    "llmJudge",
    "f1",
  ];

  const metricLabels = {
    en: {
      singleHop: "Single-Hop",
      multiHop: "Multi-Hop",
      knowledgeUpdate: "Knowledge Update",
      temporalReasoning: "Temporal Reasoning",
      abstention: "Abstention",
      implicitPreference: "Implicit Preference",
      visualReasoning: "Visual Reasoning",
      llmJudge: "Overall LLM-Judge",
      f1: "Overall F1",
    },
    zh: {
      singleHop: "单跳推理",
      multiHop: "多跳推理",
      knowledgeUpdate: "知识更新",
      temporalReasoning: "时序推理",
      abstention: "拒答",
      implicitPreference: "隐式偏好",
      visualReasoning: "视觉推理",
      llmJudge: "总体 LLM-Judge",
      f1: "总体 F1",
    },
  };

  const familyLabels = {
    en: { textual: "Textual memory", multimodal: "Multimodal memory" },
    zh: { textual: "文本记忆", multimodal: "多模态记忆" },
  };

  const rows = [
    {
      family: "textual",
      backbone: "gpt",
      method: "Long Context",
      scores: ["17.24", "10.22", "21.48", "19.28", "18.13", "34.01", "12.16", "19.14", "20.50"],
    },
    {
      family: "textual",
      backbone: "gpt",
      method: "NaiveRAG",
      scores: ["24.85", "20.44", "16.53", "19.02", "7.37", "8.56", "14.5", "15.4", "10.4"],
    },
    {
      family: "textual",
      backbone: "gpt",
      method: "LangMem",
      scores: ["21.81", "19.21", "27.52", "29.88", "12.00", "49.02", "14.95", "24.94", "7.46"],
    },
    {
      family: "textual",
      backbone: "gpt",
      method: "Mem0",
      scores: ["26.88", "25.90", "27.33", "27.43", "7.12", "43.96", "15.04", "24.73", "9.63"],
    },
    {
      family: "textual",
      backbone: "gpt",
      method: "LightMem",
      scores: ["37.42", "32.95", "38.22", "38.94", "19.21", "46.25", "25.81", "33.8", "21.5"],
    },
    {
      family: "textual",
      backbone: "gpt",
      method: "EverMemOS",
      scores: ["46.96", "40.44", "46.83", "43.47", "7.04", "60.28", "34.08", "39.41", "12.16"],
    },
    {
      family: "textual",
      backbone: "gpt",
      method: "M²A (w/ Caption)",
      scores: ["27.59", "29.60", "22.67", "16.95", "4.06", "32.14", "19.50", "21.86", "21.05"],
    },
    {
      family: "textual",
      backbone: "qwen",
      method: "Long Context",
      scores: ["4.06", "4.32", "5.05", "9.19", "6.29", "6.53", "6.78", "5.93", "12.81"],
    },
    {
      family: "textual",
      backbone: "qwen",
      method: "NaiveRAG",
      scores: ["5.07", "5.64", "2.77", "5.30", "7.45", "0.73", "2.41", "4.15", "4.38"],
    },
    {
      family: "textual",
      backbone: "qwen",
      method: "LangMem",
      scores: ["17.44", "14.19", "18.71", "17.08", "13.82", "30.18", "8.17", "17.25", "2.43"],
    },
    {
      family: "textual",
      backbone: "qwen",
      method: "Mem0",
      scores: ["25.89", "23.23", "31.81", "23.70", "13.01", "50.49", "16.79", "26.71", "8.77"],
    },
    {
      family: "textual",
      backbone: "qwen",
      method: "LightMem",
      scores: ["30.12", "26.43", "29.70", "23.16", "20.78", "36.05", "22.19", "27.08", "16.88"],
    },
    {
      family: "textual",
      backbone: "qwen",
      method: "EverMemOS",
      scores: ["28.09", "27.22", "27.82", "26.26", "13.82", "31.97", "19.22", "24.76", "3.55"],
    },
    {
      family: "textual",
      backbone: "qwen",
      method: "M²A (w/ Caption)",
      scores: ["25.96", "26.70", "21.88", "17.85", "5.46", "20.80", "17.21", "19.21", "17.53"],
    },
    {
      family: "multimodal",
      backbone: "gpt",
      method: "Multimodal Long Context",
      scores: ["34.9", "20.4", "30.9", "31.3", "14.0", "17.2", "21.9", "24.4", "18.3"],
    },
    {
      family: "multimodal",
      backbone: "gpt",
      method: "SigLIP + NaiveRAG",
      scores: ["23.1", "16.83", "19.70", "18.1", "4.8", "33.8", "9.6", "18.00", "10.0"],
    },
    {
      family: "multimodal",
      backbone: "gpt",
      method: "UniversalRAG",
      scores: ["22.6", "17.6", "22.1", "21.2", "4.9", "39.0", "7.6", "19.3", "9.5"],
    },
    {
      family: "multimodal",
      backbone: "gpt",
      method: "M²A",
      scores: ["1.52", "1.23", "2.87", "6.47", "24.44", "16.39", "3.63", "8.68", "12.12"],
    },
    {
      family: "multimodal",
      backbone: "qwen",
      method: "Multimodal Long Context",
      scores: ["16.7", "11.6", "18.3", "19.0", "1.4", "9.3", "13.5", "12.8", "12.2"],
    },
    {
      family: "multimodal",
      backbone: "qwen",
      method: "SigLIP + NaiveRAG",
      scores: ["10.9", "9.9", "9.8", "11.9", "15.56", "17.5", "4.4", "11.6", "4.6"],
    },
    {
      family: "multimodal",
      backbone: "qwen",
      method: "UniversalRAG",
      scores: ["14.8", "12.3", "15.9", "11.5", "13.1", "26.6", "3.2", "14.2", "4.6"],
    },
    {
      family: "multimodal",
      backbone: "qwen",
      method: "M²A",
      scores: ["0.82", "1.06", "2.33", "8.98", "16.42", "4.91", "2.75", "5.40", "10.54"],
    },
  ].map((row, sourceOrder) => ({
    ...row,
    sourceOrder,
    values: Object.fromEntries(metricOrder.map((metric, index) => [metric, row.scores[index]])),
  }));

  const body = document.querySelector("[data-leaderboard-body]");
  const metricSelect = document.querySelector("[data-rank-metric]");
  const stateLabel = document.querySelector("[data-leaderboard-state]");
  if (!body || !metricSelect || !stateLabel) return;

  const state = {
    backbone: "gpt",
    family: "all",
    metric: "llmJudge",
  };

  const currentLanguage = () => (document.documentElement.lang === "zh" ? "zh" : "en");

  const renderMetricOptions = () => {
    const lang = currentLanguage();
    metricSelect.replaceChildren(
      ...metricOrder.map((metric) => {
        const option = document.createElement("option");
        option.value = metric;
        option.textContent = metricLabels[lang][metric];
        option.selected = metric === state.metric;
        return option;
      }),
    );
  };

  const makeMethodCell = (row, lang) => {
    const cell = document.createElement("td");
    cell.className = "method-column";
    const content = document.createElement("span");
    content.className = "method-cell";
    const method = document.createElement("strong");
    method.textContent = row.method;
    const family = document.createElement("small");
    family.textContent = familyLabels[lang][row.family];
    content.append(method, family);
    cell.append(content);
    return cell;
  };

  const render = () => {
    const lang = currentLanguage();
    const filtered = rows
      .filter((row) => row.backbone === state.backbone)
      .filter((row) => state.family === "all" || row.family === state.family)
      .sort(
        (left, right) =>
          Number(right.values[state.metric]) - Number(left.values[state.metric]) ||
          left.sourceOrder - right.sourceOrder,
      );

    body.replaceChildren(
      ...filtered.map((row, index) => {
        const tableRow = document.createElement("tr");
        tableRow.dataset.family = row.family;
        tableRow.dataset.rank = String(index + 1);

        const rank = document.createElement("td");
        rank.className = "rank-column";
        rank.textContent = String(index + 1).padStart(2, "0");
        tableRow.append(rank, makeMethodCell(row, lang));

        metricOrder.forEach((metric) => {
          const score = document.createElement("td");
          score.className = "score-cell";
          score.dataset.scoreKey = metric;
          score.textContent = row.values[metric];
          if (metric === state.metric) score.classList.add("is-ranked");
          if (metric === state.metric && index === 0) score.classList.add("is-best");
          tableRow.append(score);
        });
        return tableRow;
      }),
    );

    document.querySelectorAll(".leaderboard-table th[data-score-key]").forEach((header) => {
      header.classList.toggle("is-ranked", header.dataset.scoreKey === state.metric);
    });

    const metric = metricLabels[lang][state.metric];
    stateLabel.textContent =
      lang === "zh"
        ? `${filtered.length} 个配置，按 ${metric} 排序`
        : `${filtered.length} configurations ranked by ${metric}`;
  };

  document.querySelectorAll("[data-backbone]").forEach((button) => {
    button.addEventListener("click", () => {
      state.backbone = button.dataset.backbone;
      document.querySelectorAll("[data-backbone]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      render();
    });
  });

  document.querySelectorAll("[data-family]").forEach((button) => {
    button.addEventListener("click", () => {
      state.family = button.dataset.family;
      document.querySelectorAll("[data-family]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      render();
    });
  });

  metricSelect.addEventListener("change", () => {
    state.metric = metricSelect.value;
    render();
  });

  window.addEventListener("mobilemem:languagechange", () => {
    renderMetricOptions();
    render();
  });

  renderMetricOptions();
  render();
})();
