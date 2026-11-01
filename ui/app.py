"""
PALIMPSEST Streamlit UI
5-tab dashboard: Chat, Memory Inspector, Decision Log, Version History, Evaluation.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PALIMPSEST",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inject CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.badge-verbatim  { background:#22c55e; color:#fff; padding:2px 8px; border-radius:12px; font-size:12px; }
.badge-summary   { background:#f59e0b; color:#fff; padding:2px 8px; border-radius:12px; font-size:12px; }
.badge-discard   { background:#ef4444; color:#fff; padding:2px 8px; border-radius:12px; font-size:12px; }
.metric-box      { background:#1e293b; padding:16px; border-radius:10px; text-align:center; }
</style>
""", unsafe_allow_html=True)


def get_agent():
    """Get or create the PALIMPSEST agent in session state."""
    if "agent" not in st.session_state:
        import sys, os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from config import Config
        from palimpsest.agent import PalimpsestAgent
        cfg = Config()
        st.session_state.agent = PalimpsestAgent(cfg)
        st.session_state.chat_history = []
        st.session_state.session_started = False
    return st.session_state.agent


def badge(category: str) -> str:
    cls = f"badge-{category}"
    return f'<span class="{cls}">{category}</span>'


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://via.placeholder.com/200x60/1e293b/64748b?text=📜+PALIMPSEST", use_column_width=True)
    st.markdown("### Settings")
    obj = st.text_area("Session Objective", "I am building a FastAPI REST API with PostgreSQL.", height=80)
    if st.button("🚀 Start New Session", use_container_width=True):
        agent = get_agent()
        vid = agent.start_session(objective=obj)
        st.session_state.chat_history = []
        st.session_state.session_started = True
        st.session_state.current_version_id = vid
        st.success(f"Session started! Version: {vid[:8]}...")

    st.markdown("---")
    st.markdown("### Version Operations")
    all_versions = []
    if "agent" in st.session_state:
        tree = st.session_state.agent.get_version_history()
        for branch, versions in tree.items():
            for v in versions:
                all_versions.append(v["version_id"])

    selected_version = st.selectbox("Select Version", all_versions or ["No versions yet"])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⏪ Rollback", use_container_width=True):
            if selected_version and selected_version != "No versions yet":
                agent = get_agent()
                new_sid = agent.rollback(selected_version)
                st.session_state.chat_history = []
                st.success(f"Rolled back! New session: {new_sid[:8]}...")

    with col2:
        branch_name = st.text_input("Branch name", "feature-1")
        if st.button("🌿 Branch", use_container_width=True):
            if selected_version and selected_version != "No versions yet":
                agent = get_agent()
                agent.branch_session(selected_version, branch_name, f"Branch: {branch_name}")
                st.success("Branch created!")

    st.markdown("---")
    st.caption("PALIMPSEST v1.0 | Proof of Concept")


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(["💬 Chat", "🧠 Memory Inspector", "📋 Decision Log", "🌳 Version History", "📊 Evaluation"])


# ── TAB 1: CHAT ────────────────────────────────────────────────────────────────
with tab1:
    st.header("Chat with PALIMPSEST")

    agent = get_agent()

    if not st.session_state.get("session_started"):
        st.info("👈 Start a session from the sidebar to begin chatting.")
    else:
        # Display chat history
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if "tokens" in msg:
                    st.caption(f"~{msg['tokens']} tokens")

        # Chat input
        user_input = st.chat_input("Type your message...")
        if user_input:
            with st.chat_message("user"):
                st.write(user_input)
            st.session_state.chat_history.append({"role": "user", "content": user_input})

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = agent.chat(user_input)
                st.write(response)
                token_est = len(response) // 4
                st.caption(f"~{token_est} tokens | Version: {agent._active_version_id[:8] if agent._active_version_id else 'N/A'}...")

            st.session_state.chat_history.append({
                "role": "assistant",
                "content": response,
                "tokens": token_est,
            })


# ── TAB 2: MEMORY INSPECTOR ────────────────────────────────────────────────────
with tab2:
    st.header("🧠 Memory Inspector")
    agent = get_agent()

    col_v, col_f = st.columns([2, 1])
    with col_v:
        vid = st.selectbox("Select Version to Inspect", all_versions or ["None"], key="inspect_version")
    with col_f:
        filter_cat = st.multiselect("Filter Category", ["verbatim", "summary", "discard"],
                                    default=["verbatim", "summary", "discard"])

    if vid and vid != "None":
        summary = agent.get_memory_summary(vid)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Items", summary["total_items"])
        c2.metric("✅ Verbatim", summary["verbatim_count"])
        c3.metric("🟡 Summary", summary["summary_count"])
        c4.metric("🔴 Discarded", summary["discard_count"])

        items = agent.store.get_items_by_version(vid)
        items = [i for i in items if i.category.value in filter_cat]

        if items:
            for item in items:
                with st.expander(f"{badge(item.category.value)} | {item.role.value.upper()} | {item.content[:80]}...", expanded=False):
                    st.markdown(f"**Full Content:**\n{item.content}")
                    st.markdown(f"**Topics:** {', '.join(item.topic_tags) or 'None'}")
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Importance", f"{item.importance_score:.2f}")
                    col_b.metric("Relevance", f"{item.relevance_score:.2f}")
                    col_c.metric("Tokens", item.token_count)
                    st.info(f"**Rationale:** {item.decision_rationale}")
        else:
            st.info("No items found for the selected filters.")


