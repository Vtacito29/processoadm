(() => {
  const normalize = (value) =>
    (value || "")
      .toString()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim();

  const isLinkedRow = (row) => {
    if (!row) return false;
    const cls = row.className || "";
    return cls.includes("ficha") || cls.includes("history");
  };

  const shouldSkipColumn = (th, index) => {
    if (index === 0) return true;
    const txt = normalize(th.textContent || "");
    if (!txt) return true;
    return txt === "acoes" || txt === "acao";
  };

  const getBaseRows = (table) =>
    Array.from(table.querySelectorAll("tbody tr")).filter((row) => !isLinkedRow(row));

  const readCellText = (row, colIdx) => {
    const cell = row.children[colIdx];
    return (cell?.innerText || "").replace(/\s+/g, " ").trim();
  };

  const DATE_PT_BR_RE = /^(0[1-9]|[12][0-9]|3[01])\/(0[1-9]|1[0-2])\/\d{4}$/;

  const ptBrToIsoDate = (value) => {
    const raw = (value || "").toString().trim();
    if (!DATE_PT_BR_RE.test(raw)) return "";
    const [day, month, year] = raw.split("/");
    return `${year}-${month}-${day}`;
  };

  const isoToPtBrDate = (value) => {
    const raw = (value || "").toString().trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return "";
    const [year, month, day] = raw.split("-");
    return `${day}/${month}/${year}`;
  };

  const maskPtBrDateInput = (value) => {
    const digits = (value || "").toString().replace(/\D+/g, "").slice(0, 8);
    if (digits.length <= 2) return digits;
    if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
    return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
  };

  const DATE_FROM_TOKEN_PREFIX = "__date_from__:";
  const DATE_TO_TOKEN_PREFIX = "__date_to__:";

  const getDateRangeFromSelected = (selected) => {
    let from = "";
    let to = "";
    (selected || new Set()).forEach((value) => {
      if ((value || "").startsWith(DATE_FROM_TOKEN_PREFIX)) {
        from = value.slice(DATE_FROM_TOKEN_PREFIX.length);
      } else if ((value || "").startsWith(DATE_TO_TOKEN_PREFIX)) {
        to = value.slice(DATE_TO_TOKEN_PREFIX.length);
      } else if (DATE_PT_BR_RE.test(value || "")) {
        const iso = ptBrToIsoDate(value);
        if (iso) {
          from = iso;
          to = iso;
        }
      }
    });
    return { from, to };
  };

  const buildDateRangeTokens = (from, to) => {
    const tokens = new Set();
    if (from) tokens.add(`${DATE_FROM_TOKEN_PREFIX}${from}`);
    if (to) tokens.add(`${DATE_TO_TOKEN_PREFIX}${to}`);
    return tokens;
  };

  const hasDateRangeTokens = (selected) =>
    Boolean(
      [...(selected || [])].some(
        (value) =>
          (value || "").startsWith(DATE_FROM_TOKEN_PREFIX) ||
          (value || "").startsWith(DATE_TO_TOKEN_PREFIX),
      ),
    );

  const matchesDateRange = (rawValue, selected) => {
    const { from, to } = getDateRangeFromSelected(selected);
    const iso = ptBrToIsoDate(rawValue);
    if (!iso) return false;
    if (from && iso < from) return false;
    if (to && iso > to) return false;
    return true;
  };

  const CALENDAR_MONTHS_PT = [
    "janeiro",
    "fevereiro",
    "marco",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
  ];
  const CALENDAR_WEEKDAYS_PT = ["D", "S", "T", "Q", "Q", "S", "S"];
  const DATE_COLUMN_SLUGS = new Set([
    "data_entrada",
    "data_de_entrada",
    "data_de_entrada_no_gabinete",
    "prazo",
    "data_de_entrada_na_gerencia",
    "entrada_gabinete",
    "data_entrada_gabinete",
    "prazo_equipe",
    "finalizado_em",
    "data_da_finalizacao",
  ]);

  const isoToDate = (value) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  };

  const dateToIso = (value) => {
    if (!(value instanceof Date) || Number.isNaN(value.getTime())) return "";
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };

  const addMonths = (value, amount) => {
    const base = value instanceof Date ? new Date(value.getFullYear(), value.getMonth(), 1) : new Date();
    return new Date(base.getFullYear(), base.getMonth() + amount, 1);
  };

  const sameDate = (left, right) =>
    left instanceof Date &&
    right instanceof Date &&
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate();

  const betweenDates = (value, start, end) => {
    if (!(value instanceof Date) || !(start instanceof Date) || !(end instanceof Date)) return false;
    const current = dateToIso(value);
    const from = dateToIso(start);
    const to = dateToIso(end);
    return Boolean(current && from && to && current >= from && current <= to);
  };

  const makePersistKey = (headers) => {
    const headerSig = headers
      .map((th) => normalize((th.textContent || "").replace(/\s+/g, " ")))
      .join("|");
    const params = new URLSearchParams(window.location.search);
    params.delete("page");
    return `table_filter_v2:${window.location.pathname}?${params.toString()}::${headerSig}`;
  };

  const initTableFilters = (table) => {
    if (!table || table.dataset.colFilterBound === "1") return;
    const headers = Array.from(table.querySelectorAll("thead tr:first-child th"));
    if (!headers.length) return;

    const state = {
      filters: {},
      sort: { col: null, dir: null },
    };
    const persistKey = makePersistKey(headers);
    let activeMenu = null;
    let activeMenuCol = null;
    let cleanupMenuListeners = null;
    const isHomeDashboard = window.location.pathname === "/";
    const responsavelEquipeIdxByText = headers.findIndex((th, idx) => {
      if (shouldSkipColumn(th, idx)) return false;
      const raw = normalize(th.textContent || "").replace(/[^a-z0-9 ]/g, " ");
      return raw.includes("respons") && raw.includes("equipe");
    });
    const responsavelEquipeIdx =
      responsavelEquipeIdxByText >= 0 ? responsavelEquipeIdxByText : headers.length - 1;

    const baseRows = getBaseRows(table);
    baseRows.forEach((row, idx) => {
      if (!row.dataset.originalOrder) row.dataset.originalOrder = String(idx);
    });

    const saveState = () => {
      try {
        const filters = {};
        Object.entries(state.filters).forEach(([idx, selected]) => {
          filters[idx] = Array.from(selected || []);
        });
        const hasFilters = Object.keys(filters).length > 0;
        const hasSort = Boolean(state.sort && state.sort.col !== null && state.sort.dir);
        if (!hasFilters && !hasSort) {
          window.sessionStorage.removeItem(persistKey);
          return;
        }
        window.sessionStorage.setItem(
          persistKey,
          JSON.stringify({
            filters,
            sort: state.sort,
          }),
        );
      } catch (_err) {
        // Ignora indisponibilidade do storage.
      }
    };

    const getHeaderLabel = (idx) => {
      const th = headers[idx];
      if (!th) return `Coluna ${idx + 1}`;
      return (th.childNodes[0]?.textContent || th.textContent || "").replace(/\s+/g, " ").trim();
    };
    const getHeaderSlug = (idx) =>
      (() => {
        const th = headers[idx];
        const dataKey = (th?.dataset?.colKey || "").trim();
        if (dataKey) {
          return normalize(dataKey)
            .replace(/[^a-z0-9]+/g, "_")
            .replace(/^_+|_+$/g, "");
        }
        return normalize(getHeaderLabel(idx))
          .replace(/[^a-z0-9]+/g, "_")
          .replace(/^_+|_+$/g, "");
      })();

    const getCellComparableText = (row, colIdx) => {
      const cell = row.children[colIdx];
      const slug = getHeaderSlug(colIdx);
      let raw = readCellText(row, colIdx);

      if (slug === "responsavel_equipe" || slug === "responsavel_adm") {
        const chipTitle = cell?.querySelector?.(".chip-title");
        if (chipTitle) {
          raw = (chipTitle.innerText || chipTitle.textContent || "").replace(/\s+/g, " ").trim();
        } else {
          raw = raw.replace(/\bresponsavel\s*(adm|equipe)\b/gi, "").replace(/\s+/g, " ").trim();
        }
      }

      return raw;
    };

    const buildCfPayload = (ignoreCol = null, includeSort = false) => {
      const payload = {};
      Object.entries(state.filters).forEach(([idxStr, selected]) => {
        const idx = Number(idxStr);
        if (ignoreCol !== null && idx === ignoreCol) return;
        if (!selected || !selected.size) return;
        const slug = getHeaderSlug(idx);
        if (!slug) return;
        payload[slug] = Array.from(selected);
      });
      if (includeSort && state.sort && state.sort.col !== null && (state.sort.dir === "asc" || state.sort.dir === "desc")) {
        const sortSlug = getHeaderSlug(state.sort.col);
        if (sortSlug) {
          payload.__sort_col = [sortSlug];
          payload.__sort_dir = [state.sort.dir];
        }
      }
      return payload;
    };

    const fetchHomeColumnValues = async (colIdx) => {
      if (!isHomeDashboard) return null;
      const slug = getHeaderSlug(colIdx);
      if (!slug) return null;

      const url = new URL("/api/home-column-options", window.location.origin);
      const nextUrl = new URL(window.location.href);
      const cfPayload = buildCfPayload(colIdx);

      if (Object.keys(cfPayload).length) nextUrl.searchParams.set("cf", JSON.stringify(cfPayload));
      else nextUrl.searchParams.delete("cf");

      nextUrl.searchParams.delete("page");
      nextUrl.searchParams.delete("col");
      nextUrl.searchParams.forEach((v, k) => url.searchParams.set(k, v));
      url.searchParams.set("col", slug);

      try {
        const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
        if (!res.ok) return null;
        const data = await res.json();
        if (!data || !Array.isArray(data.values)) return null;
        const uniq = new Map();
        data.values.forEach((labelRaw) => {
          const label = (labelRaw || "").toString().trim() || "(Vazio)";
          const key = normalize(label || "(vazio)");
          if (!uniq.has(key)) uniq.set(key, label);
        });
        return [...uniq.entries()].sort((a, b) => a[1].localeCompare(b[1], "pt-BR", { numeric: true }));
      } catch (_err) {
        return null;
      }
    };

    const fetchGerenciaColumnValues = async (colIdx) => {
      if (!window.location.pathname.startsWith("/gerencia/")) return null;
      const slug = getHeaderSlug(colIdx);
      if (!slug) return null;
      const scope = table.dataset.filterScope || "interacoes";
      const pathParts = window.location.pathname.split("/").filter(Boolean);
      const nomeGerencia = pathParts.length >= 2 ? pathParts[1] : "";
      if (!nomeGerencia) return null;

      const url = new URL(`/api/gerencia-column-options/${encodeURIComponent(nomeGerencia)}`, window.location.origin);
      const nextUrl = new URL(window.location.href);
      const cfPayload = buildCfPayload(colIdx);
      if (Object.keys(cfPayload).length) nextUrl.searchParams.set("cf", JSON.stringify(cfPayload));
      else nextUrl.searchParams.delete("cf");
      nextUrl.searchParams.delete("page");
      nextUrl.searchParams.delete("page_arq");
      nextUrl.searchParams.delete("page_dev");
      nextUrl.searchParams.forEach((v, k) => url.searchParams.set(k, v));
      url.searchParams.set("scope", scope);
      url.searchParams.set("col", slug);

      try {
        const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
        if (!res.ok) return null;
        const data = await res.json();
        if (!data || !Array.isArray(data.values)) return null;
        const uniq = new Map();
        data.values.forEach((labelRaw) => {
          const label = (labelRaw || "").toString().trim() || "(Vazio)";
          const key = normalize(label || "(vazio)");
          if (!uniq.has(key)) uniq.set(key, label);
        });
        return [...uniq.entries()].sort((a, b) => a[1].localeCompare(b[1], "pt-BR", { numeric: true }));
      } catch (_err) {
        return null;
      }
    };

    const syncServerFilters = () => {
      const isGerencia = window.location.pathname.startsWith("/gerencia/");
      if (!isHomeDashboard && !isGerencia) return false;

      const currentUrl = new URL(window.location.href);
      const nextUrl = new URL(window.location.href);

      const cfPayload = buildCfPayload(null, true);
      if (Object.keys(cfPayload).length) {
        nextUrl.searchParams.set("cf", JSON.stringify(cfPayload));
      } else {
        nextUrl.searchParams.delete("cf");
      }
      const cfInput = document.getElementById("colFiltersInput");
      if (cfInput) cfInput.value = nextUrl.searchParams.get("cf") || "";

      if (isHomeDashboard && responsavelEquipeIdx >= 0) {
        const selected = state.filters[responsavelEquipeIdx];
        const vazioAtivo = Boolean(
          selected &&
            selected.size > 0 &&
            [...selected].every((v) => v === "(vazio)" || v === "" || v === "-"),
        );
        const hiddenInput = document.getElementById("respEqVazioInput");
        if (hiddenInput) hiddenInput.value = vazioAtivo ? "1" : "";
        if (vazioAtivo) nextUrl.searchParams.set("resp_eq_vazio", "1");
        else nextUrl.searchParams.delete("resp_eq_vazio");
      }

      if (nextUrl.search !== currentUrl.search) {
        nextUrl.searchParams.delete("page");
        nextUrl.searchParams.delete("page_arq");
        nextUrl.searchParams.delete("page_dev");
        if (!nextUrl.hash && isHomeDashboard) nextUrl.hash = "filtros";
        window.location.href = nextUrl.toString();
        return true;
      }
      return false;
    };

    const updateActiveFiltersSummary = () => {
      const summaryEl = document.getElementById("activeColumnFiltersHome");
      if (!summaryEl) return;
      const entries = Object.entries(state.filters)
        .map(([idxStr, selected]) => {
          const idx = Number(idxStr);
          if (!selected || !selected.size) return "";
          const values = Array.from(selected).map((v) => (v === "(vazio)" ? "(Vazio)" : v));
          const preview = values.length > 2 ? `${values.slice(0, 2).join(", ")}...` : values.join(", ");
          return `${getHeaderLabel(idx)}: ${preview}`;
        })
        .filter(Boolean);
      if (!entries.length) {
        summaryEl.textContent = "";
        summaryEl.classList.add("d-none");
        return;
      }
      summaryEl.textContent = `Filtros ativos: ${entries.join(" | ")}`;
      summaryEl.classList.remove("d-none");
    };

    const loadState = () => {
      try {
        const raw = window.sessionStorage.getItem(persistKey);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        const filters = parsed?.filters || {};
        Object.entries(filters).forEach(([idxStr, values]) => {
          const idx = Number(idxStr);
          if (!Number.isInteger(idx) || idx < 0 || idx >= headers.length) return;
          if (!Array.isArray(values) || !values.length) return;
          state.filters[idx] = new Set(values.map((v) => normalize(v)));
        });
        const col = Number(parsed?.sort?.col);
        const dir = parsed?.sort?.dir;
        if (Number.isInteger(col) && col >= 0 && col < headers.length && (dir === "asc" || dir === "desc")) {
          state.sort = { col, dir };
        }
      } catch (_err) {
        // Ignora estado corrompido.
      }
    };

    const applyUrlDrivenDefaults = () => {
      const params = new URLSearchParams(window.location.search);
      const cfRaw = params.get("cf");
      if (cfRaw) {
        try {
          const parsed = JSON.parse(cfRaw);
          if (parsed && typeof parsed === "object") {
            const sortColRaw = Array.isArray(parsed.__sort_col) ? (parsed.__sort_col[0] || "") : "";
            const sortDirRaw = Array.isArray(parsed.__sort_dir) ? (parsed.__sort_dir[0] || "") : "";
            Object.entries(parsed).forEach(([slug, values]) => {
              if (slug === "__sort_col" || slug === "__sort_dir") return;
              if (!Array.isArray(values) || !values.length) return;
              const idx = headers.findIndex((_, i) => getHeaderSlug(i) === slug);
              if (idx < 0) return;
              state.filters[idx] = new Set(values.map((v) => normalize(v)));
            });
            const sortIdx = headers.findIndex((_, i) => getHeaderSlug(i) === normalize(sortColRaw).replace(/[^a-z0-9_]+/g, "_"));
            if (sortIdx >= 0 && (sortDirRaw === "asc" || sortDirRaw === "desc")) {
              state.sort = { col: sortIdx, dir: sortDirRaw };
            }
          }
        } catch (_err) {
          // Ignora filtro de URL invalido.
        }
      }
      if (!isHomeDashboard || responsavelEquipeIdx < 0) return;
      if (params.get("resp_eq_vazio") !== "1") return;
      if (!state.filters[responsavelEquipeIdx] || !state.filters[responsavelEquipeIdx].size) {
        state.filters[responsavelEquipeIdx] = new Set(["(vazio)"]);
      }
    };

    const closeMenu = () => {
      if (cleanupMenuListeners) {
        cleanupMenuListeners();
        cleanupMenuListeners = null;
      }
      if (!activeMenu) return;
      activeMenu.remove();
      activeMenu = null;
      activeMenuCol = null;
    };

    const rowMatchesFilters = (row, ignoreCol = null) => {
      let ok = true;
      Object.entries(state.filters).forEach(([colStr, selected]) => {
        if (!ok) return;
        const col = Number(colStr);
        if (ignoreCol !== null && col === ignoreCol) return;
        const rawValue = getCellComparableText(row, col) || "(Vazio)";
        const value = normalize(rawValue || "(vazio)");
        if (!selected || !selected.size) return;
        if (hasDateRangeTokens(selected)) {
          if (!matchesDateRange(rawValue, selected)) ok = false;
          return;
        }
        if (!selected.has(value)) ok = false;
      });
      return ok;
    };

    const appendRowWithLinked = (tbody, row) => {
      tbody?.appendChild(row);
      let next = row.nextElementSibling;
      while (
        next &&
        isLinkedRow(next) &&
        next.getAttribute("data-proc-id") === row.getAttribute("data-proc-id")
      ) {
        const current = next;
        next = next.nextElementSibling;
        tbody?.appendChild(current);
      }
    };

    const applyState = ({ syncServer = false } = {}) => {
      const rows = getBaseRows(table);
      rows.forEach((row) => {
        const visible = rowMatchesFilters(row);
        row.classList.toggle("column-filter-hidden", !visible);
        row.classList.toggle("d-none", !visible);
        let next = row.nextElementSibling;
        while (
          next &&
          isLinkedRow(next) &&
          next.getAttribute("data-proc-id") === row.getAttribute("data-proc-id")
        ) {
          next.classList.toggle("column-filter-hidden", !visible);
          if (!visible) next.classList.add("d-none");
          next = next.nextElementSibling;
        }
      });

      const tbody = table.querySelector("tbody");
      if (state.sort.col !== null && state.sort.dir) {
        const col = state.sort.col;
        const dir = state.sort.dir === "asc" ? 1 : -1;
        const sorted = [...rows].sort((a, b) => {
          const va = normalize(getCellComparableText(a, col));
          const vb = normalize(getCellComparableText(b, col));
          return va.localeCompare(vb, "pt-BR", { numeric: true }) * dir;
        });
        sorted.forEach((row) => appendRowWithLinked(tbody, row));
      } else {
        const original = [...rows].sort(
          (a, b) => Number(a.dataset.originalOrder || "0") - Number(b.dataset.originalOrder || "0"),
        );
        original.forEach((row) => appendRowWithLinked(tbody, row));
      }

      headers.forEach((th, idx) => {
        const hasFilter = Boolean(state.filters[idx] && state.filters[idx].size);
        const hasSort = state.sort.col === idx;
        th.classList.toggle("col-filter-active", hasFilter || hasSort);
      });

      updateActiveFiltersSummary();
      if (syncServer && syncServerFilters()) return;
      saveState();
    };

    const openMenu = async (colIdx, btn) => {
      if (activeMenu && activeMenuCol === colIdx) {
        closeMenu();
        return;
      }
      closeMenu();

      const rows = getBaseRows(table);
      const contextRows = rows.filter((row) => rowMatchesFilters(row, colIdx));
      const uniqueMap = new Map();
      contextRows.forEach((row) => {
        const raw = getCellComparableText(row, colIdx) || "(Vazio)";
        const key = normalize(raw || "(vazio)");
        if (!uniqueMap.has(key)) uniqueMap.set(key, raw);
      });
      let values = [...uniqueMap.entries()].sort((a, b) => a[1].localeCompare(b[1], "pt-BR", { numeric: true }));
      let remoteValues = await fetchHomeColumnValues(colIdx);
      if (!remoteValues) remoteValues = await fetchGerenciaColumnValues(colIdx);
      if (remoteValues && remoteValues.length) {
        values = remoteValues;
      }
      const nonEmptyValues = values
        .map(([, label]) => (label || "").toString().trim())
        .filter((label) => label && label !== "(Vazio)" && label !== "-");
      const currentSlug = getHeaderSlug(colIdx);
      const isDateColumn =
        DATE_COLUMN_SLUGS.has(currentSlug) ||
        (nonEmptyValues.some((label) => DATE_PT_BR_RE.test(label)) &&
          nonEmptyValues.every(
            (label) => DATE_PT_BR_RE.test(label) || normalize(label) === "sem prazo",
          ));

      const selectedNow = state.filters[colIdx] ? new Set(state.filters[colIdx]) : new Set(values.map(([k]) => k));
      let selectedTemp = new Set(selectedNow);

      const menu = document.createElement("div");
      menu.className = "table-col-filter-menu";
      menu.innerHTML = isDateColumn
        ? `
        <div class="table-filter-actions">
          <button type="button" class="table-filter-action-btn" data-sort="asc"><i class="bi bi-sort-alpha-down" aria-hidden="true"></i> Ordem crescente</button>
          <button type="button" class="table-filter-action-btn" data-sort="desc"><i class="bi bi-sort-alpha-up" aria-hidden="true"></i> Ordem decrescente</button>
          <button type="button" class="table-filter-action-btn" data-sort="clear"><i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i> Limpar ordenacao</button>
        </div>
        <div class="table-filter-date-wrap">
          <div class="table-filter-date-summary" data-date-summary></div>
          <div class="table-filter-calendar" data-calendar>
            <div class="table-filter-calendar-header">
              <button type="button" class="table-filter-calendar-nav" data-cal-nav="-1" aria-label="Mes anterior">&lsaquo;</button>
              <div class="table-filter-calendar-title" data-cal-title></div>
              <button type="button" class="table-filter-calendar-nav" data-cal-nav="1" aria-label="Proximo mes">&rsaquo;</button>
            </div>
            <div class="table-filter-calendar-weekdays">
              ${CALENDAR_WEEKDAYS_PT.map((label) => `<span>${label}</span>`).join("")}
            </div>
            <div class="table-filter-calendar-grid" data-cal-grid></div>
          </div>
        </div>
        <div class="table-filter-footer">
          <button type="button" class="btn btn-outline-secondary btn-sm" data-clear>Limpar filtro</button>
          <button type="button" class="btn btn-outline-secondary btn-sm" data-cancel>Cancelar</button>
          <button type="button" class="btn btn-primary btn-sm" data-ok>OK</button>
        </div>
      `
        : `
        <div class="table-filter-actions">
          <button type="button" class="table-filter-action-btn" data-sort="asc"><i class="bi bi-sort-alpha-down" aria-hidden="true"></i> Ordem crescente</button>
          <button type="button" class="table-filter-action-btn" data-sort="desc"><i class="bi bi-sort-alpha-up" aria-hidden="true"></i> Ordem decrescente</button>
          <button type="button" class="table-filter-action-btn" data-sort="clear"><i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i> Limpar ordenacao</button>
        </div>
        <input type="search" class="form-control form-control-sm table-filter-search" placeholder="Pesquisar">
        <div class="table-filter-list"></div>
        <div class="table-filter-footer">
          <button type="button" class="btn btn-outline-secondary btn-sm" data-cancel>Cancelar</button>
          <button type="button" class="btn btn-primary btn-sm" data-ok>OK</button>
        </div>
      `;
      document.body.appendChild(menu);
      activeMenu = menu;
      activeMenuCol = colIdx;

      const positionMenu = () => {
        const rect = btn.getBoundingClientRect();
        const margin = 8;
        const w = menu.offsetWidth || 280;
        const h = menu.offsetHeight || 320;
        let left = rect.left;
        if (left + w > window.innerWidth - margin) left = window.innerWidth - w - margin;
        if (left < margin) left = margin;
        let top = rect.bottom + 6;
        if (top + h > window.innerHeight - margin) {
          const above = rect.top - h - 6;
          top = above >= margin ? above : Math.max(margin, window.innerHeight - h - margin);
        }
        if (top < margin) top = margin;
        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
      };
      const onReposition = () => window.requestAnimationFrame(positionMenu);
      window.addEventListener("scroll", onReposition, true);
      window.addEventListener("resize", onReposition);
      cleanupMenuListeners = () => {
        window.removeEventListener("scroll", onReposition, true);
        window.removeEventListener("resize", onReposition);
      };
      window.requestAnimationFrame(positionMenu);

      let rangeFrom = "";
      let rangeTo = "";
      if (isDateColumn) {
        const summaryEl = menu.querySelector("[data-date-summary]");
        const titleEl = menu.querySelector("[data-cal-title]");
        const gridEl = menu.querySelector("[data-cal-grid]");
        const parsedRange = getDateRangeFromSelected(selectedTemp);
        rangeFrom = parsedRange.from;
        rangeTo = parsedRange.to;
        let viewMonth = new Date();
        viewMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), 1);

        const updateSummary = () => {
          if (!summaryEl) return;
          summaryEl.innerHTML = `
            <input
              type="text"
              class="table-filter-date-chip table-filter-date-input ${rangeFrom ? "is-filled" : ""}"
              data-date-input="from"
              inputmode="numeric"
              maxlength="10"
              placeholder="De: dd/mm/aaaa"
              value="${rangeFrom ? isoToPtBrDate(rangeFrom) : ""}"
            >
            <input
              type="text"
              class="table-filter-date-chip table-filter-date-input ${rangeTo ? "is-filled" : ""}"
              data-date-input="to"
              inputmode="numeric"
              maxlength="10"
              placeholder="Ate: dd/mm/aaaa"
              value="${rangeTo ? isoToPtBrDate(rangeTo) : ""}"
            >
          `;
          summaryEl.querySelectorAll("[data-date-input]").forEach((inputEl) => {
            const applyInputValue = () => {
              const role = inputEl.getAttribute("data-date-input");
              const masked = maskPtBrDateInput(inputEl.value);
              inputEl.value = masked;
              const iso = ptBrToIsoDate(masked);
              if (role === "from") {
                rangeFrom = iso || "";
                if (rangeTo && rangeFrom && rangeTo < rangeFrom) rangeTo = "";
              } else {
                rangeTo = iso || "";
                if (rangeFrom && rangeTo && rangeTo < rangeFrom) {
                  rangeFrom = rangeTo;
                  rangeTo = "";
                }
              }
              inputEl.classList.toggle("is-filled", Boolean(iso));
              renderCalendar();
            };
            inputEl.addEventListener("input", applyInputValue);
            inputEl.addEventListener("blur", applyInputValue);
            inputEl.addEventListener("keydown", (ev) => {
              if (ev.key === "Enter") {
                ev.preventDefault();
                applyInputValue();
              }
            });
          });
        };

        const renderCalendar = () => {
          if (!gridEl || !titleEl) return;
          const monthStart = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), 1);
          const monthEnd = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 0);
          titleEl.textContent = `${CALENDAR_MONTHS_PT[monthStart.getMonth()]} ${monthStart.getFullYear()}`;
          const leadingDays = monthStart.getDay();
          const cells = [];
          for (let i = 0; i < leadingDays; i += 1) {
            cells.push('<span class="table-filter-calendar-day is-empty"></span>');
          }
          const fromDate = isoToDate(rangeFrom);
          const toDate = isoToDate(rangeTo);
          for (let day = 1; day <= monthEnd.getDate(); day += 1) {
            const current = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), day);
            const iso = dateToIso(current);
            const isStart = sameDate(current, fromDate);
            const isEnd = sameDate(current, toDate);
            const isInRange =
              !isStart && !isEnd && fromDate && toDate && betweenDates(current, fromDate, toDate);
            cells.push(`
              <button type="button" class="table-filter-calendar-day ${isStart ? "is-start" : ""} ${isEnd ? "is-end" : ""} ${isInRange ? "is-in-range" : ""}" data-date-value="${iso}">
                <span>${day}</span>
              </button>
            `);
          }
          gridEl.innerHTML = cells.join("");
        };

        const applyDateClick = (iso) => {
          if (!rangeFrom || (rangeFrom && rangeTo)) {
            rangeFrom = iso;
            rangeTo = "";
          } else if (iso < rangeFrom) {
            rangeTo = rangeFrom;
            rangeFrom = iso;
          } else {
            rangeTo = iso;
          }
          updateSummary();
          renderCalendar();
        };

        updateSummary();
        renderCalendar();
        menu.querySelectorAll("[data-cal-nav]").forEach((navBtn) => {
          navBtn.addEventListener("click", () => {
            const delta = Number(navBtn.getAttribute("data-cal-nav") || "0");
            viewMonth = addMonths(viewMonth, delta);
            renderCalendar();
          });
        });
        gridEl?.addEventListener("click", (ev) => {
          const target = ev.target instanceof Element ? ev.target.closest("[data-date-value]") : null;
          if (!target) return;
          const iso = target.getAttribute("data-date-value") || "";
          if (!iso) return;
          applyDateClick(iso);
        });
        window.setTimeout(() => {
          menu.querySelector(".table-filter-calendar-nav")?.focus();
        }, 0);
        menu.querySelector("[data-clear]")?.addEventListener("click", () => {
          delete state.filters[colIdx];
          applyState({ syncServer: true });
          closeMenu();
        });
      } else {
        const listEl = menu.querySelector(".table-filter-list");
        const searchEl = menu.querySelector(".table-filter-search");
        const renderList = () => {
          const term = normalize(searchEl.value);
          const filtered = values.filter(([, label]) => normalize(label).includes(term));
          const allChecked = filtered.length > 0 && filtered.every(([k]) => selectedTemp.has(k));
          listEl.innerHTML = `
            <label class="table-filter-item">
              <input type="checkbox" data-select-all ${allChecked ? "checked" : ""}> <span>(Selecionar Tudo)</span>
            </label>
            ${filtered
              .map(
                ([k, label]) => `
              <label class="table-filter-item">
                <input type="checkbox" data-value="${k.replace(/"/g, "&quot;")}" ${selectedTemp.has(k) ? "checked" : ""}>
                <span>${label}</span>
              </label>`,
              )
              .join("")}
          `;
        };
        renderList();

        searchEl.addEventListener("input", renderList);
        listEl.addEventListener("change", (ev) => {
          const target = ev.target;
          if (!(target instanceof HTMLInputElement)) return;
          if (target.dataset.selectAll !== undefined) {
            const term = normalize(searchEl.value);
            values
              .filter(([, label]) => normalize(label).includes(term))
              .forEach(([k]) => {
                if (target.checked) selectedTemp.add(k);
                else selectedTemp.delete(k);
              });
            renderList();
            return;
          }
          const key = target.dataset.value || "";
          if (!key) return;
          if (target.checked) selectedTemp.add(key);
          else selectedTemp.delete(key);
          renderList();
        });
      }

      Array.from(menu.querySelectorAll("[data-sort]")).forEach((sortBtn) => {
        sortBtn.addEventListener("click", () => {
          const dir = sortBtn.getAttribute("data-sort");
          if (dir === "clear") state.sort = { col: null, dir: null };
          else state.sort = { col: colIdx, dir };
          applyState({ syncServer: true });
          closeMenu();
        });
      });

      menu.querySelector("[data-cancel]")?.addEventListener("click", () => closeMenu());
      menu.querySelector("[data-ok]")?.addEventListener("click", () => {
        if (isDateColumn) {
          let from = rangeFrom || "";
          let to = rangeTo || "";
          if (from && to && from > to) {
            [from, to] = [to, from];
          }
          const tokens = buildDateRangeTokens(from, to);
          if (!tokens.size) delete state.filters[colIdx];
          else state.filters[colIdx] = tokens;
        } else {
          const all = new Set(values.map(([k]) => k));
          const isAll = selectedTemp.size === all.size && [...all].every((k) => selectedTemp.has(k));
          if (isAll) delete state.filters[colIdx];
          else state.filters[colIdx] = new Set(selectedTemp);
        }
        applyState({ syncServer: true });
        closeMenu();
      });
      menu.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") {
          ev.preventDefault();
          closeMenu();
        }
      });
    };

    headers.forEach((th, idx) => {
      if (th.querySelector(".col-filter-trigger")) return;
      if (shouldSkipColumn(th, idx)) return;
      th.style.position = th.style.position || "relative";
      th.classList.add("has-col-filter-trigger");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "col-filter-trigger";
      btn.title = "Filtrar coluna";
      btn.setAttribute("aria-label", "Filtrar coluna");
      btn.innerHTML = '<i class="bi bi-search col-filter-icon" aria-hidden="true"></i>';
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        openMenu(idx, btn);
      });
      th.appendChild(btn);
    });

    document.addEventListener("pointerdown", (ev) => {
      if (!activeMenu) return;
      const target = ev.target;
      if (!(target instanceof Node)) return;
      if (activeMenu.contains(target)) return;
      if (target instanceof Element && target.closest(".col-filter-trigger")) return;
      closeMenu();
    });

    loadState();
    applyUrlDrivenDefaults();
    applyState();
    table.dataset.colFilterBound = "1";
  };

  document.addEventListener("DOMContentLoaded", () => {
    const bindAll = (root = document) => {
      root.querySelectorAll("table").forEach((table) => {
        const hasHead = table.querySelector("thead th");
        const hasBody = table.querySelector("tbody tr");
        if (!hasHead || !hasBody) return;
        initTableFilters(table);
      });
    };

    bindAll(document);

    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof Element)) return;
          if (node.matches("table")) {
            bindAll(node.parentElement || document);
            return;
          }
          bindAll(node);
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });
})();

