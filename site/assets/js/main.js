/* EasyChat shared interactions: nav, scroll reveal, headline motion, chat demo, counters, tilt, pricing, form. */
(function () {
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var doc = document.documentElement;

  // Mobile nav
  var toggle = document.querySelector(".nav-toggle");
  var links = document.getElementById("nav-links");
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      links.classList.toggle("open", !open);
    });
  }
  var nav = document.querySelector(".nav");
  function onScroll() { if (nav) nav.classList.toggle("scrolled", window.scrollY > 8); }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Scroll reveal (only when supported; content is visible by default)
  if ("IntersectionObserver" in window && !reduceMotion) {
    doc.classList.add("js-motion");
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in-view"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    document.querySelectorAll(".reveal").forEach(function (el) { io.observe(el); });
  } else {
    document.querySelectorAll(".reveal").forEach(function (el) { el.classList.add("in-view"); });
  }

  // Headline word-by-word motion
  document.querySelectorAll(".reveal-words").forEach(function (h) {
    var i = 0;
    function wrap(node) {
      Array.prototype.slice.call(node.childNodes).forEach(function (child) {
        if (child.nodeType === 3) {
          var frag = document.createDocumentFragment();
          child.textContent.split(/(\s+)/).forEach(function (part) {
            if (!part) return;
            if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(part)); return; }
            var s = document.createElement("span");
            s.className = "w";
            s.style.animationDelay = (i++ * 0.07) + "s";
            s.textContent = part;
            frag.appendChild(s);
          });
          node.replaceChild(frag, child);
        } else if (child.nodeType === 1) { wrap(child); }
      });
    }
    wrap(h);
  });

  // Animated chat demo
  var body = document.getElementById("chat-body");
  if (body) {
    var script = [
      { who: "Maya", side: "them", text: "Morning! Did the new logo files land?" },
      { who: "You", side: "me", text: "Yes, just dropped them in #design." },
      { who: "Leo", side: "them", text: "Love the blue. Shipping to the client at 2pm 🚀" },
      { who: "You", side: "me", text: "Perfect. I'll set a reminder for everyone." },
      { who: "Maya", side: "them", text: "This is so much calmer than our old tool." }
    ];
    var idx = 0;
    function add(el) {
      body.appendChild(el);
      while (body.children.length > 5) body.removeChild(body.firstElementChild);
    }
    function bubble(m) {
      var d = document.createElement("div");
      d.className = "msg " + m.side;
      if (m.side === "them") { var w = document.createElement("span"); w.className = "who"; w.textContent = m.who; d.appendChild(w); }
      d.appendChild(document.createTextNode(m.text));
      return d;
    }
    function next() {
      var m = script[idx % script.length];
      idx++;
      if (m.side === "them" && !reduceMotion) {
        var t = document.createElement("div");
        t.className = "typing";
        t.setAttribute("aria-hidden", "true");
        t.innerHTML = "<i></i><i></i><i></i>";
        add(t);
        setTimeout(function () { t.remove(); add(bubble(m)); setTimeout(next, 1700); }, 1100);
      } else {
        add(bubble(m));
        setTimeout(next, 1700);
      }
    }
    // Start with two messages so the demo is never empty
    add(bubble(script[0])); add(bubble(script[1])); idx = 2;
    if (!reduceMotion) setTimeout(next, 1400);
  }

  // Counters
  function runCounter(el) {
    var end = parseFloat(el.getAttribute("data-count"));
    var dec = (el.getAttribute("data-count").split(".")[1] || "").length;
    var suffix = el.getAttribute("data-suffix") || "";
    if (reduceMotion) { el.textContent = end.toFixed(dec) + suffix; return; }
    var start = performance.now(), dur = 1600;
    (function step(now) {
      var p = Math.min(1, (now - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = (end * eased).toFixed(dec) + suffix;
      if (p < 1) requestAnimationFrame(step);
    })(start);
  }
  var counters = document.querySelectorAll("[data-count]");
  if ("IntersectionObserver" in window) {
    var cio = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { runCounter(e.target); cio.unobserve(e.target); } });
    }, { threshold: 0.5 });
    counters.forEach(function (c) { cio.observe(c); });
  } else { counters.forEach(runCounter); }

  // 3D tilt on cards (pointer devices only)
  if (!reduceMotion && window.matchMedia("(hover: hover)").matches) {
    document.querySelectorAll("[data-tilt]").forEach(function (card) {
      card.addEventListener("pointermove", function (e) {
        var r = card.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width - 0.5;
        var y = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = "perspective(800px) rotateY(" + (x * 8) + "deg) rotateX(" + (-y * 8) + "deg) translateY(-4px)";
      });
      card.addEventListener("pointerleave", function () { card.style.transform = ""; });
    });
  }

  // Pricing toggle with animated numbers
  var billingBtns = document.querySelectorAll(".billing button");
  billingBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var yearly = btn.getAttribute("data-billing") === "yearly";
      billingBtns.forEach(function (b) { b.setAttribute("aria-pressed", String(b === btn)); });
      document.querySelectorAll("[data-monthly]").forEach(function (el) {
        var from = parseFloat(el.textContent.replace(/[^0-9.]/g, "")) || 0;
        var to = parseFloat(el.getAttribute(yearly ? "data-yearly" : "data-monthly"));
        if (reduceMotion) { el.textContent = "$" + to; return; }
        var start = performance.now();
        (function step(now) {
          var p = Math.min(1, (now - start) / 450);
          el.textContent = "$" + Math.round(from + (to - from) * p);
          if (p < 1) requestAnimationFrame(step);
        })(start);
      });
      document.querySelectorAll("[data-period]").forEach(function (el) {
        el.textContent = yearly ? "/user/mo, billed yearly" : "/user/month";
      });
    });
  });

  // Contact form: validate, then open the visitor's email app via mailto
  var form = document.getElementById("contact-form");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var ok = true;
      ["name", "email", "message"].forEach(function (id) {
        var input = document.getElementById(id);
        var err = document.getElementById(id + "-err");
        var msg = "";
        if (!input.value.trim()) msg = "Please fill this in.";
        else if (id === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.value)) msg = "Enter a valid email like you@company.com.";
        err.textContent = msg;
        input.setAttribute("aria-invalid", msg ? "true" : "false");
        if (msg) ok = false;
      });
      if (!ok) return;
      var topic = document.getElementById("topic").value;
      var subject = encodeURIComponent("[" + topic + "] Message from " + document.getElementById("name").value);
      var bodyText = encodeURIComponent(document.getElementById("message").value + "\n\n— " + document.getElementById("name").value + " (" + document.getElementById("email").value + ")");
      document.getElementById("form-status").textContent = "Opening your email app. If nothing happens, write to hello@easychat.app.";
      window.location.href = "mailto:hello@easychat.app?subject=" + subject + "&body=" + bodyText;
    });
  }

  var year = document.getElementById("year");
  if (year) year.textContent = new Date().getFullYear();
})();
