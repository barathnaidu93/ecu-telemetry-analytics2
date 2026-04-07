"use client";
import { useState, useRef, useEffect } from "react";
import axios from "axios";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, ScatterChart, Scatter, ZAxis, ReferenceLine, ReferenceArea
} from "recharts";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [fuelType, setFuelType] = useState("gasoline");
  const [aspiration, setAspiration] = useState("NA");
  const [resultData, setResultData] = useState<any>(null);
  const [selectedCharts, setSelectedCharts] = useState<string[]>(["master"]);
  const [pinA, setPinA] = useState<number | null>(null);
  const [pinB, setPinB] = useState<number | null>(null);


  const [chatInput, setChatInput] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [messages, setMessages] = useState<any[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // --- NEW: Global Aggregator State ---
  const [activeTab, setActiveTab] = useState<"diagnostic" | "global">("diagnostic");
  const [globalHeatmapSignal, setGlobalHeatmapSignal] = useState<'afr' | 'ignition' | 'boost'>('afr');
  const [showHeatmapCount, setShowHeatmapCount] = useState(false);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  // ── Scenario Filter ── computed from chart_master._scenario embedded by backend
  const { filteredMaster, filteredFueling, filteredIgnition, filteredTrims } = (() => {
    const data = resultData;
    if (!data || !activeScenario) {
      return {
        filteredMaster:  data?.chart_master  ?? [],
        filteredFueling: data?.chart_fueling  ?? [],
        filteredIgnition:data?.chart_ignition ?? [],
        filteredTrims:   data?.chart_fuel_trims ?? [],
      };
    }
    // The master array has _scenario; use its indices to filter parallel arrays
    const masterFull: any[] = data.chart_master ?? [];
    const fuelFull:   any[] = data.chart_fueling ?? [];
    const ignFull:    any[] = data.chart_ignition ?? [];
    const trimFull:   any[] = data.chart_fuel_trims ?? [];

    const filteredMaster = masterFull.filter((p: any) => p._scenario === activeScenario);

    // Parallel arrays are the same length when the same step is used, so filter by index
    const masterIndices = new Set(masterFull.map((p: any, i: number) => p._scenario === activeScenario ? i : -1).filter(i => i >= 0));
    const filterByIndex = (arr: any[]) => arr.filter((_: any, i: number) => masterIndices.has(i));

    return {
      filteredMaster,
      filteredFueling:  fuelFull.length === masterFull.length ? filterByIndex(fuelFull) : fuelFull,
      filteredIgnition: ignFull.length  === masterFull.length ? filterByIndex(ignFull)  : ignFull,
      filteredTrims:    trimFull.length === masterFull.length ? filterByIndex(trimFull) : trimFull,
    };
  })();

  const handleChartClick = (state: any) => {
    if (state && state.activeLabel !== undefined) {
      const clickedTime = state.activeLabel;

      if (pinA === clickedTime) {
        setPinA(null);
      } else if (pinB === clickedTime) {
        setPinB(null);
      } else if (pinA === null) {
        setPinA(clickedTime);
      } else if (pinB === null) {
        setPinB(clickedTime);
      } else {
        // Both set, start fresh with pinA
        setPinA(clickedTime);
        setPinB(null);
      }

      if (state.activePayload && state.activePayload.length > 0) {
        const xValue = state.activeLabel;
        const details = state.activePayload
          .map((p: any) => `${p.name} = ${p.value}`)
          .join(", ");
        const prompt = `Analyze this specific engine anomaly at timestamp ${xValue}s: ${details}. Explain the thermodynamic physics behind this and explicitly state if this is dangerous for the engine.`;
        setChatInput(prompt);
        document.getElementById("ai-chat-input")?.focus();
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setFileName(f.name);
      setStatus("");
      setError("");
      setResultData(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setStatus("");
    setError("");
    setResultData(null);
    setSessionId(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("fuel_type", fuelType);
    formData.append("aspiration", aspiration);

    try {
      const res = await axios.post("http://localhost:8889/upload", formData);
      setStatus(`Successfully parsed: ${res.data.filename}`);
      setResultData(res.data);
      if (res.data.session_id) {
        setSessionId(res.data.session_id);
      }
      setMessages([{
        role: "assistant",
        content: `New file loaded: ${res.data.filename}. Chat context has been reset. Ask me anything about this log.`
      }]);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || "Upload failed. Try again.");
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  };


  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;
    const userMsg = chatInput.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setChatInput("");
    setChatLoading(true);

    try {
      const res = await axios.post("http://localhost:8889/chat", {
        message: userMsg,
        api_key: apiKey,
        session_id: sessionId,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: res.data.reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "[Error] Failed to connect to chat API." }]);
    } finally {
      setChatLoading(false);
    }
  };

  const tooltipStyle = {
    backgroundColor: "#0f172a",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: "8px",
    color: "#e2e8f0",
  };

  // Semantic color palette — each constant maps to its telemetry signal
  const COLOR_TPS  = "#f59e0b"; // Amber   — Throttle Position
  const COLOR_MAP  = "#34d399"; // Emerald — Manifold Pressure
  const COLOR_MAF  = "#8b5cf6"; // Violet  — Mass Airflow
  const COLOR_RPM  = "#00C6FF"; // Cyan    — Engine RPM (was COLOR_AFR, now correctly named)
  const COLOR_AFR  = "#fbbf24"; // Gold    — Air-Fuel Ratio (matches fueling chart line)
  const COLOR_IGN  = "#3b82f6"; // Blue    — Ignition Timing
  const COLOR_KNK  = "#f43f5e"; // Rose    — Knock Retard
  const COLOR_STFT = "#10b981"; // Emerald — Short Term Fuel Trim
  const COLOR_LTFT = "#a78bfa"; // Purple  — Long Term Fuel Trim (was violet duplicate of COLOR_MAF)

  const masterHasRPM      = resultData?.chart_master?.some((p: Record<string, unknown>) => p.RPM      !== undefined && p.RPM      !== null);
  const masterHasThrottle = resultData?.chart_master?.some((p: Record<string, unknown>) => p.Throttle !== undefined && p.Throttle !== null);
  const masterHasSpeed    = resultData?.chart_master?.some((p: Record<string, unknown>) => p.Speed    !== undefined && p.Speed    !== null);
  // Right axis is needed only when Throttle or Speed are present
  const masterNeedsRightAxis = masterHasThrottle || masterHasSpeed;

  // ── Ignition Plot Detection ──
  const ignHasTiming  = resultData?.chart_ignition?.some((p: Record<string, unknown>)   => p.Timing !== undefined);
  const ignHasKnock   = resultData?.chart_ignition?.some((p: Record<string, unknown>)   => p.Knock  !== undefined);
  const trimHasSTFT   = resultData?.chart_fuel_trims?.some((p: Record<string, unknown>) => p.STFT   !== undefined);
  const trimHasLTFT   = resultData?.chart_fuel_trims?.some((p: Record<string, unknown>) => p.LTFT   !== undefined);
  const fuelHasAFR    = resultData?.chart_fueling?.some((p: Record<string, unknown>)    => p.AFR    !== undefined);
  const fuelHasLambda = resultData?.chart_fueling?.some((p: Record<string, unknown>)    => p.Lambda !== undefined);

  // MAF chart — detect first non-name key to show
  const mafFirstKey = resultData?.chart_rpm?.length > 0
    ? Object.keys(resultData.chart_rpm[0]).find((k) => k !== "name")
    : undefined;

  // --- REUSABLE HEATMAP HELPERS ---
  const getCellColor = (afr: number) => {
    if (afr <= 12.0) return "#2563eb";
    if (afr < 12.5) return "#3b82f6";
    if (afr <= 13.0) return "#10b981";
    if (afr < 14.5) return "#f59e0b";
    return "#ef4444";
  };

  const getOpacity = (count: number) => {
    if (count >= 15) return 1.0;
    if (count >= 5) return 0.7;
    return 0.3;
  };

  const getIgnitionColor = (deg: number) => {
    if (deg < 10)  return "#1e3a8a";
    if (deg < 20)  return "#3b82f6";
    if (deg < 30)  return "#10b981";
    if (deg < 38)  return "#f59e0b";
    return "#ef4444";
  };

  const getBoostColor = (kpa: number) => {
    if (kpa < 100) return "#1e3a8a";
    if (kpa < 130) return "#3b82f6";
    if (kpa < 160) return "#10b981";
    if (kpa < 200) return "#f59e0b";
    return "#ef4444";
  };

  return (
    <div style={{
      minHeight: "100vh",
      backgroundColor: "#0B0F19",
      backgroundImage: "radial-gradient(circle at 50% 0%, #1a233a 0%, #0B0F19 100%)",
      color: "#e2e8f0",
      fontFamily: "'Inter', 'Segoe UI', sans-serif",
      padding: "40px 20px",
    }}>
      <div style={{ maxWidth: "1000px", margin: "0 auto" }}>

        {/* ── Header ── */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "40px" }}>
          <div>
            <h1 style={{
              fontSize: "2.2rem",
              fontWeight: "900",
              margin: 0,
              background: "linear-gradient(90deg, #00C6FF 0%, #0072FF 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              letterSpacing: "-0.03em"
            }}>
              ECU ANALYTICS
            </h1>
            <p style={{ color: "#94a3b8", fontSize: "0.95rem", marginTop: "4px" }}>

            </p>
          </div>

          <div style={{
            background: "rgba(30, 41, 59, 0.4)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "12px",
            padding: "5px",
            display: "flex",
            gap: "5px"
          }}>
            <button
              onClick={() => setActiveTab("diagnostic")}
              style={{
                padding: "8px 16px",
                borderRadius: "8px",
                border: "none",
                backgroundColor: activeTab === "diagnostic" ? "#0072ff" : "transparent",
                color: "white",
                cursor: "pointer",
                fontWeight: "600",
                fontSize: "0.85rem",
                transition: "all 0.2s"
              }}
            >
              Diagnostic
            </button>
            <button
              onClick={() => setActiveTab("global")}
              style={{
                padding: "8px 16px",
                borderRadius: "8px",
                border: "none",
                backgroundColor: activeTab === "global" ? "#0072ff" : "transparent",
                color: "white",
                cursor: "pointer",
                fontWeight: "600",
                fontSize: "0.85rem",
                transition: "all 0.2s"
              }}
            >
              Global Heatmap
            </button>
          </div>
        </div>

        {/* ── SHARED UPLOADER (Unified Data Source) ── */}
        <div style={{
          background: "rgba(30, 41, 59, 0.4)",
          backdropFilter: "blur(12px)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: "16px",
          padding: "30px",
          boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
          marginBottom: "30px"
        }}>
          <h2 style={{ marginTop: 0, fontSize: "1.5rem", color: "#f8fafc" }}>Telemetry Ingestion Pipeline</h2>

          <div style={{ display: "flex", gap: "10px", marginTop: "15px" }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", fontSize: "0.85rem", color: "#64748b", marginBottom: "5px", fontWeight: 600 }}>FUEL TYPE</label>
              <select
                value={fuelType}
                onChange={(e) => setFuelType(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px",
                  background: "rgba(15,23,42,0.8)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: "6px",
                  color: "#e2e8f0",
                  fontSize: "0.9rem",
                }}
              >
                <option value="gasoline">Gasoline (Pump)</option>
                <option value="e85">E85 (Ethanol)</option>
                <option value="racegas">Race Gas</option>
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", fontSize: "0.85rem", color: "#64748b", marginBottom: "5px", fontWeight: 600 }}>ASPIRATION</label>
              <select
                value={aspiration}
                onChange={(e) => setAspiration(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px",
                  background: "rgba(15,23,42,0.8)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: "6px",
                  color: "#e2e8f0",
                  fontSize: "0.9rem",
                }}
              >
                <option value="NA">Naturally Aspirated (NA)</option>
                <option value="Turbo">Turbocharged</option>
                <option value="Supercharged">Supercharged</option>
              </select>
            </div>
          </div>

          <div style={{ display: "flex", gap: "15px", alignItems: "center", marginTop: "20px" }}>
            <label style={{
              padding: "12px 24px",
              background: "rgba(255,255,255,0.05)",
              border: "1px dashed rgba(255,255,255,0.2)",
              borderRadius: "8px",
              cursor: "pointer",
              flex: "1",
            }}>
              <span style={{ color: "#94a3b8" }}>
                {fileName ? fileName : "Select .csv or .bin log file..."}
              </span>
              <input type="file" accept=".csv,.bin" onChange={handleFileChange} style={{ display: "none" }} />
            </label>

            <button
              onClick={handleUpload}
              disabled={!file || loading}
              style={{
                padding: "12px 32px",
                background: !file || loading
                  ? "rgba(255,255,255,0.1)"
                  : "linear-gradient(90deg, #00C6FF 0%, #0072FF 100%)",
                color: !file || loading ? "#64748b" : "white",
                border: "none",
                borderRadius: "8px",
                fontSize: "1rem",
                fontWeight: "600",
                cursor: !file || loading ? "not-allowed" : "pointer",
                boxShadow: !file || loading ? "none" : "0 8px 16px rgba(0,114,255,0.25)",
              }}
            >
              {loading ? "Processing..." : "Engage"}
            </button>
          </div>

          {status && (
            <p style={{ color: "#34d399", marginTop: "15px", fontWeight: "500" }}>✓ {status}</p>
          )}
          {error && (
            <p style={{ color: "#f87171", marginTop: "15px", fontWeight: "500" }}>⚠ {error}</p>
          )}
        </div>

        {activeTab === "diagnostic" ? (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "30px" }}>

            {/* ── Uploader ── */}

            {/* ── Data Preview ── */}
            {resultData && (
              <div style={{
                background: "rgba(15,23,42,0.6)",
                border: "1px solid rgba(255,255,255,0.05)",
                borderRadius: "16px",
                padding: "30px",
              }}>

                {/* CSV view */}
                {resultData && resultData.type === "csv" && (
                  <div>
                    <h3 style={{ color: "#e2e8f0", marginTop: 0, marginBottom: "20px" }}>
                      CSV Analysis Payload
                    </h3>

                    {/* Stat cards + Diagnostics */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "15px", marginBottom: "25px" }}>
                      <div style={{ background: "rgba(0,0,0,0.3)", padding: "15px", borderRadius: "8px" }}>
                        <p style={{ margin: 0, fontSize: "0.85rem", color: "#94a3b8" }}>DATA ROWS</p>
                        <strong style={{ fontSize: "1.2rem", color: "#00C6FF" }}>
                          {resultData.rows.toLocaleString()}
                        </strong>
                      </div>

                      <div style={{ background: "rgba(0,0,0,0.3)", padding: "15px", borderRadius: "8px" }}>
                        <p style={{ margin: 0, fontSize: "0.85rem", color: "#94a3b8" }}>EXTRACTED TARGETS</p>
                        <strong style={{ fontSize: "1rem", color: "#f8fafc", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "block" }}>
                          {Object.keys(resultData.extracted || {}).length > 0
                            ? Object.keys(resultData.extracted).join(", ")
                            : "None detected"}
                        </strong>
                      </div>

                      <div style={{
                        background: resultData.diagnostics?.status === "Critical" ? "rgba(239, 68, 68, 0.15)" :
                          resultData.diagnostics?.status === "Warning" ? "rgba(245, 158, 11, 0.15)" :
                            "rgba(16, 185, 129, 0.15)",
                        padding: "15px",
                        borderRadius: "8px",
                        border: "1px solid " + (
                          resultData.diagnostics?.status === "Critical" ? "rgba(239, 68, 68, 0.3)" :
                            resultData.diagnostics?.status === "Warning" ? "rgba(245, 158, 11, 0.3)" :
                              "rgba(16, 185, 129, 0.3)"
                        )
                      }}>
                        <p style={{ margin: 0, fontSize: "0.85rem", color: "#94a3b8" }}>SYSTEM HEALTH</p>
                        <strong style={{
                          fontSize: "1.2rem",
                          color: resultData.diagnostics?.status === "Critical" ? "#f87171" :
                            resultData.diagnostics?.status === "Warning" ? "#fbbf24" : "#34d399"
                        }}>
                          {resultData.diagnostics?.health_score}% {resultData.diagnostics?.status}
                        </strong>
                      </div>
                    </div>

                    {/* Diagnostic Alerts */}
                    {resultData.diagnostics?.alerts?.length > 0 && (
                      <div style={{
                        background: "rgba(255,255,255,0.03)",
                        padding: "15px",
                        borderRadius: "12px",
                        marginBottom: "25px",
                        borderLeft: "4px solid #f87171"
                      }}>
                        <p style={{ margin: "0 0 10px 0", fontSize: "0.9rem", color: "#f87171", fontWeight: "700" }}>⚠️ ACTIVE DIAGNOSTIC ALERTS</p>
                        <ul style={{ margin: 0, paddingLeft: "18px", color: "#cbd5e1", fontSize: "0.85rem" }}>
                          {resultData.diagnostics.alerts.map((alert: string, idx: number) => (
                            <li key={idx} style={{ marginBottom: "4px" }}>{alert}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                        {resultData.column_stats && Object.keys(resultData.column_stats).length > 0 && (
                          <div style={{ marginBottom: "25px" }}>
                            <p style={{ color: "#94a3b8", fontSize: "0.8rem", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                              Numeric column ranges (full dataset)
                            </p>
                            <div style={{ overflowX: "auto", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.05)" }}>
                              <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.85rem", textAlign: "left" }}>
                                <thead style={{ backgroundColor: "rgba(0,0,0,0.4)" }}>
                                  <tr>
                                    {["Column", "Min", "Max", "Avg", "Count"].map((h) => (
                                      <th key={h} style={{ padding: "10px 14px", color: "#94a3b8", fontWeight: "600", whiteSpace: "nowrap" }}>{h}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  {(Object.entries(resultData.column_stats) as [string, { min: number; max: number; avg: number; count: number }][]).map(([col, stats], i) => {
                                    const clow = col.toLowerCase();
                                    const isLean = (clow.includes("afr") || clow.includes("lambda")) && stats.max > 15.0;
                                    return (
                                      <tr key={col} style={{
                                        borderTop: "1px solid rgba(255,255,255,0.04)",
                                        backgroundColor: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)",
                                      }}>
                                        <td style={{ padding: "9px 14px", color: "#00C6FF", whiteSpace: "nowrap" }}>{col}</td>
                                        <td style={{ padding: "9px 14px", color: "#cbd5e1" }}>{stats.min}</td>
                                        <td style={{ padding: "9px 14px", color: isLean ? "#f87171" : "#cbd5e1" }}>
                                          {stats.max}
                                          {isLean && (
                                            <span style={{ marginLeft: "6px", fontSize: "0.75rem", color: "#f87171" }}>LEAN</span>
                                          )}
                                        </td>
                                        <td style={{ padding: "9px 14px", color: "#cbd5e1" }}>{stats.avg}</td>
                                        <td style={{ padding: "9px 14px", color: "#64748b" }}>{stats.count}</td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                    {/* ── Scenario Tagging Panel ── */}
                    {resultData.scenario_summary && Object.keys(resultData.scenario_summary).length > 0 && (
                      <div style={{ marginBottom: "25px" }}>
                        <p style={{ color: "#94a3b8", fontSize: "0.8rem", marginBottom: "12px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          🏷 Auto-Detected Driving Scenarios
                        </p>

                        {/* Summary stat cards for active scenario */}
                        {activeScenario && resultData.scenario_summary[activeScenario] && (() => {
                          const s = resultData.scenario_summary[activeScenario];
                          return (
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "10px", marginBottom: "14px" }}>
                              {s.avg_rpm != null && (
                                <div style={{ background: "rgba(0,198,255,0.08)", border: "1px solid rgba(0,198,255,0.2)", borderRadius: "8px", padding: "10px 14px" }}>
                                  <p style={{ margin: 0, fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase" }}>Avg RPM</p>
                                  <strong style={{ color: "#00C6FF", fontSize: "1.1rem" }}>{s.avg_rpm.toLocaleString()}</strong>
                                </div>
                              )}
                              {s.avg_afr != null && (
                                <div style={{ background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.2)", borderRadius: "8px", padding: "10px 14px" }}>
                                  <p style={{ margin: 0, fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase" }}>Avg AFR</p>
                                  <strong style={{ color: "#fbbf24", fontSize: "1.1rem" }}>{s.avg_afr}</strong>
                                </div>
                              )}
                              {s.avg_map != null && (
                                <div style={{ background: "rgba(52,211,153,0.08)", border: "1px solid rgba(52,211,153,0.2)", borderRadius: "8px", padding: "10px 14px" }}>
                                  <p style={{ margin: 0, fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase" }}>Avg MAP</p>
                                  <strong style={{ color: "#34d399", fontSize: "1.1rem" }}>{s.avg_map} kPa</strong>
                                </div>
                              )}
                              <div style={{ background: "rgba(139,92,246,0.08)", border: "1px solid rgba(139,92,246,0.2)", borderRadius: "8px", padding: "10px 14px" }}>
                                <p style={{ margin: 0, fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase" }}>Log Share</p>
                                <strong style={{ color: "#a78bfa", fontSize: "1.1rem" }}>{s.pct}%</strong>
                              </div>
                            </div>
                          );
                        })()}

                        {/* Scenario filter pills */}
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                          <button
                            onClick={() => setActiveScenario(null)}
                            style={{
                              padding: "6px 14px",
                              borderRadius: "999px",
                              border: `1px solid ${activeScenario === null ? "#00C6FF" : "rgba(255,255,255,0.12)"}`,
                              background: activeScenario === null ? "rgba(0,198,255,0.15)" : "rgba(255,255,255,0.04)",
                              color: activeScenario === null ? "#00C6FF" : "#94a3b8",
                              cursor: "pointer",
                              fontSize: "0.8rem",
                              fontWeight: activeScenario === null ? "700" : "400",
                              transition: "all 0.18s",
                            }}
                          >
                            All Data
                          </button>
                          {(Object.entries(resultData.scenario_summary) as [string, any][]).map(([tag, stats]) => {
                            const SCENARIO_COLORS: Record<string, string> = {
                              "WOT Pull":          "#ef4444",
                              "Hard Acceleration":  "#f97316",
                              "Highway Cruise":     "#3b82f6",
                              "City Driving":       "#10b981",
                              "Idle / Decel":       "#64748b",
                              "Cold Start":         "#a78bfa",
                            };
                            const color = SCENARIO_COLORS[tag] ?? "#94a3b8";
                            const isActive = activeScenario === tag;
                            return (
                              <button
                                key={tag}
                                onClick={() => setActiveScenario(isActive ? null : tag)}
                                style={{
                                  padding: "6px 14px",
                                  borderRadius: "999px",
                                  border: `1px solid ${isActive ? color : "rgba(255,255,255,0.12)"}`,
                                  background: isActive ? `${color}22` : "rgba(255,255,255,0.04)",
                                  color: isActive ? color : "#94a3b8",
                                  cursor: "pointer",
                                  fontSize: "0.8rem",
                                  fontWeight: isActive ? "700" : "400",
                                  transition: "all 0.18s",
                                  display: "flex",
                                  alignItems: "center",
                                  gap: "6px",
                                }}
                              >
                                {tag}
                                <span style={{ opacity: 0.65, fontSize: "0.72rem" }}>{stats.pct}%</span>
                              </button>
                            );
                          })}
                        </div>
                        {activeScenario && (
                          <p style={{ color: "#64748b", fontSize: "0.75rem", marginTop: "8px", marginBottom: 0 }}>
                            Showing <strong style={{ color: "#94a3b8" }}>{filteredMaster.length}</strong> of {resultData.chart_master?.length ?? 0} data points
                          </p>
                        )}
                      </div>
                    )}

                    {/* Chart Selection Icons */}
                    <div style={{
                      display: "flex",
                      gap: "15px",
                      marginBottom: "30px",
                      padding: "15px",
                      background: "rgba(255,255,255,0.03)",
                      borderRadius: "12px",
                      border: "1px solid rgba(255,255,255,0.05)",
                      justifyContent: "center"
                    }}>
                      {[
                        { id: 'master', label: '📈 Master Plot', data: resultData.chart_master },
                        { id: 'maf', label: '📊 MAF vs RPM', data: resultData.chart_rpm },
                        { id: 'throttle_map', label: '📉 Throttle vs MAP', data: resultData.chart_throttle_map },
                        { id: 'fueling', label: '⛽ Fueling Safety', data: resultData.chart_fueling },
                        { id: 'ignition', label: '🔥 Ignition/Knock', data: resultData.chart_ignition },
                        { id: 'trims', label: '📉 Fuel Trims', data: resultData.chart_fuel_trims },
                      ].map((chart) => (
                        <button
                          key={chart.id}
                          onClick={() => {
                            setSelectedCharts(prev =>
                              prev.includes(chart.id)
                                ? prev.filter(id => id !== chart.id)
                                : [...prev, chart.id]
                            );
                          }}
                          style={{
                            padding: "10px 20px",
                            background: selectedCharts.includes(chart.id) ? "rgba(0,198,255,0.2)" : "transparent",
                            border: `1px solid ${selectedCharts.includes(chart.id) ? "#00C6FF" : "rgba(255,255,255,0.1)"}`,
                            borderRadius: "8px",
                            color: selectedCharts.includes(chart.id) ? "#00C6FF" : "#94a3b8",
                            cursor: "pointer",
                            transition: "all 0.2s ease",
                            fontWeight: "500",
                            display: "flex",
                            alignItems: "center",
                            gap: "8px"
                          }}
                        >
                          {chart.label}
                        </button>
                      ))}
                      {selectedCharts.length > 0 && (
                        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginLeft: "auto" }}>
                          {(pinA !== null || pinB !== null) && (
                            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                              {pinA !== null && (
                                <div
                                  onClick={() => setPinA(null)}
                                  style={{
                                    padding: "8px 12px",
                                    background: "rgba(244,63,94,0.1)",
                                    border: "1px solid #f43f5e",
                                    borderRadius: "6px",
                                    color: "#f43f5e",
                                    fontSize: "0.8rem",
                                    fontWeight: "700",
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "6px"
                                  }}
                                >
                                  A: {pinA}s ✕
                                </div>
                              )}
                              {pinB !== null && (
                                <div
                                  onClick={() => setPinB(null)}
                                  style={{
                                    padding: "8px 12px",
                                    background: "rgba(244,63,94,0.1)",
                                    border: "1px solid #f43f5e",
                                    borderRadius: "6px",
                                    color: "#f43f5e",
                                    fontSize: "0.8rem",
                                    fontWeight: "700",
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "6px"
                                  }}
                                >
                                  B: {pinB}s ✕
                                </div>
                              )}
                              {pinA !== null && pinB !== null && (
                                <div style={{
                                  padding: "8px 12px",
                                  background: "rgba(52, 211, 153, 0.1)",
                                  border: "1px solid #34d399",
                                  borderRadius: "6px",
                                  color: "#34d399",
                                  fontSize: "0.8rem",
                                  fontWeight: "800"
                                }}>
                                  Δt: {Math.abs(pinB - pinA).toFixed(2)}s
                                </div>
                              )}
                            </div>
                          )}
                          <button
                            onClick={() => {
                              setSelectedCharts(["master"]);
                              setPinA(null);
                              setPinB(null);
                            }}
                            style={{
                              padding: "10px 15px",
                              background: "rgba(244,63,94,0.1)",
                              border: "1px solid rgba(244,63,94,0.3)",
                              borderRadius: "8px",
                              color: "#f43f5e",
                              cursor: "pointer",
                              fontSize: "0.85rem",
                              fontWeight: "600",
                            }}
                          >
                            Reset Analysis
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Render Selected Charts in a Stack */}
                    <div style={{ display: "flex", flexDirection: "column", gap: "30px", marginTop: "20px" }}>

                      {/* 1.) Master Plot Visualization */}
                      {resultData && selectedCharts.includes('master') && resultData.chart_master && resultData.chart_master.length > 0 && (
                        <div style={{ padding: "25px", background: "rgba(0,0,0,0.2)", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.03)" }}>
                          <h3 style={{ color: "#00C6FF", marginTop: 0, marginBottom: "8px", fontSize: "1.2rem", fontWeight: "600" }}>
                            📊 Master Plot - Vehicle Telemetry
                          </h3>
                          <p style={{ color: "#64748b", fontSize: "0.8rem", marginTop: 0, marginBottom: "20px" }}>
                            Signals detected:{" "}
                            {[masterHasRPM && "RPM", masterHasThrottle && "Throttle", masterHasSpeed && "Speed"]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                          <div style={{ height: "400px", width: "100%", position: "relative" }}>
                            {(pinA !== null || pinB !== null) && resultData.chart_master && (
                              <div style={{
                                position: "absolute",
                                top: "10px",
                                right: "70px",
                                zIndex: 10,
                                background: "rgba(15, 23, 42, 0.95)",
                                padding: "12px 18px",
                                borderRadius: "10px",
                                border: "1px solid #f43f5e",
                                fontSize: "0.8rem",
                                boxShadow: "0 8px 16px rgba(0,0,0,0.6)",
                                pointerEvents: "none",
                                minWidth: "180px"
                              }}>
                                <div style={{ color: "#f43f5e", fontWeight: "bold", marginBottom: "8px", borderBottom: "1px solid rgba(244,63,94,0.3)", paddingBottom: "5px", display: "flex", justifyContent: "space-between" }}>
                                  <span>DELTA ANALYSIS</span>
                                  {pinA !== null && pinB !== null && <span style={{ color: "#34d399" }}>Δ {(pinB - pinA).toFixed(2)}s</span>}
                                </div>
                                {(() => {
                                  const pA = pinA !== null ? resultData.chart_master.find((d: any) => d.name === pinA) : null;
                                  const pB = pinB !== null ? resultData.chart_master.find((d: any) => d.name === pinB) : null;

                                  const renderMetric = (label: string, key: string, color: string, suffix: string = "") => {
                                    const valA = pA?.[key];
                                    const valB = pB?.[key];
                                    const hasBoth = valA !== undefined && valB !== undefined && valA !== null && valB !== null;
                                    const delta = hasBoth ? (valB - valA) : null;

                                    return (
                                      <div style={{ marginBottom: "6px" }}>
                                        <div style={{ color: "#94a3b8", display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
                                          <span>{label}:</span>
                                          <span style={{ fontWeight: "600", color }}>
                                            {pinA !== null && <span>{valA ?? "N/A"}{suffix}</span>}
                                            {pinB !== null && <span> → {valB ?? "N/A"}{suffix}</span>}
                                          </span>
                                        </div>
                                        {delta !== null && (
                                          <div style={{ textAlign: "right", fontSize: "0.75rem", color: delta > 0 ? "#34d399" : delta < 0 ? "#f43f5e" : "#94a3b8", fontWeight: "700" }}>
                                            {delta > 0 ? "+" : ""}{delta.toFixed(1)}{suffix} Δ
                                          </div>
                                        )}
                                      </div>
                                    );
                                  };

                                  return (
                                    <div>
                                      {masterHasRPM && renderMetric("RPM", "RPM", COLOR_RPM)}
                                      {masterHasThrottle && renderMetric("Throttle", "Throttle", COLOR_TPS, "%")}
                                      {masterHasSpeed && renderMetric("Speed", "Speed", COLOR_MAF, "km/h")}
                                    </div>
                                  );
                                })()}
                              </div>
                            )}
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={filteredMaster} syncId="efi-analysis" onClick={handleChartClick} margin={{ top: 5, right: masterNeedsRightAxis ? 30 : 10, bottom: 20, left: 10 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                                <XAxis
                                  dataKey="name"
                                  type="number"
                                  stroke="#64748b"
                                  fontSize={11}
                                  tickLine={false}
                                  axisLine={false}
                                  label={{ value: 'Time (seconds)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }}
                                />
                                {pinA !== null && (
                                  <ReferenceLine x={pinA} stroke="#f43f5e" strokeWidth={2} label={{ value: 'A', position: 'top', fill: '#f43f5e', fontSize: 10, fontWeight: 'bold' }} />
                                )}
                                {pinB !== null && (
                                  <ReferenceLine x={pinB} stroke="#f43f5e" strokeWidth={2} label={{ value: 'B', position: 'top', fill: '#f43f5e', fontSize: 10, fontWeight: 'bold' }} />
                                )}
                                {pinA !== null && pinB !== null && (
                                  <ReferenceArea x1={pinA} x2={pinB} fill="rgba(244,63,94,0.1)" />
                                )}
                                {masterHasRPM && (
                                  <YAxis
                                    yAxisId="left"
                                    stroke="#00C6FF"
                                    fontSize={11}
                                    tickLine={false}
                                    axisLine={false}
                                    width={60}
                                    domain={['auto', 'auto']}
                                    label={{ value: 'Engine RPM', angle: -90, position: 'insideLeft', fill: '#00C6FF', fontSize: 10 }}
                                  />
                                )}
                                {masterNeedsRightAxis && (
                                  <YAxis
                                    yAxisId="right"
                                    orientation="right"
                                    stroke="#94a3b8"
                                    fontSize={11}
                                    tickLine={false}
                                    axisLine={false}
                                    width={40}
                                    label={{
                                      value: [masterHasThrottle && 'Throttle (%)', masterHasSpeed && 'Speed (km/h)'].filter(Boolean).join(' / '),
                                      angle: 90,
                                      position: 'insideRight',
                                      fill: '#94a3b8',
                                      fontSize: 10,
                                    }}
                                  />
                                )}

                                {/* Fallback: if ONLY right-axis signals exist (no RPM), use a single left axis */}
                                {!masterHasRPM && !masterNeedsRightAxis && (
                                  <YAxis yAxisId="left" stroke="#94a3b8" fontSize={11} tickLine={false} axisLine={false} domain={['auto', 'auto']} />
                                )}

                                <Tooltip contentStyle={tooltipStyle} />
                                <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "20px" }} />

                                {/* RPM Line */}
                                {masterHasRPM && (
                                  <Line
                                    yAxisId="left"
                                    name="Engine RPM"
                                    type="monotone"
                                    dataKey="RPM"
                                    stroke="#00C6FF"
                                    strokeWidth={2}
                                    dot={false}
                                    activeDot={{ r: 5 }}
                                  />
                                )}

                                {/* Throttle Line — uses right axis if RPM present, otherwise left */}
                                {masterHasThrottle && (
                                  <Line
                                    yAxisId={masterHasRPM ? "right" : "left"}
                                    name="Throttle Position (%)"
                                    type="monotone"
                                    dataKey="Throttle"
                                    stroke="#f59e0b"
                                    strokeWidth={2}
                                    strokeDasharray="5 5"
                                    dot={false}
                                  />
                                )}

                                {/* Speed Line — uses right axis if RPM present, otherwise left */}
                                {masterHasSpeed && (
                                  <Line
                                    yAxisId={masterHasRPM ? "right" : "left"}
                                    name="Vehicle Speed (km/h)"
                                    type="monotone"
                                    dataKey="Speed"
                                    stroke="#34d399"
                                    strokeWidth={2}
                                    strokeDasharray="2 2"
                                    dot={false}
                                  />
                                )}
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      )}

                      {/* 2.) MAF vs RPM (RPM Binned) */}
                      {resultData && selectedCharts.includes('maf') && resultData.chart_rpm && resultData.chart_rpm.length > 0 && (
                        <div style={{ padding: "25px", background: "rgba(0,0,0,0.2)", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.03)" }}>
                          <h3 style={{ color: "#00C6FF", marginTop: 0, marginBottom: "25px", fontSize: "1.2rem", fontWeight: "600" }}>
                            📊 MAF (Airflow) vs Engine RPM
                          </h3>
                          <div style={{ height: "400px", width: "100%" }}>
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={resultData.chart_rpm} margin={{ top: 5, right: 30, bottom: 20, left: 10 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                                <XAxis dataKey="name" type="number" domain={['auto', 'auto']} stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} label={{ value: 'Engine RPM', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }} />
                                <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} domain={['auto', 'auto']} width={60} label={{ value: 'Mass Airflow (MAF)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} />
                                <Tooltip contentStyle={tooltipStyle} />
                                <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "20px" }} />
                                <Line
                                  name={mafFirstKey ? String(mafFirstKey) : "Mass Airflow (MAF)"}
                                  type="monotone"
                                  dataKey={mafFirstKey || "MAF"}
                                  stroke="#34d399"
                                  strokeWidth={2}
                                  dot={false}
                                  activeDot={{ r: 5 }}
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      )}

                      {/* 3.) Throttle vs MAP Correlation */}
                      {resultData && selectedCharts.includes('throttle_map') && resultData.chart_throttle_map && resultData.chart_throttle_map.length > 0 && (
                        <div style={{ padding: "25px", background: "rgba(0,0,0,0.2)", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.03)" }}>
                          <h3 style={{ color: "#00C6FF", marginTop: 0, marginBottom: "25px", fontSize: "1.2rem", fontWeight: "600" }}>
                            📊 Manifold Pressure (MAP) vs Throttle Position
                          </h3>
                          <div style={{ height: "400px", width: "100%" }}>
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={resultData.chart_throttle_map} margin={{ top: 5, right: 30, bottom: 20, left: 10 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                                <XAxis dataKey="Throttle" type="number" domain={[0, 100]} stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} label={{ value: 'Throttle Position (%)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }} />
                                <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} domain={['auto', 'auto']} width={60} label={{ value: 'Manifold Pressure (MAP)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} />
                                <Tooltip contentStyle={tooltipStyle} />
                                <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "20px" }} />
                                <Line name="MAP Trend" type="monotone" dataKey="MAP" stroke="#f59e0b" strokeWidth={3} dot={false} activeDot={{ r: 5 }} />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      )}

                      {/* 4.) Fueling Safety (AFR & Lambda) */}
                      {resultData && selectedCharts.includes('fueling') && (
                        <div style={{ padding: "25px", background: "rgba(0,0,0,0.2)", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.03)" }}>
                          <h3 style={{ color: "#00C6FF", marginTop: 0, marginBottom: "25px", fontSize: "1.2rem", fontWeight: "600" }}>
                            ⛽ Fueling Safety - AFR & Lambda vs Time
                          </h3>
                          {resultData.chart_fueling && resultData.chart_fueling.length > 0 ? (
                          <div style={{ height: "400px", width: "100%", position: "relative" }}>
                            {(pinA !== null || pinB !== null) && resultData.chart_fueling && (
                              <div style={{
                                position: "absolute",
                                top: "10px",
                                right: "70px",
                                zIndex: 10,
                                background: "rgba(15, 23, 42, 0.95)",
                                padding: "12px 18px",
                                borderRadius: "10px",
                                border: "1px solid #f43f5e",
                                fontSize: "0.8rem",
                                boxShadow: "0 8px 16px rgba(0,0,0,0.6)",
                                pointerEvents: "none",
                                minWidth: "160px"
                              }}>
                                {(() => {
                                  const pA = pinA !== null ? resultData.chart_fueling.find((d: any) => d.Time === pinA) : null;
                                  const pB = pinB !== null ? resultData.chart_fueling.find((d: any) => d.Time === pinB) : null;

                                  const renderMetric = (label: string, key: string, color: string, suffix: string = "") => {
                                    const valA = pA?.[key];
                                    const valB = pB?.[key];
                                    const hasBoth = valA !== undefined && valB !== undefined && valA !== null && valB !== null;
                                    const delta = hasBoth ? (valB - valA) : null;

                                    return (
                                      <div style={{ marginBottom: "6px" }}>
                                        <div style={{ color: "#94a3b8", display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
                                          <span>{label}:</span>
                                          <span style={{ fontWeight: "600", color }}>
                                            {pinA !== null && <span>{valA ?? "N/A"}{suffix}</span>}
                                            {pinB !== null && <span> → {valB ?? "N/A"}{suffix}</span>}
                                          </span>
                                        </div>
                                        {delta !== null && (
                                          <div style={{ textAlign: "right", fontSize: "0.75rem", color: delta > 0 ? "#f43f5e" : delta < 0 ? "#34d399" : "#94a3b8", fontWeight: "700" }}>
                                            {/* In AFR, lower is usually richer (better for power), so green for negative delta if it's within range, but simple +/- is safer */}
                                            {delta > 0 ? "+" : ""}{delta.toFixed(2)}{suffix} Δ
                                          </div>
                                        )}
                                      </div>
                                    );
                                  };

                                  return (
                                    <div>
                                      {renderMetric("AFR", "AFR", COLOR_AFR)}
                                      {pA?.Lambda !== undefined && renderMetric("Lambda", "Lambda", "#fbbf24")}
                                    </div>
                                  );
                                })()}
                              </div>
                            )}
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={filteredFueling} syncId="efi-analysis" onClick={handleChartClick} margin={{ top: 5, right: 30, bottom: 20, left: 10 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                                <XAxis
                                  dataKey="Time"
                                  type="number"
                                  stroke="#64748b"
                                  fontSize={11}
                                  tickLine={false}
                                  axisLine={false}
                                  label={{ value: 'Time (seconds)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }}
                                />
                                {pinA !== null && (
                                  <ReferenceLine x={pinA} stroke="#f43f5e" strokeWidth={2} />
                                )}
                                {pinB !== null && (
                                  <ReferenceLine x={pinB} stroke="#f43f5e" strokeWidth={2} />
                                )}
                                {pinA !== null && pinB !== null && (
                                  <ReferenceArea x1={pinA} x2={pinB} fill="rgba(244,63,94,0.1)" />
                                )}
                                <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} domain={['auto', 'auto']} width={60} label={{ value: 'AFR / Lambda', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} />
                                <Tooltip contentStyle={tooltipStyle} />
                                <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "20px" }} />
                                {fuelHasAFR && (
                                  <Line
                                    name="AFR (Air-Fuel Ratio)"
                                    type="monotone"
                                    dataKey="AFR"
                                    stroke={COLOR_AFR}
                                    strokeWidth={2}
                                    dot={false}
                                    activeDot={{ r: 5 }}
                                  />
                                )}
                                {fuelHasLambda && (
                                  <Line
                                    name="Lambda"
                                    type="monotone"
                                    dataKey="Lambda"
                                    stroke="#34d399"
                                    strokeWidth={2}
                                    strokeDasharray="5 5"
                                    dot={false}
                                  />
                                )}
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                          ) : (
                            <div style={{ textAlign: "center", padding: "100px 20px", color: "#64748b" }}>
                              <p style={{ fontSize: "1.1rem", marginBottom: "8px" }}>No AFR or Lambda sensors detected in this log.</p>
                              <p style={{ fontSize: "0.9rem" }}>Requires AFR, Lambda, or WBO2 columns in the data.</p>
                            </div>
                          )}
                        </div>
                      )}

                      {/* 5.) Ignition Timing & Knock Retard */}
                      {selectedCharts.includes('ignition') && (
                        <div style={{ padding: "25px", background: "rgba(0,0,0,0.2)", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.03)" }}>
                          <h3 style={{ color: COLOR_IGN, marginTop: 0, marginBottom: "25px", fontSize: "1.2rem", fontWeight: "600" }}>
                            🔥 Power Limit Analysis - Ignition & Knock
                          </h3>
                          {resultData.chart_ignition && resultData.chart_ignition.length > 0 ? (
                            <div style={{ height: "400px", width: "100%", position: "relative" }}>
                              {(pinA !== null || pinB !== null) && resultData.chart_ignition && (
                                <div style={{
                                  position: "absolute",
                                  top: "10px",
                                  right: "70px",
                                  zIndex: 10,
                                  background: "rgba(15, 23, 42, 0.95)",
                                  padding: "12px 18px",
                                  borderRadius: "10px",
                                  border: "1px solid #f43f5e",
                                  fontSize: "0.8rem",
                                  boxShadow: "0 8px 16px rgba(0,0,0,0.6)",
                                  pointerEvents: "none",
                                  minWidth: "160px"
                                }}>
                                  {(() => {
                                    const pA = pinA !== null ? resultData.chart_ignition.find((d: any) => d.Time === pinA) : null;
                                    const pB = pinB !== null ? resultData.chart_ignition.find((d: any) => d.Time === pinB) : null;

                                    const renderMetric = (label: string, key: string, color: string, suffix: string = "") => {
                                      const valA = pA?.[key];
                                      const valB = pB?.[key];
                                      const hasBoth = valA !== undefined && valB !== undefined && valA !== null && valB !== null;
                                      const delta = hasBoth ? (valB - valA) : null;

                                      return (
                                        <div style={{ marginBottom: "6px" }}>
                                          <div style={{ color: "#94a3b8", display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
                                            <span>{label}:</span>
                                            <span style={{ fontWeight: "600", color }}>
                                              {pinA !== null && <span>{valA ?? "N/A"}{suffix}</span>}
                                              {pinB !== null && <span> → {valB ?? "N/A"}{suffix}</span>}
                                            </span>
                                          </div>
                                          {delta !== null && (
                                            <div style={{ textAlign: "right", fontSize: "0.75rem", color: delta > 0 ? "#34d399" : delta < 0 ? "#f43f5e" : "#94a3b8", fontWeight: "700" }}>
                                              {delta > 0 ? "+" : ""}{delta.toFixed(1)}{suffix} Δ
                                            </div>
                                          )}
                                        </div>
                                      );
                                    };

                                    return (
                                      <div>
                                        {renderMetric("Timing", "Timing", COLOR_IGN, "°")}
                                        {renderMetric("Knock", "Knock", COLOR_KNK, "°")}
                                      </div>
                                    );
                                  })()}
                                </div>
                              )}
                              <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={filteredIgnition} syncId="efi-analysis" onClick={handleChartClick} margin={{ top: 5, right: 30, bottom: 20, left: 10 }}>
                                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                                  <XAxis
                                    dataKey="Time"
                                    type="number"
                                    stroke="#64748b"
                                    fontSize={11}
                                    tickLine={false}
                                    axisLine={false}
                                    label={{ value: 'Time (seconds)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }}
                                  />
                                  {pinA !== null && (
                                    <ReferenceLine x={pinA} stroke="#f43f5e" strokeWidth={2} />
                                  )}
                                  {pinB !== null && (
                                    <ReferenceLine x={pinB} stroke="#f43f5e" strokeWidth={2} />
                                  )}
                                  {pinA !== null && pinB !== null && (
                                    <ReferenceArea x1={pinA} x2={pinB} fill="rgba(244,63,94,0.1)" />
                                  )}
                                  <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} domain={['auto', 'auto']} width={60} label={{ value: 'Degrees (°)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }} />
                                  <Tooltip contentStyle={tooltipStyle} />
                                  <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "20px" }} />
                                  <Line name="Ignition Timing" type="monotone" dataKey="Timing" stroke={COLOR_IGN} strokeWidth={2} dot={false} activeDot={{ r: 5 }} />
                                  <Line name="Knock Retard" type="monotone" dataKey="Knock" stroke={COLOR_KNK} strokeWidth={3} dot={false} />
                                </LineChart>
                              </ResponsiveContainer>
                            </div>
                          ) : (
                            <div style={{ textAlign: "center", padding: "100px 20px", color: "#64748b" }}>
                              <p style={{ fontSize: "1.1rem", marginBottom: "8px" }}>No Ignition or Knock sensors identified in this log.</p>
                              <p style={{ fontSize: "0.9rem" }}>Try a log containing Ignition Timing (`zwout`) or Knock Retard (`dwout`) columns.</p>
                            </div>
                          )}
                        </div>
                      )}

                      {/* 6.) Fuel Trim Correction */}
                      {selectedCharts.includes('trims') && (
                        <div style={{ padding: "25px", background: "rgba(0,0,0,0.2)", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.03)" }}>
                          <h3 style={{ color: COLOR_STFT, marginTop: 0, marginBottom: "25px", fontSize: "1.2rem", fontWeight: "600" }}>
                            📉 Fuel Trim Correction (STFT & LTFT)
                          </h3>
                          {resultData.chart_fuel_trims && resultData.chart_fuel_trims.length > 0 ? (
                            <div style={{ height: "400px", width: "100%", position: "relative" }}>
                              {(pinA !== null || pinB !== null) && resultData.chart_fuel_trims && (
                                <div style={{
                                  position: "absolute",
                                  top: "10px",
                                  right: "70px",
                                  zIndex: 10,
                                  background: "rgba(15, 23, 42, 0.95)",
                                  padding: "12px 18px",
                                  borderRadius: "10px",
                                  border: "1px solid #f43f5e",
                                  fontSize: "0.8rem",
                                  boxShadow: "0 8px 16px rgba(0,0,0,0.6)",
                                  pointerEvents: "none",
                                  minWidth: "160px"
                                }}>
                                  {(() => {
                                    const pA = pinA !== null ? resultData.chart_fuel_trims.find((d: any) => d.Time === pinA) : null;
                                    const pB = pinB !== null ? resultData.chart_fuel_trims.find((d: any) => d.Time === pinB) : null;

                                    const renderMetric = (label: string, key: string, color: string, suffix: string = "") => {
                                      const valA = pA?.[key];
                                      const valB = pB?.[key];
                                      const hasBoth = valA !== undefined && valB !== undefined && valA !== null && valB !== null;
                                      const delta = hasBoth ? (valB - valA) : null;

                                      return (
                                        <div style={{ marginBottom: "6px" }}>
                                          <div style={{ color: "#94a3b8", display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
                                            <span>{label}:</span>
                                            <span style={{ fontWeight: "600", color }}>
                                              {pinA !== null && <span>{valA ?? "N/A"}{suffix}</span>}
                                              {pinB !== null && <span> → {valB ?? "N/A"}{suffix}</span>}
                                            </span>
                                          </div>
                                          {delta !== null && (
                                            <div style={{ textAlign: "right", fontSize: "0.75rem", color: delta > 0 ? "#f43f5e" : delta < 0 ? "#34d399" : "#94a3b8", fontWeight: "700" }}>
                                              {delta > 0 ? "+" : ""}{delta.toFixed(1)}{suffix} Δ
                                            </div>
                                          )}
                                        </div>
                                      );
                                    };

                                    return (
                                      <div>
                                        {trimHasSTFT && renderMetric("STFT", "STFT", COLOR_STFT, "%")}
                                        {trimHasLTFT && renderMetric("LTFT", "LTFT", COLOR_LTFT, "%")}
                                      </div>
                                    );
                                  })()}
                                </div>
                              )}
                              <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={filteredTrims} syncId="efi-analysis" onClick={handleChartClick} margin={{ top: 5, right: 30, bottom: 20, left: 10 }}>
                                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                                  <XAxis
                                    dataKey="Time"
                                    type="number"
                                    stroke="#64748b"
                                    fontSize={11}
                                    tickLine={false}
                                    axisLine={false}
                                    label={{ value: 'Time (s)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 10 }}
                                  />
                                  {pinA !== null && (
                                    <ReferenceLine x={pinA} stroke="#f43f5e" strokeWidth={2} />
                                  )}
                                  {pinB !== null && (
                                    <ReferenceLine x={pinB} stroke="#f43f5e" strokeWidth={2} />
                                  )}
                                  {pinA !== null && pinB !== null && (
                                    <ReferenceArea x1={pinA} x2={pinB} fill="rgba(244,63,94,0.1)" />
                                  )}
                                  <YAxis
                                    stroke="#64748b"
                                    fontSize={11}
                                    tickLine={false}
                                    axisLine={false}
                                    width={60}
                                    label={{ value: 'Trim %', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }}
                                  />
                                  <Tooltip contentStyle={tooltipStyle} />
                                  <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "20px" }} />
                                  <Line name="Short Term (STFT)" type="monotone" dataKey="STFT" stroke={COLOR_STFT} strokeWidth={1} dot={false} strokeOpacity={0.8} />
                                  <Line name="Long Term (LTFT)" type="monotone" dataKey="LTFT" stroke={COLOR_LTFT} strokeWidth={4} dot={false} />
                                </LineChart>
                              </ResponsiveContainer>
                            </div>
                          ) : (
                            <div style={{ textAlign: "center", padding: "100px 20px", color: "#64748b" }}>
                              <p style={{ fontSize: "1.1rem", marginBottom: "8px" }}>No Fuel Trim sensors identified.</p>
                              <p style={{ fontSize: "0.9rem" }}>Requires `STFT` and `LTFT` columns.</p>
                            </div>
                          )}
                        </div>
                      )}

                      {selectedCharts.length === 0 && (
                        <div style={{ textAlign: "center", padding: "80px 20px", color: "#64748b", background: "rgba(255,255,255,0.01)", borderRadius: "12px", border: "1px dashed rgba(255,255,255,0.1)" }}>
                          <p style={{ fontSize: "1.1rem" }}>Select a visualization from the icons above to begin multi-chart analysis</p>
                        </div>
                      )}


                    </div>
                  </div>
                )}

                {/* BIN view */}
                {resultData.type === "bin" && (
                  <div>
                    <h3 style={{ color: "#e2e8f0", marginTop: 0, marginBottom: "20px" }}>Binary Hex Dump</h3>
                    <div style={{ display: "flex", gap: "20px", marginBottom: "20px" }}>
                      <p style={{ background: "rgba(0,0,0,0.3)", padding: "10px 15px", borderRadius: "6px", margin: 0 }}>
                        <strong>Size:</strong> {resultData.total_bytes} bytes
                      </p>
                      <p style={{ background: "rgba(0,0,0,0.3)", padding: "10px 15px", borderRadius: "6px", margin: 0 }}>
                        <strong>Preview:</strong> {resultData.preview_length} bytes
                      </p>
                    </div>
                    <pre style={{
                      background: "#05080f",
                      color: "#34d399",
                      padding: "20px",
                      borderRadius: "8px",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-all",
                      fontFamily: "'Fira Code', 'Courier New', monospace",
                      lineHeight: "1.6",
                      fontSize: "0.85rem",
                      border: "1px solid rgba(52,211,153,0.2)",
                    }}>
                      {resultData.hex_preview}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* ── Chat ── */}
            <div style={{
              background: "rgba(30,41,59,0.4)",
              backdropFilter: "blur(12px)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "16px",
              boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
              display: "flex",
              flexDirection: "column",
              height: "500px",
            }}>
              {/* Chat header */}
              <div style={{ padding: "20px 30px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "1.4rem", fontWeight: "600", color: "#f8fafc" }}>
                    <span style={{ width: "10px", height: "10px", background: "#34d399", borderRadius: "50%", boxShadow: "0 0 10px #34d399", display: "inline-block" }} />
                    Tuning Intelligence Agent
                  </span>
                  <input
                    type="password"
                    placeholder="Google Gemini API Key (AIza...)"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    style={{
                      width: "280px",
                      padding: "8px 15px",
                      borderRadius: "8px",
                      border: "1px solid rgba(255,255,255,0.2)",
                      background: "rgba(0,0,0,0.3)",
                      color: "white",
                      fontSize: "0.85rem",
                      outline: "none",
                    }}
                  />
                </div>
              </div>

              {/* Messages */}
              <div style={{ flex: 1, overflowY: "auto", padding: "20px 30px", display: "flex", flexDirection: "column", gap: "20px" }}>
                {messages.length === 0 && (
                  <div style={{ margin: "auto", textAlign: "center", color: "#64748b" }}>
                    <p style={{ fontSize: "1.2rem", marginBottom: "5px" }}>Assistant is online.</p>
                    <p style={{ fontSize: "0.95rem" }}>Upload a log file and ask me to analyze AFR, Boost, or RPM anomalies.</p>
                  </div>
                )}

                {messages.map((msg, idx) => (
                  <div key={idx} style={{ alignSelf: msg.role === "user" ? "flex-end" : "flex-start", maxWidth: "80%" }}>
                    <div style={{
                      padding: "14px 20px",
                      borderRadius: "16px",
                      borderBottomRightRadius: msg.role === "user" ? "4px" : "16px",
                      borderBottomLeftRadius: msg.role === "assistant" ? "4px" : "16px",
                      background: msg.role === "user"
                        ? "linear-gradient(135deg, #0072FF 0%, #00C6FF 100%)"
                        : "rgba(255,255,255,0.05)",
                      color: msg.role === "user" ? "#fff" : "#cbd5e1",
                      border: msg.role === "assistant" ? "1px solid rgba(255,255,255,0.1)" : "none",
                      lineHeight: "1.6",
                      fontSize: "0.95rem",
                    }}>
                      <strong style={{
                        display: "block",
                        marginBottom: "4px",
                        fontSize: "0.8rem",
                        color: msg.role === "user" ? "rgba(255,255,255,0.8)" : "#00C6FF",
                        textTransform: "uppercase",
                        letterSpacing: "1px",
                      }}>
                        {msg.role === "user" ? "You" : ""}
                      </strong>
                      <span style={{ whiteSpace: "pre-wrap" }}>{msg.content}</span>
                    </div>
                  </div>
                ))}

                {chatLoading && (
                  <div style={{ alignSelf: "flex-start" }}>
                    <div style={{ padding: "14px 20px", borderRadius: "16px", backgroundColor: "rgba(255,255,255,0.03)", color: "#64748b", fontStyle: "italic", fontSize: "0.95rem" }}>
                      Analyzing data traces...
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Input bar */}
              <div style={{
                padding: "20px 30px",
                borderTop: "1px solid rgba(255,255,255,0.05)",
                background: "rgba(0,0,0,0.2)",
                borderBottomLeftRadius: "16px",
                borderBottomRightRadius: "16px",
              }}>
                <div style={{ display: "flex", gap: "10px" }}>
                  <input
                    id="ai-chat-input"
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
                    placeholder="Ask about boost spikes, AFR targets, or anomaly detection..."
                    style={{
                      flex: 1,
                      padding: "16px 20px",
                      borderRadius: "12px",
                      border: "1px solid rgba(255,255,255,0.1)",
                      background: "rgba(255,255,255,0.03)",
                      color: "white",
                      fontSize: "1rem",
                      outline: "none",
                    }}
                    onFocus={(e) => e.target.style.borderColor = "#00C6FF"}
                    onBlur={(e) => e.target.style.borderColor = "rgba(255,255,255,0.1)"}
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={chatLoading || !chatInput.trim()}
                    style={{
                      padding: "0 30px",
                      background: chatLoading || !chatInput.trim()
                        ? "rgba(255,255,255,0.05)"
                        : "linear-gradient(135deg, #00C6FF 0%, #0072FF 100%)",
                      color: chatLoading || !chatInput.trim() ? "#64748b" : "white",
                      border: "none",
                      borderRadius: "12px",
                      fontSize: "1rem",
                      fontWeight: "600",
                      cursor: chatLoading || !chatInput.trim() ? "not-allowed" : "pointer",
                      boxShadow: chatLoading || !chatInput.trim() ? "none" : "0 4px 15px rgba(0,114,255,0.3)",
                    }}
                  >
                    Send
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "30px" }}>
            {/* --- Global Calibration Heatmap Suite --- */}
            {resultData && (
              <div style={{
                background: "rgba(15, 23, 42, 0.4)",
                border: "1px solid rgba(255,255,255,0.05)",
                borderRadius: "16px",
                padding: "25px",
                boxShadow: "0 10px 30px rgba(0,0,0,0.3)"
              }}>
                {/* Header */}
                <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "20px" }}>
                  <div style={{ width: "8px", height: "8px", background: "#00C6FF", borderRadius: "50%", boxShadow: "0 0 10px #00C6FF" }} />
                  <h3 style={{ margin: 0, color: "#f8fafc", fontSize: "1.1rem" }}>
                    📊 Global Calibration Heatmap Suite
                  </h3>
                </div>

                {/* Signal Selector + Count Toggle */}
                <div style={{ display: "flex", gap: "10px", marginBottom: "20px", flexWrap: "wrap", alignItems: "center" }}>
                  <span style={{ color: "#64748b", fontSize: "0.8rem", fontWeight: "700", letterSpacing: "0.06em", textTransform: "uppercase" }}>Signal:</span>
                  {([
                    { id: 'afr'      as const, label: '⛽ AFR',       key: 'afr_heatmap' },
                    { id: 'ignition' as const, label: '🔥 Ignition',  key: 'ignition_heatmap' },
                    { id: 'boost'    as const, label: '💨 Boost/MAP', key: 'boost_heatmap' },
                  ]).map((s) => {
                    const available = !!(resultData[s.key]?.cells?.length);
                    return (
                      <button
                        key={s.id}
                        onClick={() => available && setGlobalHeatmapSignal(s.id)}
                        style={{
                          padding: "8px 16px", borderRadius: "8px",
                          border: `1px solid ${globalHeatmapSignal === s.id ? '#00C6FF' : 'rgba(255,255,255,0.1)'}`,
                          background: globalHeatmapSignal === s.id ? 'rgba(0,198,255,0.15)' : 'transparent',
                          color: !available ? '#334155' : globalHeatmapSignal === s.id ? '#00C6FF' : '#94a3b8',
                          cursor: available ? 'pointer' : 'not-allowed',
                          fontSize: "0.85rem", fontWeight: "600", transition: "all 0.2s",
                        }}
                      >
                        {s.label}{!available && <span style={{ marginLeft: "5px", fontSize: "0.7rem" }}>N/A</span>}
                      </button>
                    );
                  })}
                  <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ color: "#64748b", fontSize: "0.78rem" }}>Sample Count</span>
                    <div
                      onClick={() => setShowHeatmapCount(v => !v)}
                      style={{
                        width: "38px", height: "22px", borderRadius: "11px",
                        background: showHeatmapCount ? "#00C6FF" : "rgba(255,255,255,0.1)",
                        cursor: "pointer", position: "relative", transition: "background 0.2s",
                      }}
                    >
                      <div style={{
                        width: "16px", height: "16px", borderRadius: "50%", background: "white",
                        position: "absolute", top: "3px",
                        left: showHeatmapCount ? "19px" : "3px", transition: "left 0.2s",
                      }} />
                    </div>
                  </div>
                </div>

                {/* Heatmap Table */}
                {(() => {
                  const hData = globalHeatmapSignal === 'afr'
                    ? resultData.afr_heatmap
                    : globalHeatmapSignal === 'ignition'
                    ? resultData.ignition_heatmap
                    : resultData.boost_heatmap;

                  if (!hData || !hData.cells || hData.cells.length === 0) {
                    return (
                      <div style={{ textAlign: "center", padding: "60px 20px", color: "#64748b" }}>
                        <p style={{ fontSize: "1rem", marginBottom: "8px" }}>
                          No <strong style={{ color: "#94a3b8" }}>{globalHeatmapSignal.toUpperCase()}</strong> data available.
                        </p>
                        <p style={{ fontSize: "0.85rem" }}>This signal was not detected or had insufficient coverage in this log.</p>
                      </div>
                    );
                  }

                  const getColor = (value: number) => {
                    if (globalHeatmapSignal === 'afr')      return getCellColor(value);
                    if (globalHeatmapSignal === 'ignition') return getIgnitionColor(value);
                    return getBoostColor(value);
                  };

                  return (
                    <div style={{ overflowX: "auto", paddingBottom: "10px" }}>
                      <table style={{ borderCollapse: "collapse", margin: "0 auto", fontSize: "0.75rem" }}>
                        <thead>
                          <tr>
                            <th style={{ padding: "8px 10px", color: "#64748b", border: "1px solid rgba(255,255,255,0.05)", textAlign: "center", whiteSpace: "nowrap" }}>
                              RPM \ {hData.load_type}
                            </th>
                            {hData.load_bins.map((load: number) => (
                              <th key={load} style={{ padding: "6px 4px", color: "#94a3b8", fontWeight: "600", border: "1px solid rgba(255,255,255,0.05)", textAlign: "center", minWidth: "48px" }}>
                                {load}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {hData.rpm_bins.map((rpm: number) => (
                            <tr key={rpm}>
                              <td style={{ padding: "6px 10px", color: "#94a3b8", fontWeight: "600", border: "1px solid rgba(255,255,255,0.05)", textAlign: "right", whiteSpace: "nowrap" }}>
                                {rpm}
                              </td>
                              {hData.load_bins.map((load: number) => {
                                const cell = hData.cells.find((c: any) => c.rpm === rpm && c.load === load);
                                const color = cell ? getColor(cell.value) : "rgba(255,255,255,0.02)";
                                const opacity = cell ? getOpacity(cell.count) : 1;
                                const displayVal = cell
                                  ? showHeatmapCount ? String(cell.count) : cell.value.toFixed(1)
                                  : "";
                                return (
                                  <td
                                    key={`${rpm}-${load}`}
                                    title={cell
                                      ? `Value: ${cell.value}\nStd Dev: ±${cell.std}\nSamples: ${cell.count}\nRPM: ${rpm} | Load: ${load}`
                                      : `RPM: ${rpm} | Load: ${load} — No Data`}
                                    style={{
                                      width: "48px", height: "34px",
                                      backgroundColor: color, opacity: opacity,
                                      border: "1px solid rgba(255,255,255,0.07)",
                                      textAlign: "center", verticalAlign: "middle",
                                      color: cell ? "white" : "rgba(255,255,255,0.08)",
                                      fontSize: showHeatmapCount ? "0.65rem" : "0.7rem",
                                      fontWeight: "bold", transition: "all 0.15s ease",
                                      cursor: cell ? "crosshair" : "default",
                                    }}
                                  >
                                    {displayVal}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}

                {/* Dynamic Legend */}
                <div style={{ display: "flex", justifyContent: "center", gap: "14px", marginTop: "16px", fontSize: "0.7rem", color: "#64748b", flexWrap: "wrap" }}>
                  {(globalHeatmapSignal === 'afr' ? [
                    { color: "#2563eb", label: "Rich (≤12.0)" },
                    { color: "#3b82f6", label: "Mid-Rich (12–12.5)" },
                    { color: "#10b981", label: "Optimal (12.5–13)" },
                    { color: "#f59e0b", label: "Mid-Lean (13–14.5)" },
                    { color: "#ef4444", label: "Lean (≥14.5)" },
                  ] : globalHeatmapSignal === 'ignition' ? [
                    { color: "#1e3a8a", label: "Retarded (<10°)" },
                    { color: "#3b82f6", label: "Conservative (10–20°)" },
                    { color: "#10b981", label: "Optimal (20–30°)" },
                    { color: "#f59e0b", label: "Aggressive (30–38°)" },
                    { color: "#ef4444", label: "Dangerous (>38°)" },
                  ] : [
                    { color: "#1e3a8a", label: "Vacuum (<100 kPa)" },
                    { color: "#3b82f6", label: "Atmosphere (100–130)" },
                    { color: "#10b981", label: "Light Boost (130–160)" },
                    { color: "#f59e0b", label: "High Boost (160–200)" },
                    { color: "#ef4444", label: "Overboost (>200)" },
                  ]).map((item) => (
                    <div key={item.label} style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                      <div style={{ width: "12px", height: "12px", background: item.color, borderRadius: "2px" }} />
                      {item.label}
                    </div>
                  ))}
                  {showHeatmapCount && <span style={{ color: "#94a3b8", fontStyle: "italic", marginLeft: "8px" }}>📊 Showing sample count</span>}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
