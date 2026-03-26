"use client";
import { useState, useRef, useEffect } from "react";
import axios from "axios";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend
} from "recharts";

export default function Home() {
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [resultData, setResultData] = useState(null);

  const [chatInput, setChatInput] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [messages, setMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  const handleChartClick = (state) => {
    if (state && state.activePayload && state.activePayload.length > 0) {
      const xValue = state.activeLabel;
      const details = state.activePayload
        .map((p) => `${p.name} = ${p.value}`)
        .join(", ");
      const prompt = `Analyze this specific engine anomaly at RPM ${xValue}: ${details}. Explain the thermodynamic physics behind this and explicitly state if this is dangerous for the engine.`;
      setChatInput(prompt);
      document.getElementById("ai-chat-input")?.focus();
    }
  };

  const handleFileChange = (e) => {
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

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await axios.post("http://localhost:8000/upload", formData);
      setStatus(`Successfully parsed: ${res.data.filename}`);
      setResultData(res.data);
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
      const res = await axios.post("http://localhost:8000/chat", {
        message: userMsg,
        api_key: apiKey,
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

  // The custom colors for our specific lines
  const COLOR_TPS = "#f59e0b"; // Orange
  const COLOR_MAP = "#34d399"; // Green 
  const COLOR_MAF = "#8b5cf6"; // Purple
  const COLOR_AFR = "#00C6FF"; // Blue

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
        <div style={{ textAlign: "center", marginBottom: "40px" }}>
          <h1 style={{
            fontSize: "2.5rem",
            fontWeight: "800",
            marginBottom: "10px",
            background: "linear-gradient(90deg, #00C6FF 0%, #0072FF 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}>
            ECU Analytics
          </h1>
          <p style={{ color: "#94a3b8", fontSize: "1.1rem" }}>

          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "30px" }}>

          {/* ── Uploader ── */}
          <div style={{
            background: "rgba(30, 41, 59, 0.4)",
            backdropFilter: "blur(12px)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "16px",
            padding: "30px",
            boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
          }}>
            <h2 style={{ marginTop: 0, fontSize: "1.5rem", color: "#f8fafc" }}>Data Pipeline</h2>

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

          {/* ── Data Preview ── */}
          {resultData && (
            <div style={{
              background: "rgba(15,23,42,0.6)",
              border: "1px solid rgba(255,255,255,0.05)",
              borderRadius: "16px",
              padding: "30px",
            }}>

              {/* CSV view */}
              {resultData.type === "csv" && (
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
                        {resultData.diagnostics.alerts.map((alert, idx) => (
                          <li key={idx} style={{ marginBottom: "4px" }}>{alert}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Column stats table */}
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
                            {Object.entries(resultData.column_stats).map(([col, stats], i) => {
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
                                      <span style={{ marginLeft: "6px", fontSize: "0.75rem", color: "#f87171" }}>⚠ LEAN</span>
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

                  {/* Tuning Curve Charts */}
                  {resultData.chart_rpm && resultData.chart_rpm.length > 0 && (
                    <div style={{ marginTop: "40px", padding: "25px", background: "rgba(0,0,0,0.2)", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.03)" }}>
                      <h3 style={{ color: "#00C6FF", marginTop: 0, marginBottom: "25px", fontSize: "1.2rem", fontWeight: "600" }}>
                        📊 Performance Diagnostics (RPM Binned)
                      </h3>

                      {/* 1.) RPM vs Throttle Position */}
                      <div style={{ marginBottom: "50px", height: "320px", width: "100%" }}>
                        <div style={{ marginBottom: "12px" }}>
                          <p style={{ color: "#f8fafc", fontSize: "1rem", margin: 0, fontWeight: "600" }}> 1. RPM vs Throttle Position</p>
                          <p style={{ color: "#94a3b8", fontSize: "0.85rem", margin: "4px 0" }}></p>
                          <p style={{ color: "#f59e0b", fontSize: "0.8rem", margin: 0 }}></p>
                        </div>
                        <ResponsiveContainer width="100%" height={250}>
                          <LineChart data={resultData.chart_rpm} syncId="engine-diagnostics" margin={{ top: 5, right: 30, bottom: 20, left: 0 }} onClick={handleChartClick} style={{ cursor: "pointer" }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                            <XAxis dataKey="name" type="number" domain={['auto', 'auto']} stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
                            <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} domain={[0, 100]} />
                            <Tooltip contentStyle={tooltipStyle} />
                            <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "10px" }} />
                            <Line name="Throttle Position (%)" type="monotone" dataKey="Throttle Position" stroke={COLOR_TPS} strokeWidth={2} dot={false} activeDot={{ r: 5 }} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>

                      {/* 2.) RPM vs MAP */}
                      <div style={{ marginBottom: "50px", height: "320px", width: "100%" }}>
                        <div style={{ marginBottom: "12px" }}>
                          <p style={{ color: "#f8fafc", fontSize: "1rem", margin: 0, fontWeight: "600" }}> 2. RPM vs MAP (Manifold Pressure)</p>
                          <p style={{ color: "#94a3b8", fontSize: "0.85rem", margin: "4px 0" }}></p>
                          <p style={{ color: "#34d399", fontSize: "0.8rem", margin: 0 }}></p>
                        </div>
                        <ResponsiveContainer width="100%" height={250}>
                          <LineChart data={resultData.chart_rpm} syncId="engine-diagnostics" margin={{ top: 5, right: 30, bottom: 20, left: 0 }} onClick={handleChartClick} style={{ cursor: "pointer" }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                            <XAxis dataKey="name" type="number" domain={['auto', 'auto']} stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
                            <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} domain={['auto', 'auto']} />
                            <Tooltip contentStyle={tooltipStyle} />
                            <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "10px" }} />
                            <Line name="Manifold Pressure (MAP)" type="monotone" dataKey="MAP" stroke={COLOR_MAP} strokeWidth={2} dot={false} activeDot={{ r: 5 }} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>

                      {/* 3.) RPM vs MAF */}
                      <div style={{ height: "320px", width: "100%" }}>
                        <div style={{ marginBottom: "12px" }}>
                          <p style={{ color: "#f8fafc", fontSize: "1rem", margin: 0, fontWeight: "600" }}> 3. RPM vs MAF (Airflow)</p>
                          <p style={{ color: "#94a3b8", fontSize: "0.85rem", margin: "4px 0" }}></p>
                          <p style={{ color: "#8b5cf6", fontSize: "0.8rem", margin: 0 }}></p>
                        </div>
                        <ResponsiveContainer width="100%" height={250}>
                          <LineChart data={resultData.chart_rpm} syncId="engine-diagnostics" margin={{ top: 5, right: 10, bottom: 20, left: 0 }} onClick={handleChartClick} style={{ cursor: "pointer" }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                            <XAxis dataKey="name" type="number" domain={['auto', 'auto']} stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
                            <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} domain={['auto', 'auto']} />
                            <Tooltip contentStyle={tooltipStyle} />
                            <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "10px" }} />
                            <Line name="Mass Airflow (MAF)" type="monotone" dataKey="MAF" stroke={COLOR_MAF} strokeWidth={2} dot={false} activeDot={{ r: 5 }} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>

                    </div>
                  )}
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
      </div>
    </div>
  );
}