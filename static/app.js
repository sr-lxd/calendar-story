function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text || "";
}

function today() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function pad2(num) {
  return String(num).padStart(2, "0");
}

function toMonthDay(dateText) {
  if (!dateText) return "";
  const fullMatch = String(dateText).trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (fullMatch) {
    return `${fullMatch[2]}-${fullMatch[3]}`;
  }
  const mdMatch = String(dateText).trim().match(/^(\d{1,2})[-/.](\d{1,2})$/);
  if (mdMatch) {
    return `${pad2(mdMatch[1])}-${pad2(mdMatch[2])}`;
  }
  return String(dateText).trim();
}

function todayMonthDay() {
  return toMonthDay(today());
}

function isDatePickerInput(input) {
  return !!(input && input.type === "date");
}

function normalizeQueryDate(rawText) {
  const text = String(rawText || "").trim();
  if (!text) return today();

  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return text;
  }

  let matched = text.match(/^(\d{1,2})[-/.](\d{1,2})$/);
  if (!matched) {
    matched = text.match(/^(\d{1,2})月(\d{1,2})日?$/);
  }
  if (!matched) return "";

  const year = new Date().getFullYear();
  const month = Number(matched[1]);
  const day = Number(matched[2]);
  if (!Number.isInteger(month) || !Number.isInteger(day)) return "";
  if (month < 1 || month > 12 || day < 1 || day > 31) return "";

  const dt = new Date(year, month - 1, day);
  if (dt.getFullYear() !== year || dt.getMonth() !== month - 1 || dt.getDate() !== day) {
    return "";
  }
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

function weatherHeadline(dateText) {
  return `\u4eca\u65e5\u5929\u6c14\uff08${dateText || today()}\uff09`;
}

function normalizeKarlText(text) {
  if (text == null) return "";
  return String(text).replace(/卡尔\s*[·•・‧･]?\s*威特/g, "卡尔·威特");
}

function seasonFromDateText(dateText) {
  const m = String(dateText || "").match(/^\d{4}-(\d{2})-\d{2}$/);
  const month = m ? Number(m[1]) : new Date().getMonth() + 1;
  if (month === 12 || month <= 2) return "冬季";
  if (month <= 5) return "春季";
  if (month <= 8) return "夏季";
  return "秋季";
}

function buildWellnessFallback(data) {
  const dateText = data?.solar?.date || today();
  const season = seasonFromDateText(dateText);
  const jieqi = (data?.jieqi?.name || "").trim() || "当下节气";
  return {
    tip:
      `• 饮食调理：${season}建议三餐定时、清淡均衡，晚餐七分饱并注意饮水。\n` +
      "• 运动指导：安排20-40分钟中低强度活动（快走/拉伸/轻力量），以微汗为宜。\n" +
      "• 作息安排：尽量23点前入睡，晨起接触自然光10分钟，帮助稳定生物节律。\n" +
      `• 情绪调节：结合“${jieqi}”做3-5分钟呼吸放松，睡前记录1件积极小事。`,
    breakfast: `${season}早餐建议：杂粮粥或燕麦+鸡蛋+水果，避免空腹只喝咖啡。`,
    lunch: "午餐建议：优质蛋白（鱼/鸡胸/豆腐）+两份蔬菜+少量主食，八分饱为宜。",
    dinner: "晚餐建议：清淡易消化（蔬菜汤+蒸蛋+少量粗粮），尽量在睡前3小时完成。",
  };
}

