/** Quick-start terminal animation. */

(() => {
  // Quick-start terminal demo -------------------------------------------------

  const terminalOutput = document.querySelector("[data-terminal-output]");
  const terminalButtons = Array.from(document.querySelectorAll("[data-terminal-set]"));
  const terminalCopyButton = document.querySelector("[data-terminal-copy]");
  const terminalSets = {
    setup: [
      { text: "conda create -n mobilemem python=3.11 -y", prompt: true },
      { text: "conda activate mobilemem", prompt: true },
      { text: "git clone https://github.com/zjunlp/MobileMem.git", prompt: true },
      { text: "cd MobileMem/omni", prompt: true },
      { text: "pip install -r requirements.txt", prompt: true },
      { text: "playwright install --with-deps chromium", prompt: true },
    ],
    download: [
      {
        text: "hf download zjunlp/MobileMem --repo-type dataset --local-dir data/MobileMem",
        prompt: true,
      },
    ],
    pipeline: [
      { text: "cd MobileMem/omni/src", prompt: true },
      {
        text: "cp .env.example .env    # then fill in your API keys",
        prompt: true,
      },
      { text: "python -m pipeline.cli list", prompt: true },
      { text: "python -m pipeline.cli run", prompt: true },
    ],
    evaluation: [
      { text: "cd MobileMem/omni", prompt: true },
      {
        text: 'python eval/Jsonl2Locomo.py --stage5 path/to/stage5_all_users.jsonl --stage6-dir path/to/stage6 --stage10 "" --output-dir data/Locomo --users 0 --no-image',
        prompt: true,
      },
      { text: "cd ../..", prompt: true },
      { text: "git clone https://github.com/zjunlp/MemBase.git", prompt: true },
      { text: "cd MemBase", prompt: true },
      { text: "conda create -n <METHOD>_env python=3.12 -y", prompt: true },
      { text: "conda activate <METHOD>_env", prompt: true },
      {
        text: "pip install -r envs/<METHOD>_requirements.txt",
        prompt: true,
      },
      {
        text: "python memory_construction.py --memory-type <METHOD> --dataset-type locomo --dataset-path ../MobileMem/omni/data/Locomo --config-path <CONFIG>",
        prompt: true,
      },
      {
        text: "python memory_search.py --memory-type <METHOD> --dataset-type locomo --dataset-path ../MobileMem/omni/data/Locomo --config-path <CONFIG> --top-k 10",
        prompt: true,
      },
      {
        text: "python memory_evaluation.py --search-results-path <SEARCH_RESULTS> --dataset-type locomo --qa-model <QA_MODEL> --judge-model <JUDGE_MODEL> --api-config-path <API_CONFIG>",
        prompt: true,
      },
    ],
  };
  const terminalSetOrder = ["setup", "download", "pipeline", "evaluation"];
  const terminalTimers = new Set();
  let terminalCycleIndex = 0;
  let terminalRunId = 0;
  let activeTerminalSet = terminalSetOrder[0];
  let copyFeedbackTimer;

  const terminalCopyLabels = {
    en: { copy: "Copy current commands", copied: "Copied" },
    zh: { copy: "复制当前命令", copied: "已复制" },
  };

  const currentLanguage = () => (document.documentElement.lang === "zh" ? "zh" : "en");

  const setTerminalCopyState = (copied = false) => {
    if (!terminalCopyButton) return;
    const label = terminalCopyLabels[currentLanguage()][copied ? "copied" : "copy"];
    terminalCopyButton.classList.toggle("is-copied", copied);
    terminalCopyButton.setAttribute("aria-label", label);
    terminalCopyButton.title = label;
  };

  const writeToClipboard = async (text) => {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch {
        // file:// previews may not expose the asynchronous clipboard API.
      }
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    return copied;
  };

  const clearTerminalTimers = () => {
    terminalTimers.forEach((timer) => window.clearTimeout(timer));
    terminalTimers.clear();
  };

  const scheduleTerminal = (callback, delay, runId) => {
    const timer = window.setTimeout(() => {
      terminalTimers.delete(timer);
      if (runId === terminalRunId) callback();
    }, delay);
    terminalTimers.add(timer);
  };

  const setActiveTerminalButton = (setName) => {
    terminalButtons.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.terminalSet === setName));
    });
  };

  const startTerminalDemo = (
    setName = terminalSetOrder[terminalCycleIndex],
    shouldContinue = true,
  ) => {
    if (!terminalOutput) return;
    clearTerminalTimers();
    terminalRunId += 1;
    const runId = terminalRunId;
    activeTerminalSet = setName;
    setActiveTerminalButton(setName);
    terminalOutput.innerHTML = "";
    const terminalLines = terminalSets[setName];
    let lineIndex = 0;
    let charIndex = 0;
    let activeLine = null;

    const trimVisibleLines = () => {
      const lines = terminalOutput.querySelectorAll(".terminal-line");
      if (lines.length <= 5) return;
      lines[0].remove();
    };

    const removeCursor = () => {
      const cursor = terminalOutput.querySelector(".terminal-cursor");
      if (cursor) cursor.remove();
    };

    const appendCursor = () => {
      const cursor = document.createElement("span");
      cursor.className = "terminal-cursor";
      terminalOutput.append(cursor);
    };

    const beginLine = () => {
      if (runId !== terminalRunId) return;
      removeCursor();

      if (lineIndex >= terminalLines.length) {
        appendCursor();
        if (shouldContinue) {
          terminalCycleIndex = (terminalSetOrder.indexOf(setName) + 1) % terminalSetOrder.length;
          scheduleTerminal(
            () => startTerminalDemo(terminalSetOrder[terminalCycleIndex], true),
            1800,
            runId,
          );
        }
        return;
      }

      const terminalLine = terminalLines[lineIndex];
      const line = document.createElement("p");
      line.className = `terminal-line${terminalLine.prompt ? " prompt" : ""}`;
      line.textContent = "";
      terminalOutput.append(line);
      trimVisibleLines();

      activeLine = line;
      charIndex = 0;
      typeNextChar();
    };

    const typeNextChar = () => {
      if (runId !== terminalRunId) return;
      removeCursor();
      const terminalLine = terminalLines[lineIndex];

      if (charIndex < terminalLine.text.length) {
        activeLine.textContent += terminalLine.text.charAt(charIndex);
        charIndex += 1;
        appendCursor();
        scheduleTerminal(typeNextChar, 24 + Math.random() * 34, runId);
        return;
      }

      appendCursor();
      lineIndex += 1;
      scheduleTerminal(beginLine, terminalLine.prompt ? 520 : 900, runId);
    };

    beginLine();
  };

  startTerminalDemo();

  terminalButtons.forEach((button) => {
    button.addEventListener("click", () => {
      terminalCycleIndex = terminalSetOrder.indexOf(button.dataset.terminalSet);
      startTerminalDemo(button.dataset.terminalSet, true);
      button.blur();
    });
  });

  terminalCopyButton?.addEventListener("click", async () => {
    const commands = terminalSets[activeTerminalSet].map((line) => line.text).join("\n");
    const copied = await writeToClipboard(commands);
    if (!copied) return;

    window.clearTimeout(copyFeedbackTimer);
    setTerminalCopyState(true);
    copyFeedbackTimer = window.setTimeout(() => setTerminalCopyState(false), 1500);
  });

  window.addEventListener("mobilemem:languagechange", () => {
    window.clearTimeout(copyFeedbackTimer);
    setTerminalCopyState(false);
  });
})();
