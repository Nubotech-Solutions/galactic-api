const responses = {
  station: {
    endpoint: "GET /v1/station/status",
    clearance: "Deckhand",
    response: {
      location: "Outpost Gamma",
      oxygen_levels: "98%",
      external_weather: "Mild cosmic radiation, occasional micrometeorites.",
      current_alert_level: "Green"
    }
  },
  cargo: {
    endpoint: "GET /v1/cargo/manifest",
    clearance: "Deckhand",
    response: [
      { id: "C-098", item: "Freeze-Dried Space Tacos" },
      { id: "C-112", item: "Medical Supplies Batch-7" },
      { id: "C-421", item: "Sentient Toaster Prototype" },
      { id: "C-567", item: "Nanite Repair Swarm" }
    ]
  },
  convoy: {
    endpoint: "GET /v1/shipments/SH-002",
    clearance: "Logistics Officer",
    response: {
      shipment_id: "SH-002",
      convoy_name: "Convoy Hydra",
      status: "Delayed",
      destination: "Research Lab Kepler",
      eta: "Unknown - awaiting repair",
      delay_reason: "Engine malfunction on lead vessel. Engineering team dispatched."
    }
  },
  classified: {
    endpoint: "GET /v1/shipments/SH-004",
    clearance: "Sector Admiral required",
    response: {
      status: 403,
      detail: "Shipment 'SH-004' is Admiral-classified. Level 3 clearance required."
    }
  }
};

const output = document.querySelector("#console-output");
const tabs = Array.from(document.querySelectorAll(".tab"));

function renderResponse(key) {
  const payload = responses[key];

  output.textContent = JSON.stringify({
    endpoint: payload.endpoint,
    clearance: payload.clearance,
    response: payload.response
  }, null, 2);

  tabs.forEach((tab) => {
    const isActive = tab.dataset.panel === key;
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
  });
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => renderResponse(tab.dataset.panel));
});

renderResponse("station");
