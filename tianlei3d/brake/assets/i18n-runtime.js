/* Runtime internationalization adapter for the recovered static build. */
(function () {
  "use strict";

  const locales = window.I18N_LOCALES;
  if (!locales || typeof locales !== "object") {
    console.warn("I18N_LOCALES is unavailable; the original language will be used.");
    return;
  }

  const STORAGE_KEY = "brake-game:locale";
  const DEFAULT_LOCALE = "zh-CN";
  const FALLBACK_LOCALE = "en";
  const RULE_KEYS = ["menu.rule1", "menu.rule2", "menu.rule3"];
  const SIGN_KEYS = {
    "前方施工": "sign.workAhead",
    "道路封闭": "sign.roadClosed",
    "极限刹车挑战": "sign.title",
    "100 km/h 后可刹车": "sign.rule",
    "道路封闭  ROAD CLOSED": "sign.barrier"
  };

  let currentLocale = resolveInitialLocale();
  let languageControl;

  function localeCodes() {
    return Object.keys(locales);
  }

  function normalizeLocale(candidate) {
    if (typeof candidate !== "string") {
      return null;
    }

    const normalized = candidate.replace(/_/g, "-").trim();
    if (locales[normalized]) {
      return normalized;
    }

    const lowerCase = normalized.toLowerCase();
    const exact = localeCodes().find((code) => code.toLowerCase() === lowerCase);
    if (exact) {
      return exact;
    }

    if (lowerCase === "en" || lowerCase.startsWith("en-")) {
      return locales.en ? "en" : null;
    }
    if (lowerCase === "ja" || lowerCase.startsWith("ja-")) {
      return locales.ja ? "ja" : null;
    }
    if (lowerCase === "zh" || lowerCase.startsWith("zh-")) {
      return /(?:tw|hk|mo|hant)/.test(lowerCase) && locales["zh-TW"]
        ? "zh-TW"
        : locales["zh-CN"]
          ? "zh-CN"
          : null;
    }

    return null;
  }

  function readStoredLocale() {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch (_error) {
      return null;
    }
  }

  function saveLocale(locale) {
    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch (_error) {
      // Storage may be blocked in private or sandboxed contexts. The session still works.
    }
  }

  function resolveInitialLocale() {
    const saved = normalizeLocale(readStoredLocale());
    if (saved) {
      return saved;
    }

    const browserLocales = Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language];
    for (const candidate of browserLocales) {
      const match = normalizeLocale(candidate);
      if (match) {
        return match;
      }
    }

    return normalizeLocale(DEFAULT_LOCALE) || localeCodes()[0];
  }

  function localeDefinition(code) {
    return locales[code] || locales[DEFAULT_LOCALE] || locales[localeCodes()[0]];
  }

  function templateFor(code, key) {
    return localeDefinition(code)?.messages?.[key];
  }

  function translate(key, values) {
    const candidates = [currentLocale, FALLBACK_LOCALE, DEFAULT_LOCALE];
    let template;
    for (const code of candidates) {
      template = templateFor(code, key);
      if (typeof template === "string") {
        break;
      }
    }

    if (typeof template !== "string") {
      return key;
    }

    return template.replace(/\{(\w+)\}/g, (placeholder, name) => {
      return values && Object.prototype.hasOwnProperty.call(values, name)
        ? String(values[name])
        : placeholder;
    });
  }

  function setText(element, key, values) {
    if (!element) {
      return;
    }

    const value = translate(key, values);
    if (element.textContent !== value) {
      element.textContent = value;
    }
  }

  function setAttribute(element, attribute, key) {
    if (!element) {
      return;
    }

    const value = translate(key);
    if (element.getAttribute(attribute) !== value) {
      element.setAttribute(attribute, value);
    }
  }

  function setRuleMarkup(element, key) {
    if (!element) {
      return;
    }

    const markup = translate(key);
    const template = document.createElement("template");
    template.innerHTML = markup;
    const allowed = Array.from(template.content.querySelectorAll("*")).every((node) => {
      if (node.tagName !== "B") {
        return false;
      }
      return Array.from(node.attributes).every((attribute) => {
        return attribute.name === "class" && attribute.value === "danger";
      });
    });

    if (!allowed) {
      setText(element, key);
      return;
    }

    const nextMarkup = template.innerHTML;
    if (element.innerHTML !== nextMarkup) {
      element.replaceChildren(template.content.cloneNode(true));
    }
  }

  function textMatchesMessage(text, key) {
    return localeCodes().some((code) => templateFor(code, key) === text);
  }

  function resolveMessageKey(text, keys, fallback) {
    return keys.find((key) => textMatchesMessage(text, key)) || fallback;
  }

  function isLikelyMobile() {
    return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent) || window.innerWidth < 760;
  }

  function translateBrakeText(element) {
    const key = resolveMessageKey(
      element.textContent,
      ["hud.brake", "hud.brakeNow", "hud.brakeHold"],
      "hud.brake"
    );
    setText(element, key);
  }

  function translateMuteText(element) {
    const key = resolveMessageKey(
      element.textContent,
      ["menu.soundOn", "menu.soundOff"],
      "menu.soundOn"
    );
    setText(element, key);
  }

  function translateHintText(element) {
    const key = resolveMessageKey(
      element.textContent,
      ["menu.hintTouch", "menu.hintKeys"],
      isLikelyMobile() ? "menu.hintTouch" : "menu.hintKeys"
    );
    setText(element, key);
  }

  function translateResultTitle(element) {
    const key = resolveMessageKey(
      element.textContent,
      ["result.okTitle", "result.snapTitle", "result.crashTitle"],
      "result.okTitle"
    );
    setText(element, key);
  }

  function translateResultSub(element) {
    const text = element.textContent;
    let key = resolveMessageKey(text, ["result.okSub", "result.crashSub"], null);
    let values;

    if (!key && /^(?:踏板力度达到 )?([\d.]+) N，整车失控翻滚飞出$/.test(text)) {
      const match = text.match(/([\d.]+) N/);
      key = "result.snapSub";
      values = { force: match[1] };
    }
    if (!key && text === "稳稳停住，V800 毫发无损") {
      key = "result.okSub";
    }

    setText(element, key || "result.okSub", values);
  }

  function translateToast(element) {
    const text = element.textContent;
    const direct = {
      "完美刹停！": "toast.perfect",
      "刹车踏板断裂！": "toast.snap",
      "撞上路障！": "toast.crash"
    };
    if (direct[text]) {
      setText(element, direct[text]);
      return;
    }

    let match = text.match(/^车速达到 ([\d.]+) km\/h 后才能刹车$/);
    if (match) {
      setText(element, "toast.tooEarly", { speed: match[1] });
      return;
    }

    match = text.match(/^动力切断 · 初速度 ([\d.]+) km\/h$/);
    if (match) {
      setText(element, "toast.brakeStart", { speed: match[1] });
    }
  }

  function translateSubmitMessage(element) {
    const text = element.textContent;
    const direct = {
      "翻车不计分，再挑战一次吧": "result.noScore",
      "请先输入昵称": "board.needNick",
      "提交中…": "board.submitting",
      "提交失败": "board.submitFailed"
    };
    if (direct[text]) {
      setText(element, direct[text]);
      return;
    }

    let match = text.match(/^已上榜！当前排名第 (\d+) 名$/);
    if (match) {
      setText(element, "board.ranked", { rank: match[1] });
      return;
    }

    match = text.match(/^已提交，你的最佳成绩 ([\d.]+) 分，排名第 (\d+) 名$/);
    if (match) {
      setText(element, "board.submitted", { best: match[1], rank: match[2] });
      return;
    }

    match = text.match(/^请求失败 \(([^)]+)\)$/);
    if (match) {
      setText(element, "error.request", { status: match[1] });
    }
  }

  function translateBoardList(element) {
    const messages = {
      "加载中…": "board.loading",
      "加载失败": "board.loadFailed",
      "还没有人上榜，快来抢第一！": "board.empty"
    };

    element.querySelectorAll(".board-empty").forEach((item) => {
      const key = messages[item.textContent];
      if (key) {
        setText(item, key);
        return;
      }

      const requestError = item.textContent.match(/^请求失败 \(([^)]+)\)$/);
      if (requestError) {
        setText(item, "error.request", { status: requestError[1] });
      }
    });
  }

  function translateDynamicElement(element) {
    if (!element) {
      return;
    }

    switch (element.id) {
      case "brakeText":
        translateBrakeText(element);
        break;
      case "toast":
        translateToast(element);
        break;
      case "resultTitle":
        translateResultTitle(element);
        break;
      case "resultSub":
        translateResultSub(element);
        break;
      case "submitMsg":
        translateSubmitMessage(element);
        break;
      case "muteBtn":
        translateMuteText(element);
        break;
      case "keyHint":
        translateHintText(element);
        break;
      case "boardList":
        translateBoardList(element);
        break;
      default:
        break;
    }
  }

  function observeDynamicText() {
    const targetIds = [
      "brakeText",
      "toast",
      "resultTitle",
      "resultSub",
      "submitMsg",
      "muteBtn",
      "keyHint",
      "boardList"
    ];
    const observer = new MutationObserver((records) => {
      const changed = new Set();
      for (const record of records) {
        const node = record.target.nodeType === Node.ELEMENT_NODE
          ? record.target
          : record.target.parentElement;
        const target = node && node.closest("#brakeText, #toast, #resultTitle, #resultSub, #submitMsg, #muteBtn, #keyHint, #boardList");
        if (target) {
          changed.add(target);
        }
      }
      changed.forEach(translateDynamicElement);
    });

    targetIds.forEach((id) => {
      const element = document.getElementById(id);
      if (element) {
        observer.observe(element, { childList: true, characterData: true, subtree: true });
      }
    });
  }

  function installLanguageControl() {
    const menu = document.getElementById("menu");
    const muteButton = document.getElementById("muteBtn");
    if (!menu || !muteButton || document.getElementById("languageControl")) {
      languageControl = document.getElementById("languageControl");
      return;
    }

    const control = document.createElement("label");
    control.id = "languageControl";
    control.className = "language-control";

    const label = document.createElement("span");
    label.className = "language-control-label";
    const select = document.createElement("select");
    select.id = "languageSelect";
    select.name = "language";

    localeCodes().forEach((code) => {
      const option = document.createElement("option");
      option.value = code;
      option.textContent = localeDefinition(code).name || code;
      select.append(option);
    });

    select.value = currentLocale;
    select.addEventListener("pointerdown", (event) => event.stopPropagation());
    select.addEventListener("keydown", (event) => event.stopPropagation());
    select.addEventListener("keyup", (event) => event.stopPropagation());
    select.addEventListener("change", () => {
      const nextLocale = normalizeLocale(select.value);
      if (!nextLocale || nextLocale === currentLocale) {
        return;
      }

      currentLocale = nextLocale;
      saveLocale(nextLocale);
      applyStaticTranslations();
      // Three.js keeps the road-sign CanvasTextures private. Reloading reconstructs them
      // with the selected locale without modifying gameplay state or the recovered bundle.
      window.location.reload();
    });

    control.append(label, select);
    muteButton.insertAdjacentElement("afterend", control);
    languageControl = control;
  }

  function updateLanguageControl() {
    if (!languageControl) {
      return;
    }

    const label = languageControl.querySelector(".language-control-label");
    const select = languageControl.querySelector("select");
    if (label) {
      label.textContent = translate("lang.label");
    }
    if (select) {
      select.value = currentLocale;
      select.setAttribute("aria-label", translate("lang.label"));
    }
  }

  function applyStaticTranslations() {
    const current = localeDefinition(currentLocale);
    document.documentElement.lang = current.htmlLang || currentLocale;
    document.documentElement.style.setProperty("--i18n-font", current.font || "sans-serif");
    document.title = translate("app.title");

    setText(document.getElementById("loading"), "loading.text");

    const hudLabels = document.querySelectorAll("#hud .hud-chip .label");
    setText(hudLabels[0], "hud.timer");
    setText(hudLabels[1], "hud.distance");
    setText(document.querySelector("#hud .force-label"), "hud.force");
    translateBrakeText(document.getElementById("brakeText"));

    setText(document.querySelector("#menu .brand"), "menu.brand");
    setText(document.querySelector("#menu h1"), "menu.title");
    setText(document.querySelector("#menu .tagline"), "menu.tagline");
    const rules = document.querySelectorAll("#menu .rules li");
    RULE_KEYS.forEach((key, index) => setRuleMarkup(rules[index], key));
    setText(rules[3], "menu.rule4");
    setText(document.getElementById("startBtn"), "menu.start");
    translateMuteText(document.getElementById("muteBtn"));
    translateHintText(document.getElementById("keyHint"));

    translateResultTitle(document.getElementById("resultTitle"));
    translateResultSub(document.getElementById("resultSub"));
    const statLabels = document.querySelectorAll("#result .stats .label");
    ["result.statV0", "result.statTime", "result.statDist", "result.statForce"].forEach((key, index) => {
      setText(statLabels[index], key);
    });
    setText(document.querySelector("#result .chart-title"), "result.chartTitle");
    const legends = document.querySelectorAll("#result .legend");
    ["result.legendSpeed", "result.legendForce", "result.legendLimit"].forEach((key, index) => {
      setText(legends[index], key);
    });
    setText(document.querySelector("#result .score-box .label"), "result.score");
    setText(document.getElementById("retryBtn"), "result.retry");
    translateSubmitMessage(document.getElementById("submitMsg"));

    setText(document.querySelector("#board h2"), "board.title");
    setAttribute(document.getElementById("boardClose"), "aria-label", "board.close");
    const boardColumns = document.querySelectorAll("#board .board-cols span");
    ["board.colName", "board.colSpeed", "board.colTime", "board.colScore"].forEach((key, index) => {
      setText(boardColumns[index + 1], key);
    });
    translateBoardList(document.getElementById("boardList"));
    translateToast(document.getElementById("toast"));
    updateLanguageControl();
  }

  function localizeSignLines(lines) {
    if (!Array.isArray(lines)) {
      return lines;
    }

    return lines.flatMap((line) => {
      const key = SIGN_KEYS[String(line)];
      const translated = key ? translate(key) : String(line);
      return translated.split(/\r?\n/);
    });
  }

  window.I18N_RUNTIME = {
    getLocale: () => currentLocale,
    getSignFont: () => localeDefinition(currentLocale).font || "sans-serif",
    localizeSignLines
  };

  installLanguageControl();
  applyStaticTranslations();
  observeDynamicText();
}());
