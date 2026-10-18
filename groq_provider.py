"""Optional Groq cloud LLM provider (OpenAI-compatible tool-calling), default model 'openai/gpt-oss-20b'.
Fully optional: if GROQ_API_KEY is not configured, the 'groq' package is not installed, or any API call
fails, the agent falls back to the existing offline rule-based parser."""
import json, os

DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
MAX_OUTPUT_TOKENS = 600
MAX_TOOL_ROUNDS = 6

def _get_secret(name, default=None):
    try:
        import streamlit as st
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)

def groq_ready() -> bool:
    if not _get_secret("GROQ_API_KEY"):
        return False
    try:
        import groq  # noqa: F401
    except ImportError:
        return False
    return True

def _to_openai_tools(anthropic_style_tools):
    out = []
    for t in anthropic_style_tools:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return out

def groq_loop(user_msg, history, evidence, ledger, system_prompt, tools, dispatch_fn):
    import groq
    model = _get_secret("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    client = groq.Groq(api_key=_get_secret("GROQ_API_KEY"))
    openai_tools = _to_openai_tools(tools)
    messages = [{"role": "system", "content": system_prompt}]
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_msg})
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=openai_tools, tool_choice="auto",
            max_tokens=MAX_OUTPUT_TOKENS, temperature=0.2,
        )
        choice = resp.choices[0]
        msg = choice.message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return msg.content or ""
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": tool_calls})
        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            out = dispatch_fn(name, args, ledger)
            evidence.append(json.dumps(out))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(out)})
    return "Sorry, that took too many steps. Please rephrase."
