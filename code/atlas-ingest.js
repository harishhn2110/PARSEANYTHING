/**
 * ParseAnything Atlas Client-API Bridge.
 * Connects the atlas-ui.html frontend to FastAPI backend:
 * - Document Upload & Processing status polling
 * - Evidence Graph & Block synchronization
 * - Grounded Document Q&A with clickable citations
 * - Human-in-the-loop Review Queue (approve, reject, edit)
 * - Traceable exports (Markdown, JSON, CSV, XLSX)
 * - PII Masking toggle
 */
(function (global) {
  var API = global.ATLAS_API_BASE || (global.location && global.location.protocol === "file:" ? "http://127.0.0.1:8000" : "");

  function jsonOrThrow(res) {
    return res.text().then(function (text) {
      var body = null;
      if (text && text.trim().length > 0) {
        try {
          body = JSON.parse(text);
        } catch (e) {
          body = { message: text };
        }
      }
      if (!res.ok) {
        var code = body && body.error_code ? body.error_code : "HTTP_" + res.status;
        var msg = body && body.message ? body.message : (res.statusText || ("HTTP " + res.status));
        var err = new Error(code + ": " + msg);
        err.error_code = code;
        err.details = msg;
        throw err;
      }
      return body || {};
    });
  }

  function upload(file) {
    var form = new FormData();
    form.append("file", file, file.name);
    return fetch(API + "/v1/documents", { method: "POST", body: form }).then(jsonOrThrow);
  }

  function getJob(jobId) {
    return fetch(API + "/v1/jobs/" + encodeURIComponent(jobId)).then(jsonOrThrow);
  }

  function getDocument(docId) {
    return fetch(API + "/v1/documents/" + encodeURIComponent(docId)).then(jsonOrThrow);
  }

  function getBlocks(docId) {
    return fetch(API + "/v1/documents/" + encodeURIComponent(docId) + "/blocks").then(jsonOrThrow);
  }

  function getValidationEvents(docId) {
    return fetch(API + "/v1/documents/" + encodeURIComponent(docId) + "/validation-events").then(jsonOrThrow);
  }

  function pollJob(jobId, onUpdate) {
    return new Promise(function (resolve, reject) {
      var ticks = 0;
      function tick() {
        getJob(jobId)
          .then(function (job) {
            if (typeof onUpdate === "function") onUpdate(job);
            if (job.status === "completed" || job.status === "review") {
              resolve(job);
              return;
            }
            if (job.status === "failed") {
              var err = new Error((job.error_code || "PARTIAL_FAILURE") + ": " + (job.error_message || "Job failed"));
              err.error_code = job.error_code;
              err.details = job.error_message;
              err.job = job;
              reject(err);
              return;
            }
            ticks += 1;
            if (ticks > 300) {
              reject(new Error("TIMEOUT: Job did not finish in time."));
              return;
            }
            global.setTimeout(tick, 300);
          })
          .catch(reject);
      }
      tick();
    });
  }

  function ask(docId, question) {
    return fetch(API + "/v1/documents/" + encodeURIComponent(docId) + "/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question }),
    }).then(jsonOrThrow);
  }

  function reviewBlock(blockId, action, correctedText) {
    return fetch(API + "/v1/blocks/" + encodeURIComponent(blockId) + "/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: action, corrected_text: correctedText }),
    }).then(jsonOrThrow);
  }

  function exportDocument(docId, format, masked) {
    var actualId = (docId && docId !== "atlas-demo") ? docId : (global.__CURRENT_DOC_ID__ || docId || "atlas-demo");
    var fmt = (format || "markdown").toLowerCase();
    var ext = fmt === "excel" ? "xlsx" : fmt;
    var url = API + "/v1/documents/" + encodeURIComponent(actualId) + "/" + ext + "?masked=" + (masked ? "true" : "false");
    
    // Trigger direct browser download
    var link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.download = "";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  /**
   * Sync document and parsed blocks into the UI data arrays in-place.
   */
  function syncDocument(docId, callbacks) {
    if (!docId) return Promise.resolve(null);
    return Promise.all([
      getDocument(docId).catch(function () { return null; }),
      getBlocks(docId).catch(function () { return { items: [] }; }),
      getValidationEvents(docId).catch(function () { return []; }),
    ]).then(function (results) {
      try {
        var doc = results[0] || { id: docId, filename: "Document.pdf", pages: 1, overall_confidence: 0.95 };
        var blockData = results[1] || { items: [] };
        var valEvents = results[2] || [];
        global.__CURRENT_DOC_ID__ = docId;

        var rawBlocks = (blockData && Array.isArray(blockData.items)) ? blockData.items : [];
        if (!rawBlocks.length) return doc;

        // Transform blocks to match atlas-ui format
        var transformedBlocks = rawBlocks.map(function (b, idx) {
          var pageW = 612.0;
          var pageH = 792.0;
          var bboxStyle = null;

          if (b.bbox && Array.isArray(b.bbox) && b.bbox.length === 4) {
            var x0 = Number(b.bbox[0]) || 0;
            var y0 = Number(b.bbox[1]) || 0;
            var x1 = Number(b.bbox[2]) || 0;
            var y1 = Number(b.bbox[3]) || 0;
            var w = Math.max(10, x1 - x0);
            var h = Math.max(8, y1 - y0);

            bboxStyle = {
              top: (y0 / pageH * 100).toFixed(2) + "%",
              left: (x0 / pageW * 100).toFixed(2) + "%",
              width: (w / pageW * 100).toFixed(2) + "%",
              height: (h / pageH * 100).toFixed(2) + "%",
            };
          }

          var bType = (b.type || "paragraph");
          var bText = (b.text != null ? String(b.text) : "");
          var bConf = (typeof b.confidence === "number" ? b.confidence : 0.95);

          var color = "cyan";
          if (bConf < 0.60 || b.status === "abstain") {
            color = "amber";
          } else if (bType === "heading" || b.status === "verified") {
            color = "green";
          } else if (bType === "figure" || bType === "chart") {
            color = "violet";
          }

          var label = bType.replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });

          return {
            id: b.id || ("B" + (idx + 1)),
            type: bType,
            label: label,
            content: bText,
            page: b.page || 1,
            confidence: bConf,
            language: (b.language === "en" || !b.language) ? "English" : String(b.language).toUpperCase(),
            bbox: (b.bbox && Array.isArray(b.bbox) && b.bbox.length === 4) ? ("x " + Math.round(b.bbox[0]) + " · y " + Math.round(b.bbox[1]) + " · w " + Math.round(b.bbox[2] - b.bbox[0]) + " · h " + Math.round(b.bbox[3] - b.bbox[1])) : "x 50 · y 50 · w 200 · h 30",
            bbox_style: bboxStyle,
            status: b.status || "verified",
            order: (b.page || 1).toString().padStart(2, "0") + "." + ((idx + 1).toString().padStart(2, "0")),
            color: color,
          };
        });

        // Update in-place if exposed
        if (global.__ATLAS_DATA__) {
          var data = global.__ATLAS_DATA__;
          if (data.ul && Array.isArray(data.ul)) {
            data.ul.splice.apply(data.ul, [0, data.ul.length].concat(transformedBlocks));
          }

          if (data.understand && Array.isArray(data.understand)) {
            var understandRows = transformedBlocks.map(function (b) {
              var snippet = (b.content && b.content.length > 55) ? (b.content.slice(0, 52) + "...") : (b.content || "");
              return [b.id, b.type, snippet, b.order, Number(b.confidence).toFixed(2), (b.language || "EN").slice(0, 2).toUpperCase()];
            });
            data.understand.splice.apply(data.understand, [0, data.understand.length].concat(understandRows));
          }

          if (data.projects && Array.isArray(data.projects)) {
            var projIdx = data.projects.findIndex(function (p) { return p.id === doc.id; });
            var projPages = (doc && typeof doc.pages === "number" && doc.pages > 0) ? doc.pages : 1;
            var projSize = (doc && doc.size_bytes) ? ((doc.size_bytes / 1024 / 1024).toFixed(1) + " MB") : "1.2 MB";
            var projConf = (doc && typeof doc.overall_confidence === "number") ? (Math.round(doc.overall_confidence * 100) + "%") : "95%";
            var projItem = {
              id: doc.id,
              name: (doc.filename || "Document").replace(/\.[^/.]+$/, "").replace(/_/g, " "),
              document: doc.filename || "Document.pdf",
              pages: projPages,
              size: projSize,
              confidence: projConf,
            };
            if (projIdx >= 0) {
              data.projects[projIdx] = projItem;
            } else {
              data.projects.unshift(projItem);
            }
          }
        }

        if (callbacks) {
          if (typeof callbacks.setBlock === "function" && transformedBlocks.length > 0) {
            callbacks.setBlock(transformedBlocks[0].id);
          }
          if (typeof callbacks.setPage === "function" && transformedBlocks.length > 0) {
            callbacks.setPage(transformedBlocks[0].page);
          }
        }

        return doc;
      } catch (err) {
        console.warn("[Atlas] syncDocument warning:", err);
        return results[0] || null;
      }
    });
  }

  function checkHealth() {
    return fetch(API + "/health")
      .then(jsonOrThrow)
      .catch(function () { return null; });
  }

  function listSamples() {
    return fetch(API + "/v1/samples")
      .then(jsonOrThrow)
      .catch(function () { return []; });
  }

  function openSampleByName(filename, onUpload, onFallback) {
    var safeName = encodeURIComponent(filename);
    return fetch(API + "/v1/samples/" + safeName)
      .then(function (res) {
        if (!res.ok) throw new Error("Status: " + res.status);
        return res.blob();
      })
      .then(function (blob) {
        var file = new File([blob], filename, { type: "application/pdf" });
        if (typeof onUpload === "function") onUpload(file);
      })
      .catch(function (err) {
        console.warn("[Atlas] Sample fetch failed for " + filename + ":", err);
        if (typeof onFallback === "function") onFallback();
      });
  }

  function openSampleDocument(onUpload, onFallback) {
    return listSamples().then(function (samples) {
      if (samples && samples.length > 0) {
        // If there's more than one sample, allow picking or default to the first
        return openSampleByName(samples[0].filename, onUpload, onFallback);
      }
      // Fallback to default route
      return fetch(API + "/v1/sample-document")
        .then(function (res) {
          if (!res.ok) throw new Error("Status: " + res.status);
          return res.blob();
        })
        .then(function (blob) {
          var file = new File([blob], "Annual_Report.pdf", { type: "application/pdf" });
          if (typeof onUpload === "function") onUpload(file);
        });
    }).catch(function (err) {
      console.warn("[Atlas] Sample fetch failed, falling back to local demo:", err);
      if (typeof onFallback === "function") onFallback();
    });
  }

  global.AtlasIngest = {
    upload: upload,
    getJob: getJob,
    getDocument: getDocument,
    getBlocks: getBlocks,
    getValidationEvents: getValidationEvents,
    pollJob: pollJob,
    ask: ask,
    reviewBlock: reviewBlock,
    exportDocument: exportDocument,
    syncDocument: syncDocument,
    openSampleDocument: openSampleDocument,
    openSampleByName: openSampleByName,
    listSamples: listSamples,
    checkHealth: checkHealth,
  };
})(window);
