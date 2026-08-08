/** Quick-start terminal animation. */

(() => {
  // Quick-start terminal demo -------------------------------------------------

  const terminalOutput = document.querySelector("[data-terminal-output]");
  const terminalButtons = Array.from(document.querySelectorAll("[data-terminal-set]"));
  const terminalSets = {
    setup: [
      { text: "conda create -n mobilemem python=3.11 -y", prompt: true },
      { text: "conda activate mobilemem", prompt: true },
      { text: "git clone https://github.com/zjunlp/MobileMem.git", prompt: true },
      { text: "pip install -r MobileMem/omni/requirements.txt", prompt: true },
      { text: "playwright install chromium", prompt: true },
    ],
    download: [
      {
        text: "hf download zjunlp/MobileMem --repo-type dataset --local-dir data/MobileMem",
        prompt: true,
      },
      {
        text: "python -c 'from datasets import load_dataset; ds = load_dataset(\"zjunlp/MobileMem\")'",
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
      {
        text: "python -m pipeline.cli run --only event_photo --uuid 7",
        prompt: true,
      },
    ],
    evaluation: [
      { text: "git clone https://github.com/zjunlp/MemBase.git", prompt: true },
      { text: "cd MemBase", prompt: true },
      {
        text: "bash examples/evaluate_memory_systems_on_mobilemem/run_construction.sh",
        prompt: true,
      },
      {
        text: "bash examples/evaluate_memory_systems_on_mobilemem/run_search.sh",
        prompt: true,
      },
      {
        text: "bash examples/evaluate_memory_systems_on_mobilemem/run_evaluation.sh",
        prompt: true,
      },
    ],
  };
  const terminalSetOrder = ["setup", "download", "pipeline", "evaluation"];
  const terminalTimers = new Set();
  let terminalCycleIndex = 0;
  let terminalRunId = 0;

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
})();
