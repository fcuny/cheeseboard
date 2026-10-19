// Redo the home page's date-dependent parts for the visitor's today (Berkeley
// time) instead of the day the site was last built: which pizza is featured,
// which week "This week" shows, which row is highlighted, and whether the
// scraped schedule has run out. Mirrors build_site.py (featured_pizza,
// week_rows, today_status) and templates/index.html; without JS the page just
// stays as rendered for the build date.
//
// ?today=YYYY-MM-DD pretends it's another day, for checking.
(() => {
  const todaySection = document.getElementById("today");
  const dataScript = document.getElementById("schedule-data");
  if (!todaySection || !dataScript) return;

  const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // Dates are ISO strings throughout; Date objects only for arithmetic, in UTC.
  const parse = (iso) => new Date(iso + "T00:00:00Z");
  const iso = (date) => date.toISOString().slice(0, 10);
  const addDays = (isoDate, n) => {
    const date = parse(isoDate);
    date.setUTCDate(date.getUTCDate() + n);
    return iso(date);
  };
  const weekStart = (isoDate) => addDays(isoDate, -((parse(isoDate).getUTCDay() + 6) % 7));
  const weekday = (isoDate) => WEEKDAYS[parse(isoDate).getUTCDay()];
  const short = (isoDate) => `${MONTHS[parse(isoDate).getUTCMonth()]} ${parse(isoDate).getUTCDate()}`;
  const longDay = (isoDate) => `${weekday(isoDate)} ${short(isoDate)}, ${parse(isoDate).getUTCFullYear()}`;

  function berkeleyToday() {
    const override = new URLSearchParams(location.search).get("today");
    if (override && /^\d{4}-\d{2}-\d{2}$/.test(override)) return override;
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Los_Angeles",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      })
        .formatToParts(new Date())
        .map((p) => [p.type, p.value]),
    );
    return `${parts.year}-${parts.month}-${parts.day}`;
  }

  const builtFor = todaySection.dataset.today;
  const today = berkeleyToday();
  // The page only carries what a later visitor needs; an earlier "today"
  // (a wrong clock) keeps the build-time rendering.
  if (today <= builtFor) return;

  const days = JSON.parse(dataScript.textContent);
  const byDate = new Map(days.map((d) => [d.date, d]));
  const latest = days.length ? days[days.length - 1].date : null;

  function weekRows() {
    const start = weekStart(today);
    let end = addDays(start, 6);
    for (const d of days) if (d.date > end) end = d.date;
    const rows = [];
    for (let date = start; date <= end; date = addDays(date, 1)) {
      rows.push(byDate.get(date) || { date, weekday: weekday(date), missing: true });
    }
    return rows;
  }

  function dayLink(isoDate) {
    const a = document.createElement("a");
    a.href = `days/${isoDate}.html`;
    a.textContent = longDay(isoDate);
    return a;
  }

  // --- featured pizza ---------------------------------------------------
  const candidates = [...todaySection.querySelectorAll(".featured")];
  if (candidates.length) {
    // Rendered in date order: the first from today on, else the latest.
    const featured = candidates.find((c) => c.dataset.date >= today) || candidates[candidates.length - 1];
    for (const c of candidates) c.hidden = c !== featured;

    const eyebrow = todaySection.querySelector(".eyebrow");
    const date = featured.dataset.date;
    if (date === today) {
      eyebrow.textContent = `Today · ${longDay(date)}`;
    } else {
      const status = byDate.has(today) ? "No pizza today" : "Nothing posted for today yet";
      eyebrow.replaceChildren(`${status} · ${date > today ? "next up" : "latest was"} `, dayLink(date));
    }
  }

  // --- this week --------------------------------------------------------
  const tbody = document.querySelector("#week table.days tbody");
  if (tbody) {
    tbody.replaceChildren(
      ...weekRows().map((d) => {
        const tr = document.createElement("tr");
        if (d.closed) tr.classList.add("is-closed");
        if (d.missing) tr.classList.add("is-missing");
        if (d.date === today) tr.classList.add("is-today");
        const when = document.createElement("td");
        when.textContent = `${d.weekday} ${short(d.date)}`;
        const what = document.createElement("td");
        if (d.closed) {
          what.textContent = "Closed";
        } else if (d.missing) {
          what.textContent = "Not posted yet";
        } else {
          const a = document.createElement("a");
          a.href = `days/${d.date}.html`;
          a.textContent = d.ingredients.join(", ");
          what.append(a);
        }
        tr.append(when, what);
        return tr;
      }),
    );
  }

  const stale = document.querySelector("#week .stale");
  if (stale && latest) {
    stale.hidden = latest >= today;
    stale.querySelector(".latest").textContent = longDay(latest);
  }
})();
