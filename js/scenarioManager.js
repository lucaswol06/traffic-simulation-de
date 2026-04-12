(function() {
  var scenarioActive = false;
  var scenarioData = null;
  var originalUpdateSim = null;
  var scenarioActionsApplied = {};
  var scenarioLog = null;
  var scenarioLastFrameTime = null;
  var scenarioFrameLimitReached = false;
  var scenarioLastStatsUiTime = null;
  var scenarioLastAutoExportTime = null;
  var scenarioAutoExportCounter = 0;
  var scenarioLogConfig = {
    enabled: true,
    sampleEverySec: 0.5,
    maxFrames: 20000,
    logRegularOnly: false,
    includeSpecialVehicles: true,
    autoExportEverySec: 0,
    schemaVersion: "1.0.0"
  };

  function createUI() {
    var container = document.getElementById("container");
    if (!container) return;

    var panel = document.createElement("div");
    panel.id = "scenarioPanel";
    panel.style.background = "#f2f2f2";
    panel.style.border = "1px solid #999";
    panel.style.padding = "6px";
    panel.style.marginBottom = "6px";
    panel.style.position = "absolute";
    panel.style.left = "110vmin";
    panel.style.top = "0vmin";
    panel.style.width = "55vmin";
    panel.style.zIndex = "5";
    panel.style.maxHeight = "38vmin";
    panel.style.overflow = "auto";
    panel.innerHTML =
      '<button id="scenarioToggle" style="display:block;width:100%;text-align:left;font-weight:bold;">[open] Scenario JSON Input</button>' +
      '<div id="scenarioBody" style="display:block;margin-top:6px;">' +
        '<textarea id="scenarioInput" style="width:100%;height:140px;box-sizing:border-box;" placeholder="{\n  &quot;seed&quot;: 42,\n  &quot;duration&quot;: 60,\n  &quot;timewarp&quot;: 6\n}"></textarea>' +
        '<div style="margin-top:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">' +
          '<button id="scenarioRunBtn">Run Scenario</button>' +
          '<button id="scenarioClearBtn">Clear</button>' +
          '<button id="scenarioExportBtn">Export Scenario Log JSON</button>' +
        '</div>' +
        '<div id="scenarioStatus" style="margin-top:6px;color:#555;"></div>' +
        '<pre id="scenarioStats" style="margin-top:6px;padding:8px;background:#f5f5f5;border:1px solid #ddd;white-space:pre-wrap;"></pre>' +
      '</div>';

    var sidebarRef = document.getElementById("scenarios") || document.getElementById("sliders") || document.getElementById("contents");
    if (sidebarRef && sidebarRef.parentNode === container) {
      container.insertBefore(panel, sidebarRef);
    } else {
      container.insertBefore(panel, container.firstChild);
    }

    // toggle expand/collapse
    document.getElementById("scenarioToggle").addEventListener("click", function() {
      var body = document.getElementById("scenarioBody");
      var arrow = body.style.display === "none" ? "[open]" : "[close]";
      body.style.display = body.style.display === "none" ? "block" : "none";
      this.innerHTML = arrow + " Scenario JSON Input";
    });

    document.getElementById("scenarioRunBtn").addEventListener("click", runScenario);


    document.getElementById("scenarioClearBtn").addEventListener("click", clearScenario);

    var exportBtn = document.getElementById("scenarioExportBtn");
    if (exportBtn) {
      exportBtn.addEventListener("click", function() {
        exportScenarioLogJson();
      });
    }

    var statsEl = document.getElementById("scenarioStats");
    if (statsEl) statsEl.textContent = "";

    var inputEl = document.getElementById("scenarioInput");
    if (inputEl && !inputEl.value.trim()) {
      inputEl.value = getDefaultScenarioJson();
    }
  }

  // handle errors
  function validateScenario(data) {
    var errors = [];
    if (typeof data !== "object" || data === null) {
      errors.push("Root must be a JSON object");
      return errors;
    }
    if (data.duration !== undefined && (typeof data.duration !== "number" || data.duration <= 0)) {
      errors.push("duration must be a positive number");
    }
    if (data.seed !== undefined && typeof data.seed !== "number") {
      errors.push("seed must be a number ");
    }
    if (data.timewarp !== undefined && (typeof data.timewarp !== "number" || data.timewarp <= 0)) {
      errors.push("timewarp must be a positive number");
    }
    if (data.parameters !== undefined && typeof data.parameters !== "object") {
      errors.push("parameters must be an object");
    }
    return errors;
  }

  function getDefaultScenarioJson() {
    return JSON.stringify({
      seed: 42,
      duration: 60,
      timewarp: 6,
      parameters: {
        qIn: 4500,         // inflow to the main road [veh/h]
        qOn: 1200,         // inflow to the onramp [veh/h]
        fracTruck: 0.1,    // fraction of trucks in the traffic stream
        IDM_v0: 30,        // desired speed in the car-following model [m/s]
        IDM_T: 1.4,        // desired time headway [s]
        IDM_a: 0.3,        // maximum acceleration [m/s^2]
        MOBIL_p: 0.1       // lane-changing politeness factor
      },
      vehicles: [
        {
          id: 301,     // custom vehicle id
          road: 0,     // road index where the vehicle starts
          type: "car", // vehicle type
          lane: 0,     // lane number
          u: 100,      // position along the road [m]
          speed: 25,   // initial speed [m/s]
          isAV: false  // whether the vehicle is an autonomous vehicle
        },
        {
          id: 302,
          road: 0,
          type: "car",
          lane: 1,
          u: 70,
          speed: 10,
          isAV: true
        }
      ],
      actions: [
        {
          time: 10,
          vehicleId: 301,
          set: {
            speed: 0
          }
        }
      ],
      logging: {
        enabled: true,
        sampleEverySec: 0.5,
        autoExportEverySec: 0,
        maxFrames: 5000,
        includeSpecialVehicles: true,
        logRegularOnly: false
      }
    }, null, 2);
  }

  function nowIsoString() {
    try {
      return new Date().toISOString();
    } catch (e) {
      return "";
    }
  }

  function toFiniteNumber(value, fallback) {
    var n = Number(value);
    return isFinite(n) ? n : fallback;
  }

  function mergeScenarioLogConfig(loggingInput) {
    var merged = {
      enabled: scenarioLogConfig.enabled,
      sampleEverySec: scenarioLogConfig.sampleEverySec,
      maxFrames: scenarioLogConfig.maxFrames,
      logRegularOnly: scenarioLogConfig.logRegularOnly,
      includeSpecialVehicles: scenarioLogConfig.includeSpecialVehicles,
      autoExportEverySec: scenarioLogConfig.autoExportEverySec,
      schemaVersion: scenarioLogConfig.schemaVersion
    };

    if (loggingInput && typeof loggingInput === "object") {
      if (loggingInput.enabled !== undefined) merged.enabled = !!loggingInput.enabled;
      if (loggingInput.sampleEverySec !== undefined) {
        merged.sampleEverySec = Math.max(0.01, toFiniteNumber(loggingInput.sampleEverySec, merged.sampleEverySec));
      }
      if (loggingInput.maxFrames !== undefined) {
        merged.maxFrames = Math.max(100, Math.floor(toFiniteNumber(loggingInput.maxFrames, merged.maxFrames)));
      }
      if (loggingInput.logRegularOnly !== undefined) merged.logRegularOnly = !!loggingInput.logRegularOnly;
      if (loggingInput.includeSpecialVehicles !== undefined) merged.includeSpecialVehicles = !!loggingInput.includeSpecialVehicles;
      if (loggingInput.autoExportEverySec !== undefined) {
        merged.autoExportEverySec = Math.max(0, toFiniteNumber(loggingInput.autoExportEverySec, merged.autoExportEverySec));
      }
      if (loggingInput.schemaVersion !== undefined && typeof loggingInput.schemaVersion === "string" && loggingInput.schemaVersion.trim() !== "") {
        merged.schemaVersion = loggingInput.schemaVersion.trim();
      }
    }

    scenarioLogConfig = merged;
    return merged;
  }

  function initializeScenarioLog(data) {
    var cfg = mergeScenarioLogConfig(data && data.logging ? data.logging : null);
    scenarioLog = {
      schemaVersion: cfg.schemaVersion,
      meta: {
        createdAt: nowIsoString(),
        scenarioName: (typeof window.scenarioString !== "undefined" && window.scenarioString) ? String(window.scenarioString) : "unknown",
        seed: (data && data.seed !== undefined) ? data.seed : null,
        duration: (data && data.duration !== undefined) ? data.duration : null,
        timewarp: (data && data.timewarp !== undefined) ? data.timewarp : null,
        runStartedAtSimTime: (typeof window.time !== "undefined") ? window.time : 0
      },
      config: {
        enabled: cfg.enabled,
        sampleEverySec: cfg.sampleEverySec,
        maxFrames: cfg.maxFrames,
        logRegularOnly: cfg.logRegularOnly,
        includeSpecialVehicles: cfg.includeSpecialVehicles,
        autoExportEverySec: cfg.autoExportEverySec
      },
      events: [],
      frames: [],
      stats: {}
    };
    scenarioLastFrameTime = null;
    scenarioFrameLimitReached = false;
    scenarioLastStatsUiTime = null;
    scenarioLastAutoExportTime = null;
    scenarioAutoExportCounter = 0;
    window.scenarioLogData = scenarioLog;
    return scenarioLog;
  }

  function addScenarioEvent(eventType, payload) {
    if (!scenarioLog) return;
    if (!scenarioLog.config || !scenarioLog.config.enabled) return;

    var simTime = 0;
    var simIndex = 0;

    if (typeof window.time !== "undefined") {
      simTime = window.time;
    }
    if (typeof window.itime !== "undefined") {
      simIndex = window.itime;
    }

    var eventObj = {
      type: eventType,
      t: simTime,
      itime: simIndex,
      ts: nowIsoString(),
      payload: payload || {}
    };

    scenarioLog.events.push(eventObj);
  }

  function cloneSimpleValue(value) {
    if (value === null || value === undefined) {
      return value;
    }

    var t = typeof value;
    if (t === "number" || t === "string" || t === "boolean") {
      return value;
    }

    if (Array.isArray(value)) {
      var arr = [];
      for (var i = 0; i < value.length; i++) {
        arr.push(cloneSimpleValue(value[i]));
      }
      return arr;
    }

    if (t === "object") {
      var out = {};
      for (var key in value) {
        if (value.hasOwnProperty(key)) {
          out[key] = cloneSimpleValue(value[key]);
        }
      }
      return out;
    }

    return String(value);
  }

  function getActionFieldValue(veh, prop) {
    if (!veh) return null;

    if (prop === "longModel") {
      if (!veh.longModel) return null;
      return {
        v0: veh.longModel.v0,
        T: veh.longModel.T,
        s0: veh.longModel.s0,
        a: veh.longModel.a,
        b: veh.longModel.b
      };
    }

    if (prop === "lane") {
      return veh.lane;
    }

    return cloneSimpleValue(veh[prop]);
  }

  function isVehicleRegular(v) {
    if (!v) return false;
    if (typeof v.isRegularVeh === "function") {
      return v.isRegularVeh();
    }
    return (v.id >= 200) && (v.type !== "obstacle");
  }

  function isVehicleSpecial(v) {
    if (!v) return false;
    if (typeof v.isSpecialVeh === "function") {
      return v.isSpecialVeh();
    }
    return (v.id >= 50) && (v.id < 200);
  }

  function shouldLogVehicle(v) {
    if (!scenarioLog || !scenarioLog.config) return false;
    if (scenarioLog.config.logRegularOnly) {
      return isVehicleRegular(v);
    }
    if (scenarioLog.config.includeSpecialVehicles) {
      return true;
    }
    return !isVehicleSpecial(v);
  }

  function canCaptureFrameNow() {
    if (!scenarioLog) return false;
    if (!scenarioLog.config || !scenarioLog.config.enabled) return false;
    if (!Array.isArray(scenarioLog.frames)) return false;
    if (scenarioLog.frames.length >= scenarioLog.config.maxFrames) return false;
    if (typeof window.time === "undefined") return false;

    if (scenarioLastFrameTime === null) {
      return true;
    }

    var delta = window.time - scenarioLastFrameTime;
    var step = scenarioLog.config.sampleEverySec;
    return delta >= (step - 1e-9);
  }

  function captureScenarioFrame() {
    if (!canCaptureFrameNow()) {
      if (scenarioLog && scenarioLog.config && Array.isArray(scenarioLog.frames)) {
        if (!scenarioFrameLimitReached && scenarioLog.frames.length >= scenarioLog.config.maxFrames) {
          scenarioFrameLimitReached = true;
          addScenarioEvent("frame_limit_reached", {
            maxFrames: scenarioLog.config.maxFrames
          });
        }
      }
      return;
    }

    if (typeof network === "undefined") return;

    var frameVehicles = [];
    for (var ir = 0; ir < network.length; ir++) {
      var rd = network[ir];
      if (!rd || !rd.veh) continue;

      for (var iv = 0; iv < rd.veh.length; iv++) {
        var veh = rd.veh[iv];
        if (!shouldLogVehicle(veh)) continue;

        var routeCopy = [];
        if (veh.route && veh.route.length) {
          for (var ri = 0; ri < veh.route.length; ri++) {
            routeCopy.push(veh.route[ri]);
          }
        }

        frameVehicles.push({
          id: veh.id,
          roadID: rd.roadID,
          type: veh.type,
          isAV: !!veh.isAV,
          u: veh.u,
          v: veh.v,
          lane: veh.lane,
          speed: veh.speed,
          acc: veh.acc,
          len: veh.len,
          width: veh.width,
          driverfactor: veh.driverfactor,
          route: routeCopy
        });
      }
    }

    var frame = {
      t: (typeof window.time !== "undefined") ? window.time : 0,
      itime: (typeof window.itime !== "undefined") ? window.itime : 0,
      dt: (typeof window.dt !== "undefined") ? window.dt : null,
      vehicleCount: frameVehicles.length,
      vehicles: frameVehicles
    };

    scenarioLog.frames.push(frame);
    scenarioLastFrameTime = frame.t;
  }

  function getScenarioLogData() {
    return scenarioLog;
  }

  function buildEmptyTypeStats() {
    return {
      sampleCount: 0,
      speedSum: 0,
      speedAvg: 0,
      speedMin: null,
      speedMax: null,
      uniqueVehicleCount: 0
    };
  }

  function computeScenarioStats() {
    if (!scenarioLog) return null;
    if (!scenarioLog.frames || !Array.isArray(scenarioLog.frames)) {
      scenarioLog.stats = {};
      return scenarioLog.stats;
    }

    var frames = scenarioLog.frames;
    var perVehicleMap = {};
    var byType = {};
    var firstTime = null;
    var lastTime = null;
    var vehicleCountMin = null;
    var vehicleCountMax = null;
    var vehicleCountSum = 0;
    var vehicleCountSamples = 0;

    for (var i = 0; i < frames.length; i++) {
      var frame = frames[i];
      if (!frame || !frame.vehicles) {
        continue;
      }

      var t = frame.t;
      if (typeof t === "number") {
        if (firstTime === null || t < firstTime) {
          firstTime = t;
        }
        if (lastTime === null || t > lastTime) {
          lastTime = t;
        }
      }

      var count = frame.vehicleCount;
      if (typeof count !== "number") {
        count = frame.vehicles.length;
      }
      if (vehicleCountMin === null || count < vehicleCountMin) {
        vehicleCountMin = count;
      }
      if (vehicleCountMax === null || count > vehicleCountMax) {
        vehicleCountMax = count;
      }
      vehicleCountSum += count;
      vehicleCountSamples += 1;

      for (var j = 0; j < frame.vehicles.length; j++) {
        var veh = frame.vehicles[j];
        if (!veh) continue;

        var vid = String(veh.id);
        if (!perVehicleMap[vid]) {
          perVehicleMap[vid] = {
            id: veh.id,
            type: veh.type,
            sampleCount: 0,
            speedSum: 0,
            speedMin: null,
            speedMax: null,
            speedAvg: 0,
            distanceTraveled: 0,
            laneChanges: 0,
            activeTime: 0,
            firstSeenTime: t,
            lastSeenTime: t,
            lastU: null,
            lastLane: null,
            lastT: null
          };
        }

        var s = perVehicleMap[vid];
        s.sampleCount += 1;

        if (typeof veh.speed === "number") {
          s.speedSum += veh.speed;
          if (s.speedMin === null || veh.speed < s.speedMin) {
            s.speedMin = veh.speed;
          }
          if (s.speedMax === null || veh.speed > s.speedMax) {
            s.speedMax = veh.speed;
          }
        }

        if (typeof t === "number") {
          if (s.firstSeenTime === null || t < s.firstSeenTime) {
            s.firstSeenTime = t;
          }
          if (s.lastSeenTime === null || t > s.lastSeenTime) {
            s.lastSeenTime = t;
          }
        }

        if (typeof veh.u === "number" && typeof s.lastU === "number") {
          var du = veh.u - s.lastU;
          if (du < 0) {
            du = Math.abs(du);
          }
          s.distanceTraveled += du;
        }

        if (s.lastLane !== null && veh.lane !== s.lastLane) {
          s.laneChanges += 1;
        }

        if (typeof t === "number" && s.lastT !== null) {
          var dtLocal = t - s.lastT;
          if (dtLocal > 0) {
            s.activeTime += dtLocal;
          }
        }

        s.lastU = (typeof veh.u === "number") ? veh.u : s.lastU;
        s.lastLane = (veh.lane !== undefined) ? veh.lane : s.lastLane;
        s.lastT = (typeof t === "number") ? t : s.lastT;

        var typeKey = (veh.type !== undefined && veh.type !== null) ? String(veh.type) : "unknown";
        if (!byType[typeKey]) {
          byType[typeKey] = buildEmptyTypeStats();
          byType[typeKey].vehicleIds = {};
        }
        var typeStats = byType[typeKey];
        typeStats.sampleCount += 1;
        if (typeof veh.speed === "number") {
          typeStats.speedSum += veh.speed;
          if (typeStats.speedMin === null || veh.speed < typeStats.speedMin) {
            typeStats.speedMin = veh.speed;
          }
          if (typeStats.speedMax === null || veh.speed > typeStats.speedMax) {
            typeStats.speedMax = veh.speed;
          }
        }
        typeStats.vehicleIds[vid] = true;
      }
    }

    var perVehicle = [];
    for (var vehicleId in perVehicleMap) {
      if (perVehicleMap.hasOwnProperty(vehicleId)) {
        var sv = perVehicleMap[vehicleId];
        if (sv.sampleCount > 0) {
          sv.speedAvg = sv.speedSum / sv.sampleCount;
        }
        delete sv.speedSum;
        delete sv.lastU;
        delete sv.lastLane;
        delete sv.lastT;
        perVehicle.push(sv);
      }
    }

    var byTypeOut = {};
    for (var typeName in byType) {
      if (byType.hasOwnProperty(typeName)) {
        var st = byType[typeName];
        if (st.sampleCount > 0) {
          st.speedAvg = st.speedSum / st.sampleCount;
        }
        var ids = st.vehicleIds;
        var uniqueCount = 0;
        for (var idKey in ids) {
          if (ids.hasOwnProperty(idKey)) {
            uniqueCount += 1;
          }
        }
        st.uniqueVehicleCount = uniqueCount;
        delete st.speedSum;
        delete st.vehicleIds;
        byTypeOut[typeName] = st;
      }
    }

    var runDuration = 0;
    if (firstTime !== null && lastTime !== null && lastTime >= firstTime) {
      runDuration = lastTime - firstTime;
    }

    scenarioLog.stats = {
      summary: {
        frameCount: frames.length,
        eventCount: scenarioLog.events ? scenarioLog.events.length : 0,
        uniqueVehicleCount: perVehicle.length,
        runDuration: runDuration,
        firstFrameTime: firstTime,
        lastFrameTime: lastTime,
        vehicleCountMin: vehicleCountMin,
        vehicleCountMax: vehicleCountMax,
        vehicleCountAvg: vehicleCountSamples > 0 ? (vehicleCountSum / vehicleCountSamples) : 0
      },
      byType: byTypeOut,
      perVehicle: perVehicle
    };

    return scenarioLog.stats;
  }

  function formatStatNumber(value) {
    if (value === null || value === undefined) return "-";
    if (typeof value !== "number") return String(value);
    return (Math.round(value * 100) / 100).toFixed(2);
  }

  function updateScenarioStatsDisplay(forceUpdate) {
    var statsEl = document.getElementById("scenarioStats");
    if (!statsEl) return;

    if (!scenarioLog) {
      statsEl.textContent = "";
      return;
    }

    var nowTime = (typeof window.time === "number") ? window.time : 0;
    if (!forceUpdate && scenarioLastStatsUiTime !== null) {
      if (nowTime - scenarioLastStatsUiTime < 0.5) {
        return;
      }
    }

    var stats = computeScenarioStats();
    if (!stats || !stats.summary) {
      return;
    }

    var summary = stats.summary;
    var lines = [];
    lines.push("Frames: " + summary.frameCount);
    lines.push("Vehicles tracked: " + summary.uniqueVehicleCount);
    lines.push("Run duration [s]: " + formatStatNumber(summary.runDuration));
    lines.push(
      "Vehicle count avg/min/max: "
      + formatStatNumber(summary.vehicleCountAvg)
      + " / " + formatStatNumber(summary.vehicleCountMin)
      + " / " + formatStatNumber(summary.vehicleCountMax)
    );

    var typeParts = [];
    if (stats.byType) {
      for (var typeName in stats.byType) {
        if (stats.byType.hasOwnProperty(typeName)) {
          var tStats = stats.byType[typeName];
          typeParts.push(typeName + "=" + formatStatNumber(tStats.speedAvg) + " m/s");
        }
      }
    }
    if (typeParts.length > 0) {
      lines.push("Avg speed by type: " + typeParts.join(", "));
    }

    statsEl.textContent = lines.join("\n");
    scenarioLastStatsUiTime = nowTime;
  }

  function makeScenarioLogFilename(suffix) {
    var scenarioName = "scenario";
    if (typeof window.scenarioString !== "undefined" && window.scenarioString) {
      scenarioName = String(window.scenarioString);
    }

    var safeName = scenarioName.replace(/[^a-zA-Z0-9_-]/g, "_");
    var seedPart = "na";
    if (scenarioLog && scenarioLog.meta && scenarioLog.meta.seed !== null && scenarioLog.meta.seed !== undefined) {
      seedPart = String(scenarioLog.meta.seed);
    }

    var timePart = "0";
    if (typeof window.time !== "undefined") {
      timePart = String(Math.round(window.time * 10) / 10).replace(/\./g, "_");
    }

    var name = "scenarioLog_" + safeName + "_seed" + seedPart + "_t" + timePart;
    if (suffix) {
      name += "_" + suffix;
    }
    return name + ".json";
  }

  function downloadJsonContent(content, filename) {
    if (typeof window.download === "function") {
      window.download(content, filename);
      return true;
    }

    var blob = new Blob([content], { type: "application/json" });
    if (window.navigator && window.navigator.msSaveBlob) {
      window.navigator.msSaveBlob(blob, filename);
      return true;
    }

    var url = window.URL.createObjectURL(blob);
    var a = document.createElement("a");
    document.body.appendChild(a);
    a.href = url;
    a.download = filename;
    setTimeout(function() {
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    }, 1);
    return true;
  }

  function exportScenarioLogJson(filenameOverride, skipExportEvent) {
    if (!scenarioLog) {
      setStatus("No scenario log to export.");
      return false;
    }

    if (!skipExportEvent) {
      addScenarioEvent("log_export_requested", {
        frameCount: scenarioLog.frames ? scenarioLog.frames.length : 0,
        eventCount: scenarioLog.events ? scenarioLog.events.length : 0
      });
    }

    computeScenarioStats();

    var filename = filenameOverride || makeScenarioLogFilename();
    var content = JSON.stringify(scenarioLog, null, 2);
    downloadJsonContent(content, filename);
    setStatus("Scenario log exported: " + filename);
    return true;
  }

  function maybeAutoExportScenarioLog() {
    if (!scenarioLog) return;
    if (!scenarioLog.config) return;

    var everySec = scenarioLog.config.autoExportEverySec;
    if (!(everySec > 0)) return;
    if (typeof window.time !== "number") return;

    if (scenarioLastAutoExportTime === null) {
      scenarioLastAutoExportTime = window.time;
      return;
    }

    if (window.time - scenarioLastAutoExportTime < everySec) {
      return;
    }

    scenarioLastAutoExportTime = window.time;
    scenarioAutoExportCounter += 1;
    var filename = makeScenarioLogFilename("auto" + scenarioAutoExportCounter);
    exportScenarioLogJson(filename, true);
  }

  function updateScenarioLogConfigRuntime(partialConfig) {
    var cfg = mergeScenarioLogConfig(partialConfig);
    if (scenarioLog) {
      scenarioLog.config.enabled = cfg.enabled;
      scenarioLog.config.sampleEverySec = cfg.sampleEverySec;
      scenarioLog.config.maxFrames = cfg.maxFrames;
      scenarioLog.config.logRegularOnly = cfg.logRegularOnly;
      scenarioLog.config.includeSpecialVehicles = cfg.includeSpecialVehicles;
      scenarioLog.config.autoExportEverySec = cfg.autoExportEverySec;
    }
    return cfg;
  }

  function setScenarioLoggingEnabled(isEnabled) {
    return updateScenarioLogConfigRuntime({ enabled: !!isEnabled });
  }

  // IDM_v0: desired speed (free-flow speed)
  // IDM_T: desired time headway (seconds gap to the car ahead)
  // IDM_s0: minimum distance to the car ahead
  // IDM_a: maximum acceleration
  // IDM_b: comfortable braking deceleration

  function applyParameters(params) {
    if (!params) return;
    var paramMap = {
      // IDM
      "IDM_v0": "IDM_v0", "IDM_T": "IDM_T", "IDM_s0": "IDM_s0",
      "IDM_a": "IDM_a", "IDM_b": "IDM_b",
      // AV
      "IDM_v0_AV": "IDM_v0_AV", "IDM_T_AV": "IDM_T_AV",
      "IDM_s0_AV": "IDM_s0_AV", "IDM_a_AV": "IDM_a_AV", "IDM_b_AV": "IDM_b_AV",
      // MOBIL
      "MOBIL_bSafe": "MOBIL_bSafe", "MOBIL_bSafeMax": "MOBIL_bSafeMax",
      "MOBIL_p": "MOBIL_p", "MOBIL_bThr": "MOBIL_bThr",
      "MOBIL_bBiasRight_car": "MOBIL_bBiasRight_car",
      "MOBIL_bBiasRight_truck": "MOBIL_bBiasRight_truck",
      // Traffic flow
      "qIn": "qIn", "qOn": "qOn", "q2": "q2", "q3": "q3",
      "fracTruck": "fracTruck", "fracAV": "fracAV", "fracScooter": "fracScooter",
      "density": "density", "speedInit": "speedInit",
      // Misc
      "driver_varcoeff": "driver_varcoeff",
      "speedL": "speedL", "speedL_truck": "speedL_truck",
      "factor_T_truck": "factor_T_truck", "factor_a_truck": "factor_a_truck",
      "QnoiseAccel": "QnoiseAccel"
    };
    for (var key in params) {
      if (params.hasOwnProperty(key)) {
        if (paramMap[key] && typeof window[paramMap[key]] !== "undefined") {
          window[paramMap[key]] = params[key];
        } else {
          // no harm in creating param anyways
          window[key] = params[key];
        }
      }
    }
    // Rebuild models after param changes
    updateModels(); // we use this to refresh the ui
  }

  function placeVehicles(vehicleDefs) {
    if (!vehicleDefs || !Array.isArray(vehicleDefs) || typeof network === "undefined") return;

    // remove all regular vehicles from all roads
    for (var ir = 0; ir < network.length; ir++) {
      network[ir].veh = network[ir].veh.filter(function(v) {
        return v.isSpecialVeh();
      });
    }

    // Suppress automatic vehicle generation by setting density=0 and qIn=0
    // restore qIn from scenario params if specified
    window.density = 0;

    // place each defined vehicle
    for (var i = 0; i < vehicleDefs.length; i++) {
      var vd = vehicleDefs[i];
      var roadIdx = vd.road;
      if (roadIdx < 0 || roadIdx >= network.length) {
        console.warn("scenarioManager: invalid road index " + roadIdx);
        continue;
      }
      var rd = network[roadIdx];

      var vehType = vd.type || "car";
      var len = vd.length || (vehType === "truck" ? 10 : (vehType === "others" ? 2 : 5));
      var wid = vd.width || (vehType === "truck" ? 3 : (vehType === "others" ? 1.5 : 2));
      var lane = vd.lane || 0;
      var u = vd.u || 0;
      var spd = vd.speed || 0;
      var dvc = vd.driver_varcoeff || 0;

      var veh = new vehicle(len, wid, u, lane, spd, vehType, dvc);

      // Override auto-assigned id if specified
      if (vd.id !== undefined) {
        veh.id = vd.id;
      }
      veh.isAV = !!vd.isAV;

      // Set route if specified
      if (vd.route) {
        veh.route = vd.route;
      }

      if (vd.longModel) {
        var lm = vd.longModel;
        veh.longModel = new IDM(
          lm.v0 !== undefined ? lm.v0 : 20,
          lm.T !== undefined ? lm.T : 1.3,
          lm.s0 !== undefined ? lm.s0 : 2,
          lm.a !== undefined ? lm.a : 1,
          lm.b !== undefined ? lm.b : 2
        );
      }

      // seed is set
      if (vd.driverfactor !== undefined) {
        veh.driverfactor = vd.driverfactor;
      }

      rd.veh.push(veh);
    }

    // Sort vehicles on each road
    for (var ir2 = 0; ir2 < network.length; ir2++) {
      network[ir2].updateEnvironment();
    }
  }

  function applyActions() { //this is the actual patch where we apply our values back. 
    if (!scenarioData || !scenarioData.actions || typeof network === "undefined") return;
    var actions = scenarioData.actions;
    for (var i = 0; i < actions.length; i++) {
      var a = actions[i];
      var key = i;
      if (scenarioActionsApplied[key]) continue;
      if (time >= a.time) {
        scenarioActionsApplied[key] = true;
        var targetVeh = findVehicleById(a.vehicleId);
        var setObj = a.set || {};
        if (targetVeh) {
          var beforeVals = {};
          var afterVals = {};

          for (var propRead in setObj) {
            if (setObj.hasOwnProperty(propRead)) {
              beforeVals[propRead] = getActionFieldValue(targetVeh, propRead);
            }
          }

          for (var prop in setObj) {
            if (setObj.hasOwnProperty(prop)) {
              if (prop === "speed") {
                targetVeh.speed = setObj[prop];
              } else if (prop === "acc") {
                targetVeh.acc = setObj[prop];
              } else if (prop === "lane") {
                targetVeh.lane = setObj[prop];
                targetVeh.laneOld = setObj[prop];
                targetVeh.v = setObj[prop];
              } else if (prop === "isAV") {
                targetVeh.isAV = setObj[prop];
              } else if (prop === "type") {
                targetVeh.type = setObj[prop];
              } else if (prop === "longModel") {
                var lm = setObj[prop];
                targetVeh.longModel = new IDM(
                  lm.v0 !== undefined ? lm.v0 : 20,
                  lm.T !== undefined ? lm.T : 1.3,
                  lm.s0 !== undefined ? lm.s0 : 2,
                  lm.a !== undefined ? lm.a : 1,
                  lm.b !== undefined ? lm.b : 2
                );
              } else {
                targetVeh[prop] = setObj[prop];
              }
            }
          }

          for (var propAfter in setObj) {
            if (setObj.hasOwnProperty(propAfter)) {
              afterVals[propAfter] = getActionFieldValue(targetVeh, propAfter);
            }
          }

          addScenarioEvent("action_applied", {
            actionIndex: i,
            scheduledTime: a.time,
            appliedTime: time,
            vehicleId: a.vehicleId,
            set: cloneSimpleValue(setObj),
            before: beforeVals,
            after: afterVals
          });
          console.log("scenarioManager: action at t=" + a.time + " applied to veh " + a.vehicleId, a.set);
        } else {
          addScenarioEvent("action_target_missing", {
            actionIndex: i,
            scheduledTime: a.time,
            appliedTime: time,
            vehicleId: a.vehicleId,
            set: cloneSimpleValue(setObj)
          });
          console.warn("scenarioManager: vehicle id=" + a.vehicleId + " not found for action at t=" + a.time);
        }
      }
    }
  }

  function findVehicleById(vid) {
    if (typeof network === "undefined") return null;
    for (var ir = 0; ir < network.length; ir++) {
      for (var iv = 0; iv < network[ir].veh.length; iv++) {
        if (network[ir].veh[iv].id === vid) return network[ir].veh[iv];
      }
    }
    return null;
  }

  // todo: did'nt use pause yet
  function checkDuration() {
    if (scenarioData && scenarioData.duration && time >= scenarioData.duration) {
      if (!isStopped) {
        clearInterval(myRun);
        isStopped = true;
        var btn = document.getElementById("startStop");
        if (btn) btn.src = "figs/buttonGo_small.png";
        setStatus("Scenario complete at t=" + scenarioData.duration + "s");
        addScenarioEvent("sim_paused_duration", {
          duration: scenarioData.duration,
          reason: "duration_reached"
        });
        console.log("scenarioManager: auto-paused at duration=" + scenarioData.duration);
      }
    }
  }

  // inject scenario hooks
  function wrapUpdateSim() {
    if (originalUpdateSim) return; // already wrapped
    if (typeof window.updateSim !== "function") {
      console.warn("scenarioManager: updateSim not found");
      return;
    }
    originalUpdateSim = window.updateSim;
    window.updateSim = function() {
      originalUpdateSim();
      if (scenarioActive) {
        captureScenarioFrame();
        applyActions();
        checkDuration();
        updateScenarioStatsDisplay(false);
        maybeAutoExportScenarioLog();
      }
    };
  }

  //attempts at removing existing vehicles
  var savedQIn, savedQOn, savedDensity;

  function suppressAutoGeneration() {
    savedQIn = window.qIn;
    savedQOn = typeof window.qOn !== "undefined" ? window.qOn : 0;
    savedDensity = window.density;
  }

  function restoreAutoGeneration() {
    window.qIn = savedQIn;
    if (typeof savedQOn !== "undefined") window.qOn = savedQOn;
    window.density = savedDensity;
  }

  //=== 9. RUN SCENARIO ===
  function runScenario() {
    var inputEl = document.getElementById("scenarioInput");
    var input = inputEl ? inputEl.value.trim() : "";
    if (!input) {
      input = getDefaultScenarioJson();
      if (inputEl) {
        inputEl.value = input;
      }
    }

    var data;
    try {
      data = JSON.parse(input);
    } catch (e) {
      setStatus("JSON parse error: " + e.message);
      return;
    }

    var errors = validateScenario(data);
    if (errors.length > 0) {
      setStatus("Validation errors: " + errors.join("; "));
      return;
    }

    scenarioData = data;
    scenarioActive = true;
    scenarioActionsApplied = {};
    initializeScenarioLog(data);
    addScenarioEvent("scenario_loaded", {
      hasParameters: !!data.parameters,
      vehicleCount: (data.vehicles && data.vehicles.length) ? data.vehicles.length : 0,
      actionCount: (data.actions && data.actions.length) ? data.actions.length : 0
    });

    // Wrap updateSim if not already done
    wrapUpdateSim();

    // Stop current sim
    clearInterval(myRun);
    isStopped = true;

    // Seed RNG for determinism
    var seed = data.seed !== undefined ? data.seed : 42;
    if (typeof Math.seedrandom === "function") {
      Math.seedrandom(seed);
    }
    addScenarioEvent("seed_set", {
      seed: seed,
      seeded: typeof Math.seedrandom === "function"
    });

    // Reset time
    window.time = 0;
    window.itime = 0;
    addScenarioEvent("time_reset", {
      time: 0,
      itime: 0
    });

    // Apply timewarp
    if (data.timewarp !== undefined) {
      window.timewarp = data.timewarp;
      window.dt = data.timewarp / fps;
      var sl = document.getElementById("slider_timewarp");
      var slv = document.getElementById("slider_timewarpVal");
      if (sl) sl.value = data.timewarp;
      if (slv) slv.innerHTML = data.timewarp + " times";
    }
    addScenarioEvent("timewarp_applied", {
      timewarp: window.timewarp,
      dt: window.dt
    });

    // Save defaults for clear
    suppressAutoGeneration();

    // Apply parameters (this also calls updateModels)
    if (data.parameters) {
      applyParameters(data.parameters);
      addScenarioEvent("params_applied", {
        parameterKeys: Object.keys(data.parameters),
        count: Object.keys(data.parameters).length
      });
    } else {
      addScenarioEvent("params_applied", {
        parameterKeys: [],
        count: 0
      });
    }

    // Handle vehicles: if defined, override all auto-generation
    if (data.vehicles && data.vehicles.length > 0) {
      // Set generation to 0 unless overridden by parameters
      if (!data.parameters || data.parameters.qIn === undefined) window.qIn = 0;
      if (!data.parameters || data.parameters.qOn === undefined) {
        if (typeof window.qOn !== "undefined") window.qOn = 0;
      }
      if (!data.parameters || data.parameters.q2 === undefined) {
        if (typeof window.q2 !== "undefined") window.q2 = 0;
      }
      if (!data.parameters || data.parameters.q3 === undefined) {
        if (typeof window.q3 !== "undefined") window.q3 = 0;
      }

      // Remove existing regular vehicles and place scenario ones
      for (var ir = 0; ir < network.length; ir++) {
        network[ir].veh = network[ir].veh.filter(function(v) {
          return v.isSpecialVeh();
        });
        network[ir].inVehBuffer = 0;
      }
      placeVehicles(data.vehicles);
      addScenarioEvent("vehicles_placed", {
        mode: "scenario_defined",
        count: data.vehicles.length
      });
    } else {
      // No explicit vehicles: use standard restart with scenario params
      for (var ir2 = 0; ir2 < network.length; ir2++) {
        var rd = network[ir2];
        rd.veh = rd.veh.filter(function(v) { return v.isSpecialVeh(); });
        rd.initRegularVehicles(density, fracTruck, fracScooter, speedInit);
        rd.inVehBuffer = rd.inVehBufferInit;
      }
      addScenarioEvent("vehicles_placed", {
        mode: "auto_generated",
        count: null
      });
    }

    // Reset detectors
    if (typeof detectors !== "undefined") {
      for (var iDet = 0; iDet < detectors.length; iDet++) {
        detectors[iDet].reset();
      }
    }

    // Re-seed after setup for deterministic runtime
    if (typeof Math.seedrandom === "function") {
      Math.seedrandom(seed);
    }
    addScenarioEvent("seed_set", {
      seed: seed,
      seeded: typeof Math.seedrandom === "function",
      phase: "post_setup"
    });

    // Start sim
    isStopped = false;
    var btn = document.getElementById("startStop");
    if (btn) btn.src = "figs/buttonStop3_small.png";
    myRun = setInterval(main_loop, 1000 / fps);
    addScenarioEvent("sim_started", {
      fps: fps,
      intervalMs: 1000 / fps
    });
    updateScenarioStatsDisplay(true);

    setStatus("Scenario running" + (data.duration ? " (duration: " + data.duration + "s)" : ""));
    console.log("scenarioManager: scenario loaded and running", data);
  }

  function clearScenario() {
    if (scenarioActive) {
      addScenarioEvent("scenario_cleared", {
        reason: "manual_clear"
      });
      scenarioActive = false;
      scenarioData = null;
      scenarioActionsApplied = {};
      restoreAutoGeneration();
      setStatus("Scenario cleared. Use Restart to reset simulation.");
      updateScenarioStatsDisplay(true);
    } else {
      setStatus("No active scenario.");
    }
    document.getElementById("scenarioInput").value = "";
  }

  function setStatus(msg) {
    var el = document.getElementById("scenarioStatus");
    if (el) el.textContent = msg;
  }

  window.scenarioLogControls = {
    getConfig: function() {
      return {
        enabled: scenarioLogConfig.enabled,
        sampleEverySec: scenarioLogConfig.sampleEverySec,
        maxFrames: scenarioLogConfig.maxFrames,
        logRegularOnly: scenarioLogConfig.logRegularOnly,
        includeSpecialVehicles: scenarioLogConfig.includeSpecialVehicles,
        autoExportEverySec: scenarioLogConfig.autoExportEverySec,
        schemaVersion: scenarioLogConfig.schemaVersion
      };
    },
    setConfig: function(partialConfig) {
      return updateScenarioLogConfigRuntime(partialConfig || {});
    },
    enable: function() {
      return setScenarioLoggingEnabled(true);
    },
    disable: function() {
      return setScenarioLoggingEnabled(false);
    },
    getLog: function() {
      return getScenarioLogData();
    },
    computeStats: function() {
      return computeScenarioStats();
    },
    getStats: function() {
      if (!scenarioLog) return null;
      if (!scenarioLog.stats) return null;
      return scenarioLog.stats;
    },
    exportLog: function(filename) {
      return exportScenarioLogJson(filename);
    },
    clearLog: function() {
      scenarioLog = null;
      window.scenarioLogData = null;
      return true;
    }
  };

  // as soon as page dom loads, we call our scenario manager
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createUI);
  } else {
    createUI();
  }

})();