function buildKarlTaskFallback(karlTip) {
  if (!karlTip?.birth_date) {
    return { dailyTheme: "", main: "", backup: "", advanced: "", observation: "", reviewQuestion: "" };
  }
  const fineFocus = normalizeKarlText(karlTip?.fine_focus || "");
  const phase = normalizeKarlText(karlTip?.phase || "");
  const phaseLabel = phase || "当前发展阶段";
  const focusText = fineFocus || "先示范再让孩子尝试表达";
  const dailyTheme = normalizeKarlText(karlTip?.daily_theme || "日常养成");
  return {
    dailyTheme,
    main: `围绕“${phaseLabel}”安排1次12-20分钟高质量亲子任务，重点放在“${focusText}”。`,
    backup: "备选任务：准备一个5-10分钟轻量互动小游戏（轮流、命名、复述三选一）。",
    advanced: "进阶任务：结束后做2分钟复盘，记录“今天最顺利一步”和“明天优化一步”。",
    observation: "观察点：专注时长、指令理解速度、情绪稳定度、主动表达频次。",
    reviewQuestion: "今天哪一步最顺利？明天先从哪一步开始？",
  };
}

function renderList(id, items, formatter) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    const li = document.createElement("li");
    li.textContent = "（无）";
    el.appendChild(li);
    return;
  }
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = formatter(item);
    el.appendChild(li);
  });
}

function renderPeopleList(id, items) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    const li = document.createElement("li");
    li.textContent = "（暂无相关人物）";
    el.appendChild(li);
    return;
  }

  const filtered = items.filter((item) => {
    if (!item || typeof item !== "object") return false;
    const name = (item.name || "").trim();
    const desc = (item.desc || "").trim();
    const quote = (item.quote || "").trim();
    const year = (item.year || "").trim();
    const allUnknown =
      (name === "" || name === "暂无") &&
      (desc === "" || desc === "暂无") &&
      (quote === "" || quote === "暂无") &&
      (year === "" || year === "不详");
    return !allUnknown;
  });

  if (filtered.length === 0) {
    const li = document.createElement("li");
    li.textContent = "（暂无相关人物）";
    el.appendChild(li);
    return;
  }

  filtered.forEach((item) => {
    const li = document.createElement("li");
    const main = document.createElement("div");
    main.textContent = `${item.year || ""} ${item.name || ""}：${item.desc || ""}`;
    li.appendChild(main);
    if (item.quote && item.quote !== "暂无") {
      const quote = document.createElement("div");
      quote.textContent = `观点/名言：${item.quote}`;
      quote.classList.add("text-muted");
      li.appendChild(quote);
    }
    el.appendChild(li);
  });
}

const TIPS = [
  "查询状态会显示“查询并更新数据中（n分n秒）...”，可直观看到累计耗时。",
  "先选日期再点查询，日期栏右侧支持一键返回今日。",
  "历史查询按日期倒序排列，可快速回看已生成结果。",
  "未勾选强制刷新时优先读缓存；勾选后会重新生成并更新缓存。",
  "文化与生活方式卡片已支持“穿衣建议”字段。",
  "当日养生与三餐建议优先由 AI 生成，异常时自动使用兜底内容。",
  "育儿提示的生日默认留空；输入后才会生成对应年龄阶段的建议。",
  "查询中按钮会禁用并显示加载状态，请勿重复点击。",
  "页面内容由 AI 生成，仅供学习和生活参考。",
];

let isLoading = false;
let statusTimerId = null;
let statusTimerStartedAt = 0;
let statusAutoClearId = null;
let tipsAutoHideId = null;
let karlHintAutoClearId = null;
const KARL_BIRTH_HINT_DEFAULT = "生日默认留空。精确生日保存在本机；AI只收到年龄阶段和活动上下文。";