# ── TAB 3: DECISION LOG ────────────────────────────────────────────────────────
with tab3:
    st.header("📋 Decision Log")
    agent = get_agent()

    if all_versions:
        log_vid = st.selectbox("Select Version", all_versions, key="log_version")
        decisions = agent.inspect_decisions(log_vid)

        if decisions:
            rows = []
            for d in decisions:
                rows.append({
                    "Timestamp": d.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "Category": d.category.value,
                    "Item ID": d.memory_item_id[:8] + "...",
                    "Rationale": d.rationale,
                    "Importance": d.factors.get("importance", "-"),
                    "Relevance": d.factors.get("relevance", "-"),
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False)
            st.download_button("⬇️ Download as CSV", csv, "decisions.csv", "text/csv")
        else:
            st.info("No decisions recorded for this version yet.")
    else:
        st.info("Start a session and chat to see decisions here.")


# ── TAB 4: VERSION HISTORY ─────────────────────────────────────────────────────
with tab4:
    st.header("🌳 Version History")
    agent = get_agent()
    tree = agent.get_version_history()

    if tree:
        for branch, versions in tree.items():
            st.subheader(f"Branch: `{branch}`")
            for v in versions:
                col1, col2, col3 = st.columns([3, 1, 2])
                merge_tag = "🔀 MERGED" if v.get("is_merged") else ""
                col1.markdown(f"**{v['topic_label'] or 'No label'}** {merge_tag}")
                col2.markdown(f"`{v['version_id'][:8]}...`")
                col3.markdown(f"{v['item_count']} items | {v['created_at'][:19]}")
                if v.get("parent"):
                    st.caption(f"  ↑ parent: {v['parent'][:8]}...")
                st.markdown("---")
    else:
        st.info("No versions yet. Start a session to create the first version.")


# ── TAB 5: EVALUATION ──────────────────────────────────────────────────────────
with tab5:
    st.header("📊 Evaluation — PALIMPSEST vs Baseline")
    st.markdown("Runs a scripted conversation through both agents and compares metrics.")

    if st.button("▶️ Run Comparison (Mock Mode)", use_container_width=True):
        with st.spinner("Running evaluation... this may take a moment."):
            from config import Config
            from evaluation.evaluator import Evaluator
            cfg = Config()
            cfg.mock_mode = True
            evaluator = Evaluator(cfg)
            report = evaluator.run_comparison()

        st.success("Evaluation complete!")
        st.markdown(f"**Summary:** {report.summary}")

        # Metrics bar chart
        fig = go.Figure(data=[
            go.Bar(name="Baseline",    x=["Tokens", "Cost (µ\$)", "Avg Latency (ms)"],
                   y=[report.baseline_total_tokens,
                      report.baseline_estimated_cost_usd * 1_000_000,
                      report.baseline_avg_latency_ms],
                   marker_color="#ef4444"),
            go.Bar(name="PALIMPSEST", x=["Tokens", "Cost (µ\$)", "Avg Latency (ms)"],
                   y=[report.palimpsest_total_tokens,
                      report.palimpsest_estimated_cost_usd * 1_000_000,
                      report.palimpsest_avg_latency_ms],
                   marker_color="#22c55e"),
        ])
        fig.update_layout(barmode="group", title="Performance Comparison", template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        # Quality scores
        col1, col2 = st.columns(2)
        col1.metric("Baseline Memory Recall", f"{report.baseline_quality_score:.0%}")
        col2.metric("PALIMPSEST Memory Recall", f"{report.palimpsest_quality_score:.0%}",
                    delta=f"{(report.palimpsest_quality_score - report.baseline_quality_score):.0%}")

        # Turn-by-turn table
        st.subheader("Turn-by-Turn Results")
        rows = []
        for t in report.turns:
            rows.append({
                "User": t["user"][:50],
                "Probe?": "✓" if t["is_probe"] else "",
                "P Latency": f"{t['palimpsest_latency_ms']:.0f}ms",
                "B Latency": f"{t['baseline_latency_ms']:.0f}ms",
                "P Recalled": t.get("palimpsest_recalled", ""),
                "B Recalled": t.get("baseline_recalled", ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
