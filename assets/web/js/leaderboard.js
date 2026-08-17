/** MobileMem and MobileMem-Omni paper-result leaderboard. */

(() => {
  const familyLabels = {
    en: { textual: "Textual memory", multimodal: "Multimodal memory" },
    zh: { textual: "文本记忆", multimodal: "多模态记忆" },
  };

  const groupLabels = {
    en: { task: "Task", overall: "Overall" },
    zh: { task: "任务", overall: "总体" },
  };

  const omniMetrics = [
    { key: "singleHop", group: "task", en: "Single-Hop", zh: "单跳推理" },
    { key: "multiHop", group: "task", en: "Multi-Hop", zh: "多跳推理" },
    { key: "knowledgeUpdate", group: "task", en: "Knowledge Update", zh: "知识更新" },
    { key: "temporalReasoning", group: "task", en: "Temporal Reasoning", zh: "时序推理" },
    { key: "abstention", group: "task", en: "Abstention", zh: "拒答" },
    { key: "implicitPreference", group: "task", en: "Implicit Preference", zh: "隐式偏好" },
    { key: "visualReasoning", group: "task", en: "Visual Reasoning", zh: "视觉推理" },
    { key: "llmJudge", group: "overall", en: "LLM-Judge", zh: "LLM-Judge" },
    { key: "f1", group: "overall", en: "F1", zh: "F1" },
  ];

  const textualMetrics = [
    { key: "singleHop", group: "task", en: "Single-Hop", zh: "单跳推理" },
    { key: "multiHop", group: "task", en: "Multi-Hop", zh: "多跳推理" },
    { key: "temporalReasoning", group: "task", en: "Temporal Reasoning", zh: "时序推理" },
    { key: "relationship", group: "task", en: "Relationship", zh: "关系推理" },
    { key: "qfs", group: "task", en: "Query-Focused Summary", zh: "查询聚焦摘要" },
    { key: "adversarial", group: "task", en: "Adversarial", zh: "对抗问题" },
    { key: "others", group: "task", en: "Others", zh: "其他" },
    { key: "overall", group: "overall", en: "Overall", zh: "总体" },
  ];

  const createRows = (entries, metrics) =>
    entries.map(([family, backbone, method, scores], sourceOrder) => ({
      family,
      backbone,
      method,
      sourceOrder,
      values: Object.fromEntries(metrics.map((metric, index) => [metric.key, scores[index]])),
    }));

  const omniRows = createRows(
    [
      [
        "textual",
        "gpt54",
        "Long Context",
        ["17.24", "10.22", "21.48", "19.28", "18.13", "34.01", "12.16", "19.14", "20.50"],
      ],
      [
        "textual",
        "gpt54",
        "NaiveRAG",
        ["24.85", "20.44", "16.53", "19.02", "7.37", "8.56", "14.5", "15.4", "10.4"],
      ],
      [
        "textual",
        "gpt54",
        "LangMem",
        ["21.81", "19.21", "27.52", "29.88", "12.00", "49.02", "14.95", "24.94", "7.46"],
      ],
      [
        "textual",
        "gpt54",
        "Mem0",
        ["26.88", "25.90", "27.33", "27.43", "7.12", "43.96", "15.04", "24.73", "9.63"],
      ],
      [
        "textual",
        "gpt54",
        "LightMem",
        ["37.42", "32.95", "38.22", "38.94", "19.21", "46.25", "25.81", "33.8", "21.5"],
      ],
      [
        "textual",
        "gpt54",
        "EverMemOS",
        ["46.96", "40.44", "46.83", "43.47", "7.04", "60.28", "34.08", "39.41", "12.16"],
      ],
      [
        "textual",
        "gpt54",
        "M²A (w/ Caption)",
        ["27.59", "29.60", "22.67", "16.95", "4.06", "32.14", "19.50", "21.86", "21.05"],
      ],
      [
        "textual",
        "qwen",
        "Long Context",
        ["4.06", "4.32", "5.05", "9.19", "6.29", "6.53", "6.78", "5.93", "12.81"],
      ],
      [
        "textual",
        "qwen",
        "NaiveRAG",
        ["5.07", "5.64", "2.77", "5.30", "7.45", "0.73", "2.41", "4.15", "4.38"],
      ],
      [
        "textual",
        "qwen",
        "LangMem",
        ["17.44", "14.19", "18.71", "17.08", "13.82", "30.18", "8.17", "17.25", "2.43"],
      ],
      [
        "textual",
        "qwen",
        "Mem0",
        ["25.89", "23.23", "31.81", "23.70", "13.01", "50.49", "16.79", "26.71", "8.77"],
      ],
      [
        "textual",
        "qwen",
        "LightMem",
        ["30.12", "26.43", "29.70", "23.16", "20.78", "36.05", "22.19", "27.08", "16.88"],
      ],
      [
        "textual",
        "qwen",
        "EverMemOS",
        ["28.09", "27.22", "27.82", "26.26", "13.82", "31.97", "19.22", "24.76", "3.55"],
      ],
      [
        "textual",
        "qwen",
        "M²A (w/ Caption)",
        ["25.96", "26.70", "21.88", "17.85", "5.46", "20.80", "17.21", "19.21", "17.53"],
      ],
      [
        "multimodal",
        "gpt54",
        "Multimodal Long Context",
        ["34.9", "20.4", "30.9", "31.3", "14.0", "17.2", "21.9", "24.4", "18.3"],
      ],
      [
        "multimodal",
        "gpt54",
        "SigLIP + NaiveRAG",
        ["23.1", "16.83", "19.70", "18.1", "4.8", "33.8", "9.6", "18.00", "10.0"],
      ],
      [
        "multimodal",
        "gpt54",
        "UniversalRAG",
        ["22.6", "17.6", "22.1", "21.2", "4.9", "39.0", "7.6", "19.3", "9.5"],
      ],
      [
        "multimodal",
        "gpt54",
        "M²A",
        ["1.52", "1.23", "2.87", "6.47", "24.44", "16.39", "3.63", "8.68", "12.12"],
      ],
      [
        "multimodal",
        "qwen",
        "Multimodal Long Context",
        ["16.7", "11.6", "18.3", "19.0", "1.4", "9.3", "13.5", "12.8", "12.2"],
      ],
      [
        "multimodal",
        "qwen",
        "SigLIP + NaiveRAG",
        ["10.9", "9.9", "9.8", "11.9", "15.56", "17.5", "4.4", "11.6", "4.6"],
      ],
      [
        "multimodal",
        "qwen",
        "UniversalRAG",
        ["14.8", "12.3", "15.9", "11.5", "13.1", "26.6", "3.2", "14.2", "4.6"],
      ],
      [
        "multimodal",
        "qwen",
        "M²A",
        ["0.82", "1.06", "2.33", "8.98", "16.42", "4.91", "2.75", "5.40", "10.54"],
      ],
    ],
    omniMetrics,
  );

  const textualRows = createRows(
    [
      [
        "textual",
        "gpt41mini",
        "Long Context",
        [
          "56.54",
          "51.71",
          "53.76",
          "58.33",
          "47.06",
          "51.89",
          "60.87",
          "54.51",
          "0.00",
          "0.00",
          "0.00",
        ],
      ],
      [
        "textual",
        "gpt41mini",
        "NaiveRAG",
        [
          "38.58",
          "31.23",
          "29.03",
          "29.17",
          "20.59",
          "60.38",
          "47.83",
          "37.23",
          "0.00",
          "0.00",
          "0.00",
        ],
      ],
      [
        "textual",
        "gpt41mini",
        "HippoRAG2",
        [
          "85.67",
          "79.00",
          "61.29",
          "87.50",
          "73.53",
          "50.94",
          "82.61",
          "78.85",
          "2307.44",
          "495.84",
          "2803.28",
        ],
      ],
      [
        "textual",
        "gpt41mini",
        "LangMem",
        [
          "23.62",
          "14.96",
          "12.90",
          "20.83",
          "11.76",
          "76.42",
          "39.13",
          "24.79",
          "3836.97",
          "548.49",
          "4385.46",
        ],
      ],
      [
        "textual",
        "gpt41mini",
        "A-MEM",
        [
          "86.30",
          "79.79",
          "72.04",
          "83.33",
          "76.47",
          "44.34",
          "84.78",
          "79.68",
          "4544.41",
          "919.31",
          "5463.72",
        ],
      ],
      [
        "textual",
        "gpt41mini",
        "Mem0",
        [
          "38.11",
          "27.30",
          "26.88",
          "50.00",
          "8.82",
          "57.55",
          "50.00",
          "35.63",
          "1472.69",
          "597.22",
          "2069.91",
        ],
      ],
      [
        "textual",
        "gpt41mini",
        "Mem0ᵍ",
        [
          "39.06",
          "30.71",
          "29.03",
          "54.17",
          "11.76",
          "50.00",
          "52.17",
          "36.85",
          "1474.46",
          "600.36",
          "2074.82",
        ],
      ],
      [
        "textual",
        "gpt41mini",
        "MemOS",
        [
          "72.44",
          "61.94",
          "52.69",
          "75.00",
          "50.00",
          "50.94",
          "76.09",
          "65.88",
          "3260.79",
          "919.78",
          "4180.57",
        ],
      ],
      [
        "textual",
        "gpt41mini",
        "EverMemOS",
        [
          "68.50",
          "57.48",
          "55.91",
          "83.33",
          "55.88",
          "47.17",
          "76.09",
          "62.93",
          "7052.32",
          "518.14",
          "7570.46",
        ],
      ],
      [
        "textual",
        "gpt54",
        "Long Context",
        [
          "49.13",
          "42.26",
          "35.48",
          "45.83",
          "50.00",
          "34.91",
          "54.35",
          "45.19",
          "0.00",
          "0.00",
          "0.00",
        ],
      ],
      [
        "textual",
        "gpt54",
        "NaiveRAG",
        [
          "40.16",
          "32.28",
          "26.88",
          "45.83",
          "23.53",
          "42.45",
          "58.70",
          "37.45",
          "0.00",
          "0.00",
          "0.00",
        ],
      ],
      [
        "textual",
        "gpt54",
        "HippoRAG2",
        [
          "86.14",
          "79.27",
          "67.74",
          "91.67",
          "85.29",
          "50.94",
          "84.78",
          "80.06",
          "2154.32",
          "586.73",
          "2741.05",
        ],
      ],
      [
        "textual",
        "gpt54",
        "LangMem",
        [
          "30.71",
          "21.26",
          "16.13",
          "41.67",
          "20.59",
          "63.21",
          "54.35",
          "30.33",
          "4399.06",
          "838.12",
          "5237.17",
        ],
      ],
      [
        "textual",
        "gpt54",
        "A-MEM",
        [
          "85.67",
          "77.17",
          "68.82",
          "95.83",
          "73.53",
          "43.40",
          "82.61",
          "78.39",
          "9029.91",
          "2140.53",
          "11170.44",
        ],
      ],
      [
        "textual",
        "gpt54",
        "Mem0",
        [
          "52.28",
          "31.76",
          "31.18",
          "45.83",
          "14.71",
          "35.85",
          "56.52",
          "42.61",
          "1841.28",
          "668.07",
          "2509.34",
        ],
      ],
      [
        "textual",
        "gpt54",
        "Mem0ᵍ",
        [
          "50.71",
          "30.97",
          "29.03",
          "54.17",
          "14.71",
          "39.62",
          "52.17",
          "41.77",
          "1848.94",
          "696.20",
          "2545.14",
        ],
      ],
      [
        "textual",
        "gpt54",
        "MemOS",
        [
          "79.84",
          "72.18",
          "55.91",
          "75.00",
          "55.88",
          "63.21",
          "82.61",
          "74.00",
          "4201.20",
          "1234.40",
          "5435.60",
        ],
      ],
      [
        "textual",
        "gpt54",
        "EverMemOS",
        [
          "67.09",
          "56.69",
          "54.84",
          "75.00",
          "55.88",
          "39.62",
          "76.09",
          "61.18",
          "10543.65",
          "640.15",
          "11183.79",
        ],
      ],
    ],
    textualMetrics,
  );

  const benchmarks = {
    omni: {
      label: "MobileMem-Omni",
      title: { en: "MobileMem-Omni", zh: "MobileMem-Omni" },
      caption: {
        en: "MobileMem-Omni question-answering performance by method and task",
        zh: "MobileMem-Omni 各方法在不同任务上的问答表现",
      },
      metrics: omniMetrics,
      groups: ["task", "overall"],
      backbones: [
        { id: "gpt54", label: "GPT-5.4-mini" },
        { id: "qwen", label: "Qwen3-VL-8B-Instruct" },
      ],
      defaultBackbone: "gpt54",
      defaultMetric: "llmJudge",
      hasFamilies: true,
      rows: omniRows,
    },
    textual: {
      label: "MobileMem-Text",
      title: { en: "MobileMem-Text", zh: "MobileMem-Text" },
      caption: {
        en: "MobileMem-Text benchmark performance by memory method",
        zh: "MobileMem-Text 各记忆方法的任务表现",
      },
      metrics: textualMetrics,
      groups: ["task", "overall"],
      backbones: [
        { id: "gpt41mini", label: "GPT-4.1-mini" },
        { id: "gpt54", label: "GPT-5.4-mini" },
      ],
      defaultBackbone: "gpt54",
      defaultMetric: "overall",
      hasFamilies: false,
      rows: textualRows,
    },
  };

  const title = document.querySelector("[data-leaderboard-title]");
  const context = document.querySelector("[data-leaderboard-context]");
  const caption = document.querySelector("[data-leaderboard-caption]");
  const head = document.querySelector("[data-leaderboard-head]");
  const body = document.querySelector("[data-leaderboard-body]");
  const metricSelect = document.querySelector("[data-rank-metric]");
  const stateLabel = document.querySelector("[data-leaderboard-state]");
  const familyControlGroup = document.querySelector("[data-family-control-group]");
  const benchmarkSwitcher = document.querySelector("[data-benchmark-switcher]");
  const benchmarkSummary = benchmarkSwitcher?.querySelector("summary");
  const benchmarkButtons = Array.from(document.querySelectorAll("[data-benchmark]"));
  const backboneButtons = Array.from(document.querySelectorAll("[data-backbone]"));
  const familyButtons = Array.from(document.querySelectorAll("[data-family]"));

  if (!title || !context || !caption || !head || !body || !metricSelect || !stateLabel) return;

  const state = {
    benchmark: "omni",
    backbone: benchmarks.omni.defaultBackbone,
    family: "all",
    metric: benchmarks.omni.defaultMetric,
  };

  const currentLanguage = () => (document.documentElement.lang === "zh" ? "zh" : "en");
  const currentBenchmark = () => benchmarks[state.benchmark];
  const currentMetric = () =>
    currentBenchmark().metrics.find((metric) => metric.key === state.metric);

  const makeHeaderCell = ({ text, className, rowSpan, colSpan, scope, scoreKey }) => {
    const cell = document.createElement("th");
    cell.textContent = text;
    if (className) cell.className = className;
    if (rowSpan) cell.rowSpan = rowSpan;
    if (colSpan) cell.colSpan = colSpan;
    if (scope) cell.scope = scope;
    if (scoreKey) cell.dataset.scoreKey = scoreKey;
    return cell;
  };

  const renderTableHead = () => {
    const lang = currentLanguage();
    const benchmark = currentBenchmark();
    const firstRow = document.createElement("tr");
    const secondRow = document.createElement("tr");

    firstRow.append(
      makeHeaderCell({
        text: lang === "zh" ? "排名" : "Rank",
        className: "rank-column",
        rowSpan: 2,
        scope: "col",
      }),
      makeHeaderCell({
        text: lang === "zh" ? "方法" : "Method",
        className: "method-column",
        rowSpan: 2,
        scope: "col",
      }),
    );

    benchmark.groups.forEach((group) => {
      const groupMetrics = benchmark.metrics.filter((metric) => metric.group === group);
      firstRow.append(
        makeHeaderCell({
          text: groupLabels[lang][group],
          colSpan: groupMetrics.length,
          scope: "colgroup",
        }),
      );
      groupMetrics.forEach((metric) => {
        secondRow.append(
          makeHeaderCell({
            text: metric[lang],
            scope: "col",
            scoreKey: metric.key,
          }),
        );
      });
    });

    head.replaceChildren(firstRow, secondRow);
  };

  const renderBenchmarkControls = () => {
    const lang = currentLanguage();
    const benchmark = currentBenchmark();
    title.textContent = benchmark.title[lang];
    context.textContent = benchmark.label;
    caption.textContent = benchmark.caption[lang];
    document.title = benchmark.title.en;
    document.body.dataset.benchmark = state.benchmark;

    benchmarkButtons.forEach((button) => {
      button.setAttribute("aria-current", String(button.dataset.benchmark === state.benchmark));
    });

    if (benchmarkSummary) {
      const switchLabel = lang === "zh" ? "切换评测集" : "Switch benchmark";
      benchmarkSummary.setAttribute("aria-label", switchLabel);
      benchmarkSummary.title = switchLabel;
    }

    backboneButtons.forEach((button, index) => {
      const option = benchmark.backbones[index];
      button.dataset.backbone = option.id;
      button.textContent = option.label;
      button.setAttribute("aria-pressed", String(option.id === state.backbone));
    });

    if (familyControlGroup) familyControlGroup.hidden = !benchmark.hasFamilies;
    familyButtons.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.family === state.family));
    });
  };

  const renderMetricOptions = () => {
    const lang = currentLanguage();
    metricSelect.replaceChildren(
      ...currentBenchmark().metrics.map((metric) => {
        const option = document.createElement("option");
        option.value = metric.key;
        option.textContent = metric[lang];
        option.selected = metric.key === state.metric;
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

  const metricNumber = (value) => Number(String(value).replaceAll(",", ""));

  const render = () => {
    const lang = currentLanguage();
    const benchmark = currentBenchmark();
    const metric = currentMetric();
    const filtered = benchmark.rows
      .filter((row) => row.backbone === state.backbone)
      .filter((row) => !benchmark.hasFamilies || state.family === "all" || row.family === state.family)
      .sort((left, right) => {
        const leftValue = metricNumber(left.values[state.metric]);
        const rightValue = metricNumber(right.values[state.metric]);
        const scoreOrder =
          metric.rank === "asc" ? leftValue - rightValue : rightValue - leftValue;
        return scoreOrder || left.sourceOrder - right.sourceOrder;
      });

    body.replaceChildren(
      ...filtered.map((row, index) => {
        const tableRow = document.createElement("tr");
        tableRow.dataset.family = row.family;
        tableRow.dataset.rank = String(index + 1);

        const rank = document.createElement("td");
        rank.className = "rank-column";
        rank.textContent = String(index + 1).padStart(2, "0");
        tableRow.append(rank, makeMethodCell(row, lang));

        benchmark.metrics.forEach((scoreMetric) => {
          const score = document.createElement("td");
          score.className = "score-cell";
          score.dataset.scoreKey = scoreMetric.key;
          score.textContent = row.values[scoreMetric.key];
          if (scoreMetric.key === state.metric) score.classList.add("is-ranked");
          if (scoreMetric.key === state.metric && index === 0) score.classList.add("is-best");
          tableRow.append(score);
        });
        return tableRow;
      }),
    );

    head.querySelectorAll("th[data-score-key]").forEach((header) => {
      header.classList.toggle("is-ranked", header.dataset.scoreKey === state.metric);
    });

    stateLabel.textContent =
      lang === "zh"
        ? `${filtered.length} 个配置，按 ${metric[lang]} 排序`
        : `${filtered.length} configurations ranked by ${metric[lang]}`;
  };

  const renderAll = () => {
    renderBenchmarkControls();
    renderMetricOptions();
    renderTableHead();
    render();
  };

  benchmarkButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const nextBenchmark = benchmarks[button.dataset.benchmark];
      if (!nextBenchmark) return;
      state.benchmark = button.dataset.benchmark;
      state.backbone = nextBenchmark.defaultBackbone;
      state.family = nextBenchmark.hasFamilies ? "all" : "textual";
      state.metric = nextBenchmark.defaultMetric;
      benchmarkSwitcher?.removeAttribute("open");
      renderAll();
    });
  });

  document.addEventListener("click", (event) => {
    if (!benchmarkSwitcher?.open || benchmarkSwitcher.contains(event.target)) return;
    benchmarkSwitcher.removeAttribute("open");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !benchmarkSwitcher?.open) return;
    benchmarkSwitcher.removeAttribute("open");
    benchmarkSummary?.focus();
  });

  backboneButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.backbone = button.dataset.backbone;
      backboneButtons.forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      render();
    });
  });

  familyButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.family = button.dataset.family;
      familyButtons.forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      render();
    });
  });

  metricSelect.addEventListener("change", () => {
    state.metric = metricSelect.value;
    render();
  });

  window.addEventListener("mobilemem:languagechange", renderAll);

  renderAll();
})();