function formatElapsedCn(elapsedMs) {
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}分${seconds}秒`;
}

function setKarlBirthHint(text, active = false) {
  const el = document.getElementById("karlBirthHint");
  if (!el) return;
  const value = text || KARL_BIRTH_HINT_DEFAULT;
  el.textContent = value;
  el.classList.toggle("text-primary", !!active && !!text);
  el.classList.toggle("text-muted", !(!!active && !!text));
}

function scheduleKarlHintReset(delayMs = 3500) {
  if (karlHintAutoClearId) {
    clearTimeout(karlHintAutoClearId);
  }
  karlHintAutoClearId = setTimeout(() => {
    if (!isLoading) setKarlBirthHint("", false);
    karlHintAutoClearId = null;
  }, delayMs);
}

function startStatusTimer(prefixText = "查询并更新数据中", onTick = null) {
  if (statusAutoClearId) {
    clearTimeout(statusAutoClearId);
    statusAutoClearId = null;
  }
  if (statusTimerId) {
    clearInterval(statusTimerId);
    statusTimerId = null;
  }
  const statusSetter = typeof onTick === "function" ? onTick : setStatus;
  statusTimerStartedAt = Date.now();
  const tick = () => {
    const elapsed = Date.now() - statusTimerStartedAt;
    statusSetter(`${prefixText}（${formatElapsedCn(elapsed)}）...`);
  };
  tick();
  statusTimerId = setInterval(tick, 1000);
}

function stopStatusTimer() {
  if (statusTimerId) {
    clearInterval(statusTimerId);
    statusTimerId = null;
  }
  if (!statusTimerStartedAt) return 0;
  const elapsed = Date.now() - statusTimerStartedAt;
  statusTimerStartedAt = 0;
  return elapsed;
}

function setLoadingUI(loading) {
  const btn = document.getElementById("submitBtn");
  const btnText = btn ? btn.querySelector(".btn-text") : null;
  const btnSpinner = btn ? btn.querySelector(".btn-spinner") : null;
  if (btn) {
    btn.disabled = loading;
    if (btnText) btnText.textContent = loading ? "查询中..." : "查询";
    if (btnSpinner) btnSpinner.classList.toggle("d-none", !loading);
  }
  const dateInput = document.getElementById("dateInput");
  if (dateInput) dateInput.disabled = loading;
  const historySelect = document.getElementById("historySelect");
  if (historySelect) historySelect.disabled = loading;
  const forceRefresh = document.getElementById("forceRefresh");
  if (forceRefresh) forceRefresh.disabled = loading;
  const quickTodayBtn = document.getElementById("quickTodayBtn");
  if (quickTodayBtn) quickTodayBtn.disabled = loading;
  document.querySelectorAll(".quick-birth-btn").forEach((btn) => {
    btn.disabled = loading;
  });
}

function startTips() {
  const wrap = document.getElementById("tips");
  const span = document.getElementById("tipsText");
  if (!wrap || !span) return;
  if (tipsAutoHideId) {
    clearTimeout(tipsAutoHideId);
    tipsAutoHideId = null;
  }
  if (!span.dataset.ready) {
    const loopText = TIPS.join(" ｜ ");
    span.textContent = `${loopText} ｜ ${loopText}`;
    span.dataset.ready = "1";
  }
  wrap.classList.remove("d-none");
  wrap.classList.add("is-active");
  span.classList.add("animate");
}

function stopTips() {
  const wrap = document.getElementById("tips");
  if (wrap) wrap.classList.remove("is-active");
  const span = document.getElementById("tipsText");
  if (span) span.classList.remove("animate");
  if (tipsAutoHideId) {
    clearTimeout(tipsAutoHideId);
  }
  tipsAutoHideId = setTimeout(() => {
    const el = document.getElementById("tips");
    if (el && !isLoading) el.classList.add("d-none");
    tipsAutoHideId = null;
  }, 300);
}

function renderWeather(data, fallbackCity) {
  const el = document.getElementById("weather");
  if (!el) return;
  const dateText = data?.date || today();
  const headline = weatherHeadline(dateText);
  if (!data || data.error) {
    const cityName = fallbackCity || "\u4e0a\u6d77\u91d1\u5c71";
    el.textContent = `${cityName} ${headline}\uff1a\u6682\u65e0`;
    return;
  }
  const parts = [];
  if (data.desc) parts.push(data.desc);
  if (data.temp_min != null && data.temp_max != null) {
    parts.push(`${data.temp_min}~${data.temp_max}\u2103`);
  } else if (data.temperature != null) {
    parts.push(`${data.temperature}\u2103`);
  }
  if (data.precip_prob != null) parts.push(`\u964d\u6c34\u6982\u7387${data.precip_prob}%`);
  if (data.wind_speed != null) parts.push(`\u98ce\u901f${data.wind_speed}km/h`);
  const location = data.location || fallbackCity || "\u4e0a\u6d77\u91d1\u5c71";
  const summary = parts.length ? parts.join(" \u00b7 ") : "\u6682\u65e0";
  el.textContent = `${location} ${headline}\uff1a${summary}`;
}

function getSelectedCity() {
  const select = document.getElementById("citySelect");
  return select ? select.value : "";
}

function getChildBirthDate() {
  const input = document.getElementById("karlBirthInput");
  return input && input.value ? input.value : "";
}

function updateQuickTodayHighlight() {
  const btn = document.getElementById("quickTodayBtn");
  const dateInput = document.getElementById("dateInput");
  if (!btn || !dateInput) return;
  const selectedDate = normalizeQueryDate(dateInput.value || "");
  const needHighlight = !!selectedDate && selectedDate !== today();
  btn.classList.toggle("is-attention", needHighlight);
  btn.setAttribute("aria-pressed", needHighlight ? "true" : "false");
}

function updateQuickBirthSelection(selectedBirth) {
  const current = String(selectedBirth || "").trim();
  document.querySelectorAll(".quick-birth-btn").forEach((btn) => {
    const isSelected = (btn.dataset.birth || "") === current;
    btn.classList.toggle("is-selected", isSelected);
    btn.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });
}

async function loadWeather(city) {
  const el = document.getElementById("weather");
  const cityName = city || getSelectedCity() || "\u4e0a\u6d77\u91d1\u5c71";
  if (el) el.textContent = `${cityName} ${weatherHeadline()}\uff1a\u52a0\u8f7d\u4e2d...`;
  try {
    const params = new URLSearchParams({ city: cityName });
    const res = await fetch(`/api/weather?${params.toString()}`);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "\u5929\u6c14\u83b7\u53d6\u5931\u8d25");
    }
    renderWeather(data, cityName);
  } catch (err) {
    if (el) el.textContent = `${cityName} ${weatherHeadline()}\uff1a\u83b7\u53d6\u5931\u8d25`;
  }
}

async function fetchData(dateStr, refresh, childBirth) {
  const params = new URLSearchParams({ date: dateStr });
  if (childBirth) params.set("child_birth", childBirth);
  if (refresh) {
    params.set("refresh", "1");
  }
  const res = await fetch(`/api/full?${params.toString()}`);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function renderData(data) {
  document.getElementById("result").classList.remove("d-none");

  setText("solarDate", data.solar?.date);
  setText("weekday", data.solar?.weekday);
  setText("weekQuarter", `${data.solar?.week_of_year || ""} / ${data.solar?.quarter || ""}`);
  setText("moonPhase", data.solar?.moon_phase);

  const lunar = data.lunar || {};
  const leap = lunar.is_leap_month ? "闰" : "";
  setText("lunarInfo", `${lunar.year || ""} ${leap}${lunar.month || ""}${lunar.day || ""}`);
  setText("ganzhiInfo", `${lunar.ganzhi_year || ""} ${lunar.ganzhi_month || ""} ${lunar.ganzhi_day || ""}`);
  setText("zodiac", lunar.zodiac || "");
  setText("jieqiName", data.jieqi?.name || "");
  setText("jieqiDesc", data.jieqi?.desc || "");

  const huangli = data.huangli || {};
  setText("huangliYi", (huangli.yi || []).join("、"));
  setText("huangliJi", (huangli.ji || []).join("、"));
  setText("chongSha", huangli.chong_sha || "");
  setText("jiShen", (huangli.ji_shen || []).join("、"));
  setText("xiongShen", (huangli.xiong_shen || []).join("、"));
  setText("jiShi", (huangli.ji_shi || []).join("、"));

  renderList("festivals", data.festivals, (i) => `${i.name || ""}（${i.type || ""}）`);
  renderList("memorialDays", data.memorial_days, (i) => `${i.name || ""}（${i.type || ""}）`);

  renderList("historyChina", data.history?.china, (i) => `${i.year || ""} - ${i.event || ""}`);
  renderList("historyWorld", data.history?.world, (i) => `${i.year || ""} - ${i.event || ""}`);

  renderPeopleList("peopleBirths", data.people?.births);
  renderPeopleList("peopleDeaths", data.people?.deaths);

  setText("cultureQuoteCn", data.culture?.quote_cn || "");
  setText("cultureQuoteEn", data.culture?.quote_en || "");
  setText("cultureWork", (data.culture?.work || []).join("、"));
  setText("cultureGreeting", data.culture?.greeting || "");
  setText("lifestyleFood", (data.lifestyle?.food || []).join("、"));
  setText("lifestyleTips", (data.lifestyle?.tips || []).join("、"));
  setText("lifestyleClothing", data.lifestyle?.clothing || "");
  const dailyWellness = data.daily_wellness || {};
  const wellnessFallback = buildWellnessFallback(data);
  setText("wellnessTip", dailyWellness.tip || data.wellness_tip || wellnessFallback.tip);
  setText("wellnessBreakfast", dailyWellness.breakfast || wellnessFallback.breakfast);
  setText("wellnessLunch", dailyWellness.lunch || wellnessFallback.lunch);
  setText("wellnessDinner", dailyWellness.dinner || wellnessFallback.dinner);

  const karlTip = data.karl_witte_tip || {};
  const karlFallback = buildKarlTaskFallback(karlTip);
  const karlTipFallback = normalizeKarlText(karlTip.tip || "");
  const karlBirthDate = normalizeKarlText(karlTip.birth_date || "未设置");
  const karlAge = normalizeKarlText(karlTip.age || "");
  const karlPhase = normalizeKarlText(karlTip.phase || "");
  const karlFinePhase = normalizeKarlText(karlTip.phase_fine || "");
  const karlDailyTheme = normalizeKarlText(karlTip.daily_theme || karlFallback.dailyTheme);
  const karlFineFocus = normalizeKarlText(karlTip.fine_focus || "");
  const karlPrinciple = normalizeKarlText(karlTip.principle || "");
  const karlTipMain = normalizeKarlText(karlTip.tip_main || karlTipFallback || karlFallback.main);
  const karlTipBackup = normalizeKarlText(karlTip.tip_backup || karlFallback.backup);
  const karlTipAdvanced = normalizeKarlText(karlTip.tip_advanced || karlFallback.advanced);
  const karlObservation = normalizeKarlText(karlTip.observation || karlFallback.observation);
  const karlReviewQuestion = normalizeKarlText(karlTip.review_question || karlFallback.reviewQuestion);
  const karlTipText = normalizeKarlText(karlTip.tip || karlTipMain || karlFallback.main || "输入儿童生日后生成建议。");

  setText("karlBirthDate", karlBirthDate);
  const birthInput = document.getElementById("karlBirthInput");
  if (birthInput && karlTip.birth_date) birthInput.value = karlTip.birth_date;
  if (birthInput) updateQuickBirthSelection(birthInput.value);
  setText("karlAge", karlAge);
  setText("karlPhase", karlPhase);
  setText("karlFinePhase", karlFinePhase);
  setText("karlDailyTheme", karlDailyTheme);
  setText("karlFineFocus", karlFineFocus);
  setText("karlPrinciple", karlPrinciple);
  setText("karlTipMain", karlTipMain);
  setText("karlTipBackup", karlTipBackup);
  setText("karlTipAdvanced", karlTipAdvanced);
  setText("karlObservation", karlObservation);
  setText("karlReviewQuestion", karlReviewQuestion);
  setText("karlTip", karlTipText);

  setText("aiNotice", data.ai_notice || "");
  const meta = data._meta || {};
  setText("metaInfo", `模型：${meta.model || ""} | 缓存：${meta.cached ? "是" : "否"} | 生成时间：${meta.created_at || ""}`);
}

function showError(msg) {
  const el = document.getElementById("error");
  el.textContent = msg;
  el.classList.remove("d-none");
}

function clearError() {
  const el = document.getElementById("error");
  el.classList.add("d-none");
  el.textContent = "";
}

function setStatus(msg) {
  document.getElementById("status").textContent = msg;
}

function scheduleStatusClear(delayMs = 3500) {
  if (statusAutoClearId) {
    clearTimeout(statusAutoClearId);
  }
  statusAutoClearId = setTimeout(() => {
    if (!isLoading) {
      setStatus("");
    }
    statusAutoClearId = null;
  }, delayMs);
}

function initDate() {
  const input = document.getElementById("dateInput");
  if (!input) return;
  if (isDatePickerInput(input)) {
    if (!input.value) input.value = today();
    return;
  }
  if (!input.value) {
    input.value = todayMonthDay();
    return;
  }
  input.value = toMonthDay(input.value);
}

function formatHistoryLabel(item) {
  if (!item || typeof item !== "object") return "";
  return toMonthDay(item.date || "");
}

function populateHistorySelect(items, selectedDate) {
  const select = document.getElementById("historySelect");
  if (!select) return;
  select.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "暂无历史";
    select.appendChild(opt);
    return;
  }
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "选择历史日期";
  select.appendChild(placeholder);
  items.forEach((item) => {
    if (!item || !item.date) return;
    const opt = document.createElement("option");
    opt.value = item.date;
    opt.textContent = formatHistoryLabel(item) || item.date;
    select.appendChild(opt);
  });
  if (selectedDate) {
    select.value = selectedDate;
  }
}

async function loadHistory(selectedDate) {
  const select = document.getElementById("historySelect");
  if (!select) return { items: [], last_date: "" };
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    let items = Array.isArray(data.items) ? data.items.slice() : [];
    const lastDate = data.last_date || "";
    if (lastDate && !items.some((item) => item && item.date === lastDate)) {
      items.push({ date: lastDate });
    }
    items = items
      .filter((item) => item && item.date)
      .sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    populateHistorySelect(items, selectedDate || lastDate);
    return { items, last_date: lastDate };
  } catch (err) {
    populateHistorySelect([], "");
    return { items: [], last_date: "" };
  }
}

async function runQuery(dateStr, options = {}) {
  if (!dateStr || isLoading) return;
  clearError();
  const loadingPrefix = options.loadingPrefix || "查询并更新数据中";
  const donePrefix = options.donePrefix || "完成";
  const useKarlHint = options.statusTarget === "karl";
  if (useKarlHint) {
    if (karlHintAutoClearId) {
      clearTimeout(karlHintAutoClearId);
      karlHintAutoClearId = null;
    }
    setStatus("");
  }
  startStatusTimer(
    loadingPrefix,
    useKarlHint ? (msg) => setKarlBirthHint(msg, true) : null
  );
  startTips();
  isLoading = true;
  setLoadingUI(true);
  let queryOk = false;
  try {
    const childBirth = options.childBirth || getChildBirthDate();
    const data = await fetchData(dateStr, options.refresh, childBirth);
    renderData(data);
    queryOk = true;
    if (options.refreshHistory) {
      await loadHistory(dateStr);
    }
  } catch (err) {
    showError(err.message || "请求失败");
  } finally {
    const elapsed = stopStatusTimer();
    if (queryOk) {
      if (useKarlHint) {
        setKarlBirthHint(`${donePrefix}（用时${formatElapsedCn(elapsed)}）`, true);
        scheduleKarlHintReset();
      } else {
        setStatus(`${donePrefix}（用时${formatElapsedCn(elapsed)}）`);
        scheduleStatusClear();
      }
    } else {
      if (useKarlHint) {
        setKarlBirthHint(`儿童生日更新失败（已用时${formatElapsedCn(elapsed)}）`, true);
        scheduleKarlHintReset(5000);
      } else {
        setStatus(`查询失败（已用时${formatElapsedCn(elapsed)}）`);
      }
    }
    stopTips();
    isLoading = false;
    setLoadingUI(false);
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  initDate();
  updateQuickTodayHighlight();
  await loadWeather();
  const form = document.getElementById("queryForm");
  const dateInput = document.getElementById("dateInput");
  const historySelect = document.getElementById("historySelect");
  const forceRefresh = document.getElementById("forceRefresh");
  const citySelect = document.getElementById("citySelect");
  const karlBirthInput = document.getElementById("karlBirthInput");
  const quickTodayBtn = document.getElementById("quickTodayBtn");
  const quickBirthButtons = document.querySelectorAll(".quick-birth-btn");

  if (karlBirthInput) updateQuickBirthSelection(karlBirthInput.value);

  if (citySelect) {
    citySelect.addEventListener("change", async (e) => {
      await loadWeather(e.target.value);
    });
  }

  if (quickBirthButtons && quickBirthButtons.length) {
    quickBirthButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const quickBirth = btn.dataset.birth || "";
        if (!quickBirth || !karlBirthInput || isLoading) return;
        karlBirthInput.value = quickBirth;
        updateQuickBirthSelection(quickBirth);
        karlBirthInput.dispatchEvent(new Event("change"));
      });
    });
  }

  if (quickTodayBtn) {
    quickTodayBtn.addEventListener("click", () => {
      if (!dateInput || isLoading) return;
      dateInput.value = isDatePickerInput(dateInput) ? today() : todayMonthDay();
      updateQuickTodayHighlight();
      if (historySelect) historySelect.value = "";
      if (form) {
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.dispatchEvent(new Event("submit", { cancelable: true }));
        }
      }
    });
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const rawDate = dateInput ? dateInput.value : "";
      const dateStr = normalizeQueryDate(rawDate);
      if (!dateStr) {
        showError("日期格式请填写“YYYY-MM-DD”或“月-日”（如03-08）。");
        setStatus("");
        return;
      }
      if (dateInput) {
        dateInput.value = isDatePickerInput(dateInput) ? dateStr : toMonthDay(dateStr);
      }
      updateQuickTodayHighlight();
      const force = forceRefresh ? forceRefresh.checked : false;
      if (force) {
        await runQuery(dateStr, { refresh: true, refreshHistory: true });
        return;
      }
      await runQuery(dateStr, { refresh: false, refreshHistory: true });
    });
  }

  if (karlBirthInput) {
    karlBirthInput.addEventListener("change", async () => {
      updateQuickBirthSelection(karlBirthInput.value);
      const dateStr = normalizeQueryDate(dateInput ? dateInput.value : "");
      if (!dateStr) return;
      await runQuery(dateStr, {
        refresh: false,
        refreshHistory: false,
        childBirth: getChildBirthDate(),
        loadingPrefix: "已切换儿童生日，正在更新内容",
        donePrefix: "儿童生日更新完成",
        statusTarget: "karl",
      });
    });
  }

  if (historySelect) {
    historySelect.addEventListener("change", async (e) => {
      const dateStr = e.target.value;
      if (!dateStr) return;
      if (dateInput) {
        dateInput.value = isDatePickerInput(dateInput) ? dateStr : toMonthDay(dateStr);
      }
      updateQuickTodayHighlight();
      await runQuery(dateStr, { refreshHistory: false });
    });
  }

  if (dateInput) {
    dateInput.addEventListener("change", updateQuickTodayHighlight);
    dateInput.addEventListener("input", updateQuickTodayHighlight);
  }
  setKarlBirthHint("", false);

  const history = await loadHistory();
  const todayValue = today();
  if (history.last_date && history.last_date === todayValue) {
    if (dateInput) {
      dateInput.value = isDatePickerInput(dateInput)
        ? history.last_date
        : toMonthDay(history.last_date);
    }
    updateQuickTodayHighlight();
    await runQuery(history.last_date, { refreshHistory: false });
  }
});
