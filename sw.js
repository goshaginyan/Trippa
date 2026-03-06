var CACHE_NAME = "trippa-v1";
var ASSETS = [
  "/Trippa/",
  "/Trippa/index.html",
  "/Trippa/manifest.json"
];

// Install — cache shell
self.addEventListener("install", function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener("activate", function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_NAME; })
            .map(function(k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

// Fetch — network first, fallback to cache
self.addEventListener("fetch", function(e) {
  e.respondWith(
    fetch(e.request).then(function(resp) {
      if (resp && resp.status === 200) {
        var clone = resp.clone();
        caches.open(CACHE_NAME).then(function(cache) {
          cache.put(e.request, clone);
        });
      }
      return resp;
    }).catch(function() {
      return caches.match(e.request);
    })
  );
});

// Push notification received
self.addEventListener("push", function(e) {
  var data = {};
  try { data = e.data.json(); } catch(err) {
    data = { title: "Trippa", body: e.data ? e.data.text() : "" };
  }
  var title = data.title || "Trippa";
  var options = {
    body: data.body || "",
    icon: "/Trippa/icons/icon-192.png",
    badge: "/Trippa/icons/icon-192.png",
    tag: data.tag || "trippa-reminder",
    data: { url: data.url || "/Trippa/" }
  };
  e.waitUntil(self.registration.showNotification(title, options));
});

// Click on notification — open app
self.addEventListener("notificationclick", function(e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || "/Trippa/";
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function(clients) {
      for (var i = 0; i < clients.length; i++) {
        if (clients[i].url.indexOf("/Trippa") !== -1 && "focus" in clients[i]) {
          return clients[i].focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});

// Periodic check — triggered by main page via postMessage
self.addEventListener("message", function(e) {
  if (e.data && e.data.type === "CHECK_REMINDERS") {
    var trips = e.data.trips || [];
    var lang = e.data.lang || "ru";
    var today = new Date();
    today.setHours(0, 0, 0, 0);

    trips.forEach(function(tr) {
      if (!tr.cities || !tr.cities.length) return;
      var fd = new Date(tr.cities[0].dateFrom + "T00:00:00");
      var diff = Math.ceil((fd - today) / 86400000);
      if (diff === (tr.notifDays || 1)) {
        var EMOJI = { vacation:"\uD83C\uDF34", business:"\uD83D\uDCBC", weekend:"\u26FA", trip:"\uD83D\uDE97", other:"\uD83D\uDCCC" };
        var dayWord;
        if (lang === "en") {
          dayWord = diff === 1 ? "day" : "days";
          var body = diff === 0 ? "Today" : "In " + diff + " " + dayWord;
        } else {
          var a = Math.abs(diff);
          if (a % 10 === 1 && a % 100 !== 11) dayWord = "день";
          else if ([2,3,4].indexOf(a % 10) >= 0 && [12,13,14].indexOf(a % 100) < 0) dayWord = "дня";
          else dayWord = "дней";
          var body = diff === 0 ? "Сегодня" : "Через " + diff + " " + dayWord;
        }
        var names = tr.cities.map(function(c) { return c.name; }).join(" \u2192 ");
        self.registration.showNotification(
          (EMOJI[tr.type] || "") + " " + tr.name,
          {
            body: body + " \u2014 " + names,
            icon: "/Trippa/icons/icon-192.png",
            badge: "/Trippa/icons/icon-192.png",
            tag: "trippa-" + tr.id
          }
        );
      }
    });
  }
});
