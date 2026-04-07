(function() {
  var scenarioActive = false;
  var scenarioData = null;
  var originalUpdateSim = null;
  var scenarioActionsApplied = {};

  function createUI() {
    var container = document.getElementById("container");
    if (!container) return;

    var panel = document.createElement("div");

    // insert after buttons, before canvas
    var simDiv = document.getElementById("simCanvas") || document.getElementById("canvas_onramp") || container.querySelector("canvas");
    if (simDiv && simDiv.parentNode === container) {
      container.insertBefore(panel, simDiv);
    } 

    // toggle expand/collapse
    document.getElementById("scenarioToggle").addEventListener("click", function() {
      var body = document.getElementById("scenarioBody");
      var arrow = body.style.display === "none" ? "Open" : "CLose";
      body.style.display = body.style.display === "none" ? "block" : "none";
      this.innerHTML = arrow + " Scenario JSON Input";
    });

    document.getElementById("scenarioRunBtn").addEventListener("click", runScenario);


    document.getElementById("scenarioClearBtn").addEventListener("click", clearScenario);
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
    if (data.vehicles !== undefined) {
      errors.push("vehicles must be defined");
    }
    if (data.actions !== undefined) {
      errors.push("aactions must be an defined");
    }
    return errors;
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
        if (targetVeh) {
          var setObj = a.set;
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
          console.log("scenarioManager: action at t=" + a.time + " applied to veh " + a.vehicleId, a.set);
        } else {
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
        applyActions();
        checkDuration();
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
    var input = document.getElementById("scenarioInput").value.trim();
    if (!input) {
      setStatus("Error: empty input");
      return;
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

    // Reset time
    window.time = 0;
    window.itime = 0;

    // Apply timewarp
    if (data.timewarp !== undefined) {
      window.timewarp = data.timewarp;
      window.dt = data.timewarp / fps;
      var sl = document.getElementById("slider_timewarp");
      var slv = document.getElementById("slider_timewarpVal");
      if (sl) sl.value = data.timewarp;
      if (slv) slv.innerHTML = data.timewarp + " times";
    }

    // Save defaults for clear
    suppressAutoGeneration();

    // Apply parameters (this also calls updateModels)
    if (data.parameters) {
      applyParameters(data.parameters);
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
    } else {
      // No explicit vehicles: use standard restart with scenario params
      for (var ir2 = 0; ir2 < network.length; ir2++) {
        var rd = network[ir2];
        rd.veh = rd.veh.filter(function(v) { return v.isSpecialVeh(); });
        rd.initRegularVehicles(density, fracTruck, fracScooter, speedInit);
        rd.inVehBuffer = rd.inVehBufferInit;
      }
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

    // Start sim
    isStopped = false;
    var btn = document.getElementById("startStop");
    if (btn) btn.src = "figs/buttonStop3_small.png";
    myRun = setInterval(main_loop, 1000 / fps);

    setStatus("Scenario running" + (data.duration ? " (duration: " + data.duration + "s)" : ""));
    console.log("scenarioManager: scenario loaded and running", data);
  }

  function clearScenario() {
    if (scenarioActive) {
      scenarioActive = false;
      scenarioData = null;
      scenarioActionsApplied = {};
      restoreAutoGeneration();
      setStatus("Scenario cleared. Use Restart to reset simulation.");
    } else {
      setStatus("No active scenario.");
    }
    document.getElementById("scenarioInput").value = "";
  }

  function setStatus(msg) {
    var el = document.getElementById("scenarioStatus");
    if (el) el.textContent = msg;
  }

  // as soon as page dom loads, we call our scenario manager
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createUI);
  } else {
    createUI();
  }

})();
