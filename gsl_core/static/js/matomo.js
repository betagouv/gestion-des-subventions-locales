var _paq = (window._paq = window._paq || []);
/* tracker methods like "setCustomDimension" should be called before "trackPageView" */
_paq.push(["trackPageView"]);
_paq.push(["enableLinkTracking"]);
(function () {
  var u = "https://stats.beta.gouv.fr/";
  _paq.push(["setTrackerUrl", u + "matomo.php"]);
  _paq.push(["setSiteId", MATOMO_SITE_ID]);
  var d = document,
    g = d.createElement("script"),
    s = d.getElementsByTagName("script")[0];
  g.async = true;
  g.src = u + "matomo.js";
  s.parentNode.insertBefore(g, s);
})();

// Fire Matomo events triggered via HX-Trigger header from HTMX partial responses.
document.addEventListener("matomoEvents", function (event) {
  var _paq = (window._paq = window._paq || []);
  var events = event.detail.value;
  if (Array.isArray(events)) {
    events.forEach(function (e) {
      _paq.push(["trackEvent", e.category, e.action, e.name || ""]);
    });
  }
});
