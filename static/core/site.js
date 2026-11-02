(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (!reduceMotion && "IntersectionObserver" in window) {
    const targets = document.querySelectorAll([
      ".page-hero", ".value-card", ".product-card", ".course-card", ".level-card",
      ".blog-card", ".faq-item", ".dashboard-card", ".cart-row", ".validation-banner", ".service-pack-card",
      ".academy-band", ".closing-cta", ".about-manifesto", ".contact-form-card",
      ".auth-form-card", ".wallet-overview article", ".referral-share",
    ].join(","));

    if (targets.length) {
      const siblingIndexes = new Map();
      targets.forEach((target) => {
        const parent = target.parentElement;
        const siblingIndex = siblingIndexes.get(parent) || 0;
        siblingIndexes.set(parent, siblingIndex + 1);
        target.style.setProperty("--reveal-delay", `${(siblingIndex % 4) * 75}ms`);
        target.setAttribute("data-reveal", "");
      });

      const observer = new IntersectionObserver((entries, currentObserver) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          currentObserver.unobserve(entry.target);
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -36px 0px" });

      document.documentElement.classList.add("has-reveal");
      targets.forEach((target) => observer.observe(target));
    }
  }

  const makeElement = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  function addContactLink(container, tag, value, prefix) {
    if (!value) return;
    const link = makeElement("a", "tree-contact");
    link.href = `${prefix}:${value}`;
    link.textContent = value;
    container.appendChild(link);
  }

  function makeBranch(member) {
    const branch = makeElement("li", "genealogy-branch");
    branch.dataset.treeNode = "";
    branch.dataset.memberId = member.id;
    branch.dataset.depth = member.depth;

    const card = makeElement("article", "genealogy-person");
    card.appendChild(makeElement("span", "tree-level-badge", `Niveau ${member.depth}`));
    card.appendChild(makeElement("strong", "", member.name));
    card.appendChild(makeElement("small", "", `Parrain : ${member.sponsor_name} · ${member.status}`));
    if (member.contacts_shared) {
      addContactLink(card, "a", member.email, "mailto");
      addContactLink(card, "a", member.phone, "tel");
    } else {
      card.appendChild(makeElement("small", "contacts-private", "Coordonnées non partagées"));
    }

    if (member.children_count > 0 && member.depth < 100) {
      const expand = makeElement("button", "mini-button tree-expand", `Voir ${member.children_count} filleul(s)`);
      expand.type = "button";
      expand.dataset.treeExpand = "";
      expand.dataset.memberId = member.id;
      expand.setAttribute("aria-expanded", "false");
      card.appendChild(expand);
    } else {
      card.appendChild(makeElement("small", "tree-leaf", member.depth >= 100 ? "Limite du 100ᵉ niveau atteinte" : "Aucun filleul direct"));
    }

    const children = makeElement("ul", "genealogy-children");
    children.dataset.treeChildren = "";
    children.setAttribute("role", "group");
    children.hidden = true;
    branch.append(card, children);
    return branch;
  }

  async function fetchChildren(tree, parentId, offset, group) {
    const url = new URL(tree.dataset.childrenUrl, window.location.href);
    url.pathname = url.pathname.replace(/\d+\/$/, `${parentId}/`);
    url.searchParams.set("offset", String(offset));
    const response = await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
    if (!response.ok) throw new Error("Les membres de cette branche ne sont pas accessibles.");
    const payload = await response.json();
    payload.members.forEach((member) => group.appendChild(makeBranch(member)));
    if (payload.has_more) {
      const moreItem = makeElement("li", "tree-more-item");
      const more = makeElement("button", "mini-button tree-more", "Afficher les filleuls suivants");
      more.type = "button";
      more.dataset.treeMore = "";
      more.dataset.memberId = parentId;
      more.dataset.offset = payload.next_offset;
      moreItem.appendChild(more);
      group.appendChild(moreItem);
    }
    if (payload.limit_reached) group.appendChild(makeElement("li", "tree-depth-limit", "Le réseau est affiché jusqu’au 100ᵉ niveau."));
    return payload;
  }

  document.querySelectorAll("[data-referral-tree]").forEach((tree) => {
    tree.addEventListener("click", async (event) => {
      const expand = event.target.closest("[data-tree-expand]");
      const more = event.target.closest("[data-tree-more]");
      if (!expand && !more) return;

      const button = expand || more;
      const parentId = button.dataset.memberId;
      const branch = button.closest("[data-tree-node]");
      const group = branch
        ? branch.querySelector(":scope > [data-tree-children]")
        : tree.querySelector(":scope > .genealogy-scroll > [data-tree-children]");
      if (!group) return;

      if (expand && button.getAttribute("aria-expanded") === "true") {
        group.hidden = true;
        button.setAttribute("aria-expanded", "false");
        button.textContent = button.dataset.originalLabel || `Voir les filleuls`;
        return;
      }

      if (more) {
        const item = more.closest("li");
        const offset = Number(more.dataset.offset || 0);
        more.disabled = true;
        more.textContent = "Chargement…";
        try {
          await fetchChildren(tree, parentId, offset, group);
          item.remove();
        } catch (error) {
          more.disabled = false;
          more.textContent = error.message;
        }
        return;
      }

      group.hidden = false;
      if (branch?.dataset.loaded === "true") {
        button.setAttribute("aria-expanded", "true");
        button.dataset.originalLabel ||= button.textContent;
        button.textContent = "Réduire cette branche";
        return;
      }

      button.dataset.originalLabel ||= button.textContent;
      button.disabled = true;
      button.textContent = "Chargement…";
      try {
        await fetchChildren(tree, parentId, 0, group);
        if (branch) branch.dataset.loaded = "true";
        button.setAttribute("aria-expanded", "true");
        button.textContent = "Réduire cette branche";
        if (!group.children.length) group.appendChild(makeElement("li", "tree-empty", "Aucun filleul dans cette branche."));
      } catch (error) {
        button.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
  });

  const packNavigation = document.querySelector(".service-pack-nav");
  if (packNavigation && "IntersectionObserver" in window) {
    const links = [...packNavigation.querySelectorAll('a[href^="#"]')];
    const sections = links.map((link) => document.querySelector(link.getAttribute("href"))).filter(Boolean);
    const visibleSections = new Set();
    const syncActiveLink = () => {
      const active = [...visibleSections].sort((a, b) =>
        Math.abs(a.getBoundingClientRect().top - 130) - Math.abs(b.getBoundingClientRect().top - 130)
      )[0];
      links.forEach((link) => {
        if (active && link.hash === `#${active.id}`) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      });
    };
    const navObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) visibleSections.add(entry.target);
        else visibleSections.delete(entry.target);
      });
      syncActiveLink();
    }, { rootMargin: "-12% 0px -62% 0px", threshold: 0 });
    sections.forEach((section) => navObserver.observe(section));
    links.forEach((link) => link.addEventListener("click", () => {
      links.forEach((item) => item.removeAttribute("aria-current"));
      link.setAttribute("aria-current", "location");
    }));
  }

  const pricingReset = document.querySelector("[data-pricing-reset]");
  if (pricingReset) {
    const resetAt = Number(pricingReset.dataset.pricingReset);
    const delay = resetAt - Date.now();
    if (Number.isFinite(resetAt) && delay > 0) {
      window.setTimeout(() => window.location.reload(), delay + 750);
    }
  }
})();
